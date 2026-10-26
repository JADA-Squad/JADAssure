"""Versioned rule configuration per organization (BE-012, FR-15).

Each check has a typed parameter model. Changing parameters creates a new RuleVersion; findings
record the version they were computed with. Business-type differences (e.g. how long after the
billing date an unbilled delivery counts as leakage) are configuration, never code (FR-42).
"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.audit import service as audit
from app.domains.rules.models import CHECK_TYPES, Rule, RuleVersion


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeliveredNotBilledParams(_Params):
    grace_days: int = Field(15, ge=0, le=365, description="Days after the billing date before unbilled delivery is leakage")
    min_value: Decimal = Field(Decimal("0.01"), ge=0, description="Ignore shortfalls below this value")


class IncorrectRateParams(_Params):
    unit_price_tolerance: Decimal = Field(Decimal("0.01"), ge=0, description="Allowed unit price difference")
    min_value: Decimal = Field(Decimal("0.01"), ge=0)


class ExpiredDiscountParams(_Params):
    discount_tolerance_pct: Decimal = Field(Decimal("0.01"), ge=0, description="Allowed excess discount, in % points")
    min_value: Decimal = Field(Decimal("0.01"), ge=0)


class MissedIncreaseParams(_Params):
    unit_price_tolerance: Decimal = Field(Decimal("0.01"), ge=0)
    min_value: Decimal = Field(Decimal("0.01"), ge=0)


class CreditOutsidePolicyParams(_Params):
    require_reason_code: bool = True
    # Fallbacks when an agreement has no credit_policy term; None means "no limit".
    default_approval_threshold: Decimal | None = Field(None, ge=0)
    default_max_credit: Decimal | None = Field(None, ge=0)


PARAM_MODELS: dict[str, type[_Params]] = {
    "delivered_not_billed": DeliveredNotBilledParams,
    "incorrect_rate": IncorrectRateParams,
    "expired_discount": ExpiredDiscountParams,
    "missed_increase": MissedIncreaseParams,
    "credit_outside_policy": CreditOutsidePolicyParams,
}
assert set(PARAM_MODELS) == set(CHECK_TYPES)

# Starting configuration per business type (seeded as version 1). Anything not listed uses defaults.
BUSINESS_TYPE_DEFAULTS: dict[str, dict[str, dict[str, Any]]] = {
    "professional_services": {"delivered_not_billed": {"grace_days": 10}},
    "subscription_software": {"delivered_not_billed": {"grace_days": 5}},
    "distribution": {"delivered_not_billed": {"grace_days": 3}},
}


def validate_params(check_type: str, params: dict[str, Any]) -> dict[str, Any]:
    """Validated, JSON-safe params (decimals as strings)."""
    try:
        model = PARAM_MODELS[check_type].model_validate(params)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors(include_url=False, include_context=False)) from None
    # Normalize decimals so "5", "5.0" and "5.00" are the same configuration.
    return {k: (_decimal_text(v) if isinstance(v, Decimal) else v) for k, v in model.model_dump().items()}


def _decimal_text(d: Decimal) -> str:
    text = format(d.normalize(), "f")
    return "0" if text in ("-0", "") else text


def typed(check_type: str, params: dict[str, Any]) -> Any:
    return PARAM_MODELS[check_type].model_validate(params)


def _new_version(session: Session, rule: Rule, params: dict[str, Any], actor_id: uuid.UUID | None) -> RuleVersion:
    last = session.scalar(select(func.max(RuleVersion.version_no)).where(RuleVersion.rule_id == rule.id)) or 0
    version = RuleVersion(org_id=rule.org_id, rule_id=rule.id, version_no=last + 1, params=params, created_by=actor_id)
    session.add(version)
    session.flush()
    rule.active_version_id = version.id
    audit.record(session, org_id=rule.org_id, actor_id=actor_id, action="rule.version_created", entity="rule",
                 entity_id=rule.id, payload={"check_type": rule.check_type, "version_no": version.version_no,
                                             "params": params})
    return version


def ensure_rules(session: Session, org_id: uuid.UUID, business_type: str, actor_id: uuid.UUID | None) -> dict[str, RuleVersion]:
    """Create version 1 of any missing rule; return the active version per check type."""
    rules = {r.check_type: r for r in session.scalars(select(Rule).where(Rule.org_id == org_id))}
    overrides = BUSINESS_TYPE_DEFAULTS.get(business_type, {})
    for check_type in CHECK_TYPES:
        if check_type not in rules:
            rule = Rule(org_id=org_id, check_type=check_type)
            session.add(rule)
            session.flush()
            _new_version(session, rule, validate_params(check_type, overrides.get(check_type, {})), actor_id)
            rules[check_type] = rule
    return {ct: session.get(RuleVersion, r.active_version_id) for ct, r in rules.items()}  # type: ignore[misc]


def update_params(session: Session, org_id: uuid.UUID, check_type: str, params: dict[str, Any],
                  actor_id: uuid.UUID) -> RuleVersion:
    rule = session.scalar(select(Rule).where(Rule.org_id == org_id, Rule.check_type == check_type))
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    clean = validate_params(check_type, params)
    current = session.get(RuleVersion, rule.active_version_id)
    if current is not None and current.params == clean:
        return current  # no-op: identical parameters don't create a version
    return _new_version(session, rule, clean, actor_id)

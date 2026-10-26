import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext
from app.domains.access.models import Organization
from app.domains.access.permissions import Cap, require
from app.domains.rules import config
from app.domains.rules.models import Rule, RuleVersion

router = APIRouter(prefix="/api/rules", tags=["rules"])

CheckType = Literal["delivered_not_billed", "incorrect_rate", "expired_discount", "missed_increase",
                    "credit_outside_policy"]


class RuleVersionOut(BaseModel):
    id: uuid.UUID
    version_no: int
    params: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: datetime


class RuleOut(BaseModel):
    check_type: str
    active_version: RuleVersionOut
    history: list[RuleVersionOut]


class RuleUpdateIn(BaseModel):
    params: dict[str, Any]


def _rules_out(session: Session, org_id: uuid.UUID) -> list[RuleOut]:
    out = []
    for rule in session.scalars(select(Rule).where(Rule.org_id == org_id).order_by(Rule.check_type)):
        versions = list(session.scalars(
            select(RuleVersion).where(RuleVersion.rule_id == rule.id).order_by(RuleVersion.version_no.desc())
        ))
        history = [RuleVersionOut.model_validate(v, from_attributes=True) for v in versions]
        active = next(h for h in history if h.id == rule.active_version_id)
        out.append(RuleOut(check_type=rule.check_type, active_version=active, history=history))
    return out


@router.get("", response_model=list[RuleOut])
def list_rules(ctx: TenantContext = Depends(require(Cap.VIEW_AGREEMENTS)), session: Session = Depends(get_session)):
    org = session.get(Organization, ctx.org_id)
    config.ensure_rules(session, ctx.org_id, org.business_type, None)  # type: ignore[union-attr]
    session.commit()
    return _rules_out(session, ctx.org_id)


@router.put("/{check_type}", response_model=RuleOut)
def update_rule(check_type: CheckType, data: RuleUpdateIn, ctx: TenantContext = Depends(require(Cap.EDIT_RULES)),
                session: Session = Depends(get_session)):
    org = session.get(Organization, ctx.org_id)
    config.ensure_rules(session, ctx.org_id, org.business_type, None)  # type: ignore[union-attr]
    config.update_params(session, ctx.org_id, check_type, data.params, ctx.user_id)
    session.commit()
    return next(r for r in _rules_out(session, ctx.org_id) if r.check_type == check_type)

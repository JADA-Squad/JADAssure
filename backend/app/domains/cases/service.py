"""Findings queue, detail, timeline and comments (BE-020, FR-25, FR-26)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, aliased

from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.models import User
from app.domains.audit import service as audit
from app.domains.access.permissions import Cap, has_cap
from app.domains.cases.models import Approval, Correction, InvestigationEvent
from app.domains.cases.schemas import (
    CorrectionRef,
    FilterOption,
    FindingDetail,
    FindingFilters,
    FindingListItem,
    FindingPage,
    RuleVersionRef,
    TimelineEntry,
)
from app.domains.contracts.models import Agreement
from app.domains.ingestion.models import Customer
from app.domains.rules.models import CheckRun, Finding, RuleVersion

# Priority = value × confidence weight (FR-25).
CONFIDENCE_WEIGHT = {"high": Decimal("1.0"), "medium": Decimal("0.7"), "low": Decimal("0.4")}
_weight = case(*((Finding.confidence == k, v) for k, v in CONFIDENCE_WEIGHT.items()), else_=Decimal("0.4"))
PRIORITY = (Finding.value * _weight).label("priority")

Owner = aliased(User)


def _base(ctx: TenantContext) -> Select:
    return (
        select(Finding, Customer.name, Agreement.title, Owner.name, PRIORITY)
        .where(Finding.org_id == ctx.org_id)
        .outerjoin(Customer, Customer.id == Finding.customer_id)
        .outerjoin(Agreement, Agreement.id == Finding.agreement_id)
        .outerjoin(Owner, Owner.id == Finding.owner_id)
    )


def _item(row, now: datetime) -> dict:
    f, customer_name, agreement_title, owner_name, priority = row
    return {
        "id": f.id, "check_type": f.check_type, "family": f.family, "status": f.status, "value": f.value,
        "currency": f.currency, "confidence": f.confidence, "priority": priority.quantize(Decimal("0.0001")),
        "customer_id": f.customer_id, "customer_name": customer_name, "agreement_title": agreement_title,
        "item_code": f.item_code, "period_start": f.period_start, "period_end": f.period_end,
        "owner_id": f.owner_id, "owner_name": owner_name, "reason": f.reason,
        "age_days": (now - f.created_at).days, "created_at": f.created_at,
    }


def list_findings(
    session: Session,
    ctx: TenantContext,
    *,
    min_value: Decimal | None = None,
    max_value: Decimal | None = None,
    customer_id: uuid.UUID | None = None,
    check_type: str | None = None,
    confidence: str | None = None,
    statuses: list[str] | None = None,
    owner_id: uuid.UUID | None = None,
    unassigned: bool = False,
    min_age_days: int | None = None,
    max_age_days: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> FindingPage:
    now = datetime.now(UTC)
    stmt = _base(ctx)
    conditions = []
    if min_value is not None:
        conditions.append(Finding.value >= min_value)
    if max_value is not None:
        conditions.append(Finding.value <= max_value)
    if customer_id:
        conditions.append(Finding.customer_id == customer_id)
    if check_type:
        conditions.append(Finding.check_type == check_type)
    if confidence:
        conditions.append(Finding.confidence == confidence)
    if statuses:
        conditions.append(Finding.status.in_(statuses))
    if owner_id:
        conditions.append(Finding.owner_id == owner_id)
    if unassigned:
        conditions.append(Finding.owner_id.is_(None))
    if min_age_days is not None:
        conditions.append(Finding.created_at <= now - timedelta(days=min_age_days))
    if max_age_days is not None:
        conditions.append(Finding.created_at >= now - timedelta(days=max_age_days))
    stmt = stmt.where(*conditions)

    total = session.scalar(select(func.count()).select_from(stmt.with_only_columns(Finding.id).subquery())) or 0
    sums = session.execute(
        select(Finding.currency, func.sum(Finding.value)).where(Finding.org_id == ctx.org_id, *conditions)
        .outerjoin(Customer, Customer.id == Finding.customer_id).group_by(Finding.currency)
    ).all()
    rows = session.execute(stmt.order_by(PRIORITY.desc(), Finding.created_at, Finding.id).limit(limit).offset(offset))
    return FindingPage(items=[FindingListItem(**_item(r, now)) for r in rows], total=total,
                       value_by_currency={c: v for c, v in sums})


def filters(session: Session, ctx: TenantContext) -> FindingFilters:
    customers = session.execute(
        select(Customer.id, Customer.name).join(Finding, Finding.customer_id == Customer.id)
        .where(Finding.org_id == ctx.org_id).distinct().order_by(Customer.name)
    ).all()
    owners = session.execute(
        select(User.id, User.name).where(User.org_id == ctx.org_id, User.active.is_(True),
                                         User.role.in_(("analyst", "approver", "commercial"))).order_by(User.name)
    ).all()
    present = session.execute(select(Finding.check_type, Finding.status).where(Finding.org_id == ctx.org_id)).all()
    return FindingFilters(
        customers=[FilterOption(id=i, name=n) for i, n in customers],
        owners=[FilterOption(id=i, name=n) for i, n in owners],
        check_types=sorted({c for c, _ in present}),
        statuses=sorted({s for _, s in present}),
    )


def detail(session: Session, ctx: TenantContext, finding_id: uuid.UUID) -> FindingDetail:
    get_scoped(session, Finding, finding_id, ctx)  # 404 across orgs (GR-06)
    row = session.execute(_base(ctx).where(Finding.id == finding_id)).one()
    f: Finding = row[0]
    rv = session.get(RuleVersion, f.rule_version_id)
    first_run = session.get(CheckRun, f.first_run_id)
    last_run = session.get(CheckRun, f.last_run_id)
    names = {u.id: u.name for u in session.scalars(scoped(User, ctx))}

    timeline = [TimelineEntry(at=f.created_at, kind="detected", actor_name=None,
                              body=f"Detected by {f.check_type.replace('_', ' ')} check",
                              data={"run_id": str(f.first_run_id)})]
    for e in session.scalars(scoped(InvestigationEvent, ctx).where(InvestigationEvent.finding_id == f.id)
                             .order_by(InvestigationEvent.created_at)):
        timeline.append(TimelineEntry(at=e.created_at, kind=e.kind, actor_name=names.get(e.actor_id), body=e.body,
                                      data=e.data))
    for a in session.scalars(scoped(Approval, ctx).where(Approval.finding_id == f.id)):
        timeline.append(TimelineEntry(at=a.created_at, kind="approval", actor_name=names.get(a.approver_id),
                                      body=a.note, data={"decision": a.decision}))
    timeline.sort(key=lambda t: t.at)

    item = _item(row, datetime.now(UTC))
    correction = session.scalar(select(Correction).where(Correction.finding_id == f.id))
    return FindingDetail(
        **item,
        also_detected_by=list(f.also_detected_by or []),
        recommended_action=f.recommended_action,
        calculation=f.calculation,
        evidence=f.evidence,
        rule_version=RuleVersionRef(id=rv.id, version_no=rv.version_no, params=rv.params),  # type: ignore[union-attr]
        root_cause_category=f.root_cause_category,
        root_cause=f.root_cause,
        proposer_id=f.proposer_id,
        proposer_name=names.get(f.proposer_id),
        correction=CorrectionRef(id=correction.id, reference=correction.reference, kind=correction.kind,
                                 status=correction.status, amount=correction.amount,
                                 currency=correction.currency) if correction else None,
        available_actions=available_actions(ctx, f),
        ai_summary=f.ai_summary,
        first_detected_at=first_run.created_at if first_run else f.created_at,
        last_checked_at=(last_run.finished_at or last_run.created_at) if last_run else f.updated_at,
        timeline=timeline,
    )


def available_actions(ctx: TenantContext, f: Finding) -> list[str]:
    """What this user may do to this finding right now (FE-004 shows exactly these)."""
    from app.domains.cases.workflow import ASSIGNABLE, TRANSITIONS

    actions = []
    if has_cap(ctx.role, Cap.COMMENT_ASSIGN):
        actions.append("comment")
        if f.status in ASSIGNABLE:
            actions.append("assign")
    for name, t in TRANSITIONS.items():
        if has_cap(ctx.role, t.cap) and f.status in t.from_states:
            if name == "approve" and f.proposer_id == ctx.user_id:
                continue  # separation of duties (GR-12)
            actions.append(name)
    return actions


def add_comment(session: Session, ctx: TenantContext, finding_id: uuid.UUID, body: str) -> None:
    from app.domains.cases.workflow import lock_finding, start_review_if_open

    f = lock_finding(session, ctx, finding_id)
    start_review_if_open(session, ctx, f, "comment")
    session.add(InvestigationEvent(org_id=ctx.org_id, finding_id=f.id, actor_id=ctx.user_id, kind="comment",
                                   body=body.strip(), data={}))
    # Audit the fact of the comment, not its text (GR-15).
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="finding.commented", entity="finding",
                 entity_id=f.id, payload={"length": len(body)})

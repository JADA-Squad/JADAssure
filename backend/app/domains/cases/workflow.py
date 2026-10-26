"""Finding workflow (BE-021, FR-27, FR-28, GR-12, GR-13). Transitions exactly as design §2.5.

    open --assign/comment--> in_review --propose--> proposed --approve--> approved
    open|in_review --reject--> rejected            proposed --send_back--> in_review
    approved|billed --write_off--> closed_no_recovery
    approved --> billed --> recovered  (system only, from imported invoices and payments: recovery domain)

Every transition locks the finding row (no double approval), records a timeline event and an audit
event in the same transaction, and checks the from-state. The database trigger from migration 0004
makes terminal findings immutable whatever code path tries.
"""

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.domains.access.models import User
from app.domains.access.permissions import Cap, has_cap
from app.domains.audit import service as audit
from app.domains.cases import corrections
from app.domains.cases.models import Approval, InvestigationEvent
from app.domains.rules.models import ROOT_CAUSES, Finding


@dataclass(frozen=True)
class Transition:
    from_states: frozenset[str]
    to_state: str | None  # None: status unchanged (assign on later states)
    cap: Cap


TRANSITIONS: dict[str, Transition] = {
    "propose": Transition(frozenset({"in_review"}), "proposed", Cap.PROPOSE_REJECT),
    "reject": Transition(frozenset({"open", "in_review"}), "rejected", Cap.PROPOSE_REJECT),
    "send_back": Transition(frozenset({"proposed"}), "in_review", Cap.APPROVE),
    "approve": Transition(frozenset({"proposed"}), "approved", Cap.APPROVE),
    "write_off": Transition(frozenset({"approved", "billed"}), "closed_no_recovery", Cap.APPROVE),
}
ASSIGNABLE = frozenset({"open", "in_review", "proposed", "approved", "billed"})
CASE_ROLES = ("analyst", "approver", "commercial")


def lock_finding(session: Session, ctx: TenantContext, finding_id: uuid.UUID) -> Finding:
    f = session.scalar(select(Finding).where(Finding.id == finding_id, Finding.org_id == ctx.org_id)
                       .with_for_update())
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return f


def _event(session: Session, ctx: TenantContext | None, f: Finding, action: str, frm: str, to: str,
           note: str | None, extra: dict | None = None, org_id: uuid.UUID | None = None) -> None:
    org = org_id or (ctx.org_id if ctx else f.org_id)
    actor = ctx.user_id if ctx else None
    session.add(InvestigationEvent(org_id=org, finding_id=f.id, actor_id=actor, kind="status", body=note,
                                   data={"action": action, "from": frm, "to": to, **(extra or {})}))
    audit.record(session, org_id=org, actor_id=actor, action=f"finding.{action}", entity="finding", entity_id=f.id,
                 payload={"from": frm, "to": to, **(extra or {})})


def start_review_if_open(session: Session, ctx: TenantContext, f: Finding, action: str) -> None:
    """open → in_review on first assignment or comment (design §2.5)."""
    if f.status == "open":
        f.status = "in_review"
        _event(session, ctx, f, action, "open", "in_review", None)


def assign(session: Session, ctx: TenantContext, finding_id: uuid.UUID, owner_id: uuid.UUID | None) -> Finding:
    f = lock_finding(session, ctx, finding_id)
    if f.status not in ASSIGNABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A {f.status} finding can't be reassigned")
    if owner_id is not None:
        owner = session.get(User, owner_id)
        if owner is None or owner.org_id != ctx.org_id or not owner.active or owner.role not in CASE_ROLES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Owner must be an active analyst, approver "
                                                                       "or commercial manager in your organization")
    f.owner_id = owner_id
    session.add(InvestigationEvent(org_id=ctx.org_id, finding_id=f.id, actor_id=ctx.user_id, kind="assign",
                                   body=None, data={"owner_id": str(owner_id) if owner_id else None}))
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="finding.assigned", entity="finding",
                 entity_id=f.id, payload={"owner_id": str(owner_id) if owner_id else None})
    start_review_if_open(session, ctx, f, "assign")
    return f


def transition(session: Session, ctx: TenantContext, finding_id: uuid.UUID, action: str, *,
               note: str | None = None, root_cause_category: str | None = None,
               root_cause: str | None = None) -> Finding:
    t = TRANSITIONS[action]
    if not has_cap(ctx.role, t.cap):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit this action")
    f = lock_finding(session, ctx, finding_id)
    if f.status not in t.from_states:
        allowed = ", ".join(sorted(t.from_states))
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Can't {action.replace('_', ' ')} a finding that is {f.status} (allowed from: {allowed})")
    extra: dict = {}
    if action == "propose":
        if root_cause_category not in ROOT_CAUSES or not (root_cause or "").strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "A root cause category and description are required to propose (FR-31)")
        f.root_cause_category = root_cause_category
        f.root_cause = root_cause.strip()  # type: ignore[union-attr]
        f.proposer_id = ctx.user_id
        extra = {"root_cause_category": root_cause_category}
    elif action in ("reject", "send_back", "write_off") and not (note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A reason is required")
    elif action == "approve" and f.proposer_id == ctx.user_id:
        # Separation of duties (GR-12): whoever proposed can't approve.
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You proposed this finding, so a different approver must approve it (separation of duties)")

    frm = f.status
    f.status = t.to_state  # type: ignore[assignment]
    if action in ("approve", "send_back", "write_off"):
        decision = {"approve": "approved", "send_back": "sent_back", "write_off": "written_off"}[action]
        session.add(Approval(org_id=ctx.org_id, finding_id=f.id, approver_id=ctx.user_id, decision=decision,
                             note=(note or "").strip() or None))
    if action == "approve":
        c = corrections.prepare(session, ctx, f)  # FR-29: exactly one prepared correction
        extra = {"correction_reference": c.reference}
    _event(session, ctx, f, action, frm, f.status, (note or "").strip() or None, extra)
    session.flush()
    return f


def system_transition(session: Session, f: Finding, to: str, note: str, extra: dict | None = None) -> None:
    """Recovery-driven moves (approved → billed → recovered). Never used for human decisions."""
    frm = f.status
    f.status = to
    _event(session, None, f, to, frm, to, note, extra, org_id=f.org_id)

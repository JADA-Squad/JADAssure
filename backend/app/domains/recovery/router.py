import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.models import Organization
from app.domains.access.permissions import Cap, require, require_any
from app.domains.cases.models import Correction
from app.domains.ingestion.models import Invoice
from app.domains.recovery import demo_simulation, service
from app.domains.recovery.models import RecoveryEvent
from app.domains.rules.models import Finding

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


class RecoveryEventOut(BaseModel):
    kind: str
    amount: Decimal
    source_entity: str
    occurred_on: str


class CorrectionRow(BaseModel):
    id: uuid.UUID
    reference: str
    kind: str
    status: str
    amount: Decimal
    currency: str
    finding_id: uuid.UUID
    finding_status: str
    check_type: str
    customer_name: str | None
    invoice_numbers: list[str]
    billed: Decimal
    cash_received: Decimal
    cash_recovered: Decimal  # verified outcome: payments against the corrected invoice, capped (GR-04)
    events: list[RecoveryEventOut]
    created_at: datetime


class TrackerOut(BaseModel):
    is_demo: bool
    corrections: list[CorrectionRow]


@router.get("/corrections", response_model=TrackerOut)
def tracker(ctx: TenantContext = Depends(require(Cap.VIEW_RECOVERY)), session: Session = Depends(get_session)):
    """Recovery tracker (FR-37): prepared → billed → cash, per correction."""
    rows = []
    for c in session.scalars(scoped(Correction, ctx).order_by(Correction.created_at.desc())):
        f = session.get(Finding, c.finding_id)
        t = service.totals(session, c)
        invoices = session.scalars(select(Invoice.number).where(Invoice.id.in_(c.matched_invoice_ids or []))).all() \
            if c.matched_invoice_ids else []
        events = session.scalars(select(RecoveryEvent).where(RecoveryEvent.correction_id == c.id)
                                 .order_by(RecoveryEvent.occurred_on)).all()
        rows.append(CorrectionRow(
            id=c.id, reference=c.reference, kind=c.kind, status=c.status, amount=c.amount, currency=c.currency,
            finding_id=c.finding_id, finding_status=f.status, check_type=f.check_type,  # type: ignore[union-attr]
            customer_name=((f.evidence or {}).get("customer") or {}).get("name"),  # type: ignore[union-attr]
            invoice_numbers=list(invoices), billed=t.billed, cash_received=t.cash_received,
            cash_recovered=t.cash_recovered,
            events=[RecoveryEventOut(kind=e.kind, amount=e.amount, source_entity=e.source_entity,
                                     occurred_on=e.occurred_on.isoformat()) for e in events],
            created_at=c.created_at,
        ))
    org = session.get(Organization, ctx.org_id)
    return TrackerOut(is_demo=bool(org and org.is_demo), corrections=rows)


class SimulateIn(BaseModel):
    stage: Literal["billing", "payment"]


@router.post("/corrections/{correction_id}/simulate", response_model=TrackerOut)
def simulate(correction_id: uuid.UUID, data: SimulateIn,
             ctx: TenantContext = Depends(require_any(Cap.EXPORT_CORRECTIONS, Cap.MANAGE_DATA)),
             session: Session = Depends(get_session)):
    """DEMO orgs only: stand in for the customer's billing system (decision 0006 D-3)."""
    c = get_scoped(session, Correction, correction_id, ctx)
    demo_simulation.simulate(session, ctx, c, data.stage)
    session.commit()
    return tracker(ctx, session)

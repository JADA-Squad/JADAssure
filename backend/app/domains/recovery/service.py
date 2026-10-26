"""Recovery tracking from prepared correction to billed to cash (BE-023, FR-30, GR-04, GR-11).

Billed: an imported invoice whose `correction_reference` equals the correction's reference. Each
of its lines becomes a `billed` recovery event (net of tax).
Cash: only payment allocations to those invoices, each a `cash` recovery event. Cash recovered
for a correction is capped at the correction amount, so tax or overpayment never inflate it
(GR-04). Recovery events are unique per (correction, kind, source record), so re-importing the
same files never double counts (GR-11).
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.models import Job
from app.domains.audit import service as audit
from app.domains.cases import workflow
from app.domains.cases.models import Correction
from app.domains.ingestion.models import Invoice, InvoiceLine, Payment, PaymentAllocation
from app.domains.recovery.models import RecoveryEvent
from app.domains.rules.models import Finding

RECONCILE_JOB = "recovery_reconcile"
ZERO = Decimal("0")


@dataclass(frozen=True)
class CorrectionTotals:
    billed: Decimal
    cash_received: Decimal
    cash_recovered: Decimal  # min(cash received, correction amount): the only "recovered" figure


def totals(session: Session, c: Correction) -> CorrectionTotals:
    events = session.scalars(select(RecoveryEvent).where(RecoveryEvent.correction_id == c.id)).all()
    billed = sum((e.amount for e in events if e.kind == "billed"), ZERO)
    cash = sum((e.amount for e in events if e.kind == "cash"), ZERO)
    return CorrectionTotals(billed=billed, cash_received=cash, cash_recovered=min(cash, c.amount))


def _record(session: Session, c: Correction, kind: str, amount: Decimal, entity: str, entity_id: uuid.UUID,
            on: date) -> bool:
    """Insert one recovery event; returns False if it was already recorded (idempotent)."""
    stmt = insert(RecoveryEvent).values(
        id=uuid.uuid4(), org_id=c.org_id, correction_id=c.id, kind=kind, amount=amount, source_entity=entity,
        source_entity_id=entity_id, occurred_on=on,
    ).on_conflict_do_nothing(constraint="uq_recovery_event_source")
    return session.execute(stmt).rowcount > 0  # type: ignore[attr-defined]


def reconcile(session: Session, org_id: uuid.UUID) -> dict[str, int]:
    """Match every open correction of the org against imported invoices and payments."""
    stats = {"billed_events": 0, "cash_events": 0, "moved_to_billed": 0, "moved_to_recovered": 0}
    open_corrections = session.scalars(
        select(Correction).where(Correction.org_id == org_id, Correction.status != "paid").with_for_update()
    ).all()
    for c in open_corrections:
        invoices = session.scalars(select(Invoice).where(Invoice.org_id == org_id,
                                                         Invoice.correction_reference == c.reference)).all()
        if not invoices:
            continue
        inv_ids = [i.id for i in invoices]
        inv_dates = {i.id: i.invoice_date for i in invoices}
        for line in session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id.in_(inv_ids))):
            stats["billed_events"] += _record(session, c, "billed", line.net_amount, "invoice_line", line.id,
                                              inv_dates[line.invoice_id])
        allocations = session.execute(
            select(PaymentAllocation, Payment.payment_date)
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(PaymentAllocation.org_id == org_id, PaymentAllocation.invoice_id.in_(inv_ids))
        ).all()
        for alloc, paid_on in allocations:
            stats["cash_events"] += _record(session, c, "cash", alloc.amount, "payment_allocation", alloc.id, paid_on)
        session.flush()

        t = totals(session, c)
        c.matched_invoice_ids = inv_ids
        new_status = ("paid" if t.cash_received >= c.amount else "partially_paid" if t.cash_received > 0
                      else "billed" if t.billed > 0 else "prepared")
        if new_status != c.status:
            audit.record(session, org_id=org_id, actor_id=None, action="correction.status_changed",
                         entity="correction", entity_id=c.id,
                         payload={"from": c.status, "to": new_status, "billed": str(t.billed),
                                  "cash_recovered": str(t.cash_recovered)})
            c.status = new_status

        f = session.scalar(select(Finding).where(Finding.id == c.finding_id).with_for_update())
        if f is None or f.status == "closed_no_recovery":
            continue  # written off: tracked on the correction, but the decision stands
        if f.status == "approved" and t.billed > 0:
            workflow.system_transition(session, f, "billed", f"Corrected invoice with reference {c.reference} imported",
                                       {"billed": str(t.billed)})
            stats["moved_to_billed"] += 1
        if f.status == "billed" and t.cash_received >= c.amount:
            workflow.system_transition(session, f, "recovered", f"Payment received against {c.reference}",
                                       {"cash_recovered": str(t.cash_recovered)})
            stats["moved_to_recovered"] += 1
    return stats


def request_reconcile(session: Session, org_id: uuid.UUID) -> None:
    """Queue one reconcile per org (skipped if one is already waiting)."""
    pending = session.scalar(select(Job.id).where(Job.org_id == org_id, Job.kind == RECONCILE_JOB,
                                                  Job.status == "queued").limit(1))
    if pending is None:
        jobs.enqueue(session, kind=RECONCILE_JOB, org_id=org_id, payload={})


def _handler(session: Session, job: Job) -> None:
    reconcile(session, job.org_id)  # type: ignore[arg-type]


jobs.register(RECONCILE_JOB)(_handler)

"""DEMO-only simulation of the customer's billing system (decision 0006 D-3, scenario 6).

In real use, finance raises the prepared correction in their billing system and the resulting
invoice and payment come back through an import. In DEMO orgs this module writes those two
imports itself: CSVs in the canonical template columns, committed through the normal ingestion
path into a labelled DEMO source. Matching, recovery and cash rules are therefore exercised for
real. Refused for any org that isn't flagged is_demo (GR-14).
"""

import csv
import io
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.domains.access.models import Organization
from app.domains.cases.models import Correction
from app.domains.ingestion import service as ingestion
from app.domains.ingestion.models import DataSource
from app.domains.ingestion.registry import RECORDS
from app.domains.recovery import service as recovery
from app.domains.rules.models import Finding

SOURCE_NAME = "Billing simulation (DEMO)"


def _csv(record_type: str, rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[f.name for f in RECORDS[record_type].fields], lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: "" if v is None else v for k, v in r.items()})
    return buf.getvalue().encode("utf-8")


def _source(session: Session, ctx: TenantContext) -> DataSource:
    src = session.scalar(select(DataSource).where(DataSource.org_id == ctx.org_id, DataSource.name == SOURCE_NAME))
    return src or ingestion.create_source(session, ctx, name=SOURCE_NAME, is_demo=True)


def _load(session: Session, ctx: TenantContext, source: DataSource, record_type: str, rows: list[dict]) -> None:
    batch = ingestion.start_import(session, ctx, source, record_type, f"simulated-{record_type}.csv",
                                   _csv(record_type, rows))
    batch.status = "running"
    ingestion.commit_batch(session, batch)
    if batch.counts.get("rejected"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Simulated {record_type} rows were rejected")


def simulate(session: Session, ctx: TenantContext, c: Correction, stage: str) -> None:
    org = session.get(Organization, ctx.org_id)
    if org is None or not org.is_demo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Billing simulation is only available in DEMO organizations")
    f = session.get(Finding, c.finding_id)
    assert f is not None
    customer = (f.evidence.get("customer") or {}).get("source_record_id")
    agreement = (f.evidence.get("agreement") or {}).get("source_record_id")
    source = _source(session, ctx)
    invoice_id = f"SIM-{c.reference}"
    today = date.today()

    if stage == "billing":
        if c.status != "prepared":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Correction is already {c.status}")
        _load(session, ctx, source, "invoice", [{
            "invoice_id": invoice_id, "customer_id": customer, "number": f"{c.reference}-INV", "invoice_date": today,
            "currency": c.currency, "status": "posted", "correction_reference": c.reference,
        }])
        _load(session, ctx, source, "invoice_line", [{
            "line_id": f"{invoice_id}-L{n}", "invoice_id": invoice_id, "agreement_id": agreement,
            "item_code": line.get("item_code") or "ADJUSTMENT", "quantity": line.get("quantity") or "1",
            "unit_price": line.get("unit_price"), "net_amount": line.get("amount"), "tax_amount": "0",
            # The supplementary invoice covers the original service period.
            "service_period_start": f.period_start, "service_period_end": f.period_end,
        } for n, line in enumerate(c.lines, start=1)])
    elif stage == "payment":
        if c.status not in ("billed", "partially_paid"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Simulate billing first: the correction isn't invoiced yet")
        billed = recovery.totals(session, c).billed
        _load(session, ctx, source, "payment", [{
            "payment_id": f"{invoice_id}-P", "customer_id": customer, "amount": billed, "currency": c.currency,
            "payment_date": today,
        }])
        _load(session, ctx, source, "payment_allocation", [{
            "allocation_id": f"{invoice_id}-P-A1", "payment_id": f"{invoice_id}-P", "invoice_id": invoice_id,
            "amount": billed,
        }])
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "stage must be 'billing' or 'payment'")
    recovery.reconcile(session, ctx.org_id)

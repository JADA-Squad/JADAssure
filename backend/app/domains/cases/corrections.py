"""Prepared corrections (BE-022, FR-29, GR-01).

Approval creates exactly one correction with a unique reference. Corrections are prepared and
exported for people to carry out in their billing system. There is no code path that sends one
anywhere (GR-01). The reference must appear on the corrected invoice so recovery can match it
(BE-023).
"""

import csv
import io
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext
from app.domains.access.models import Organization
from app.domains.audit import service as audit
from app.domains.cases.models import Correction
from app.domains.ingestion.parsing import csv_safe
from app.domains.rules.models import Finding


def _lines(f: Finding) -> tuple[str, list[dict[str, Any]]]:
    calc = f.calculation or {}
    inputs = calc.get("inputs", {})
    ev = f.evidence or {}
    if f.family == "unbilled":
        return "supplementary_invoice", [{
            "description": f"Unbilled {f.item_code} delivered {f.period_start} to {f.period_end}",
            "item_code": f.item_code, "quantity": inputs.get("unbilled"),
            "unit_price": inputs.get("net_unit_price"), "amount": str(f.value),
        }]
    if f.family == "price":
        billed = (ev.get("billed") or [{}])[0]
        return "supplementary_invoice", [{
            "description": f"Price adjustment for invoice {billed.get('invoice_number')} ({f.check_type.replace('_', ' ')})",
            "item_code": f.item_code, "quantity": "1", "unit_price": str(f.value), "amount": str(f.value),
        }]
    credit = ev.get("credit") or {}
    return "credit_reversal", [{
        "description": f"Reversal of credit {credit.get('source_record_id')} outside policy",
        "item_code": None, "quantity": "1", "unit_price": str(f.value), "amount": str(f.value),
    }]


def prepare(session: Session, ctx: TenantContext, f: Finding) -> Correction:
    existing = session.scalar(select(Correction).where(Correction.finding_id == f.id))
    if existing is not None:
        return existing  # unique per finding (also enforced by the database)
    org = session.get(Organization, ctx.org_id)
    assert org is not None
    # Sequential, human-quotable references per org: JA-<org code>-0001.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"correction-ref:{org.id}"})
    seq = (session.scalar(select(func.count()).select_from(Correction).where(Correction.org_id == org.id)) or 0) + 1
    kind, lines = _lines(f)
    c = Correction(org_id=org.id, finding_id=f.id, reference=f"JA-{org.short_code}-{seq:04d}", kind=kind,
                   lines=lines, amount=f.value, currency=f.currency, status="prepared", matched_invoice_ids=[])
    session.add(c)
    session.flush()
    audit.record(session, org_id=org.id, actor_id=ctx.user_id, action="correction.prepared", entity="correction",
                 entity_id=c.id, payload={"reference": c.reference, "amount": str(c.amount), "currency": c.currency})
    return c


def export_dict(c: Correction, f: Finding) -> dict[str, Any]:
    customer = (f.evidence or {}).get("customer") or {}
    return {
        "reference": c.reference, "kind": c.kind, "status": c.status, "currency": c.currency,
        "amount": str(c.amount), "customer": {"name": customer.get("name"),
                                              "source_record_id": customer.get("source_record_id")},
        "finding_id": str(f.id), "check_type": f.check_type, "lines": c.lines,
        "instructions": (f"Raise this {c.kind.replace('_', ' ')} in your billing system and quote reference "
                         f"{c.reference} on it, so JADAssure can match the invoice and its payment."),
    }


def export_csv(c: Correction, f: Finding) -> str:
    d = export_dict(c, f)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["reference", "kind", "customer_source_id", "customer_name", "currency", "line", "description",
                "item_code", "quantity", "unit_price", "amount"])
    for n, line in enumerate(c.lines, start=1):
        w.writerow([csv_safe(str(x)) if x is not None else "" for x in (
            d["reference"], d["kind"], d["customer"]["source_record_id"], d["customer"]["name"], d["currency"], n,
            line.get("description"), line.get("item_code"), line.get("quantity"), line.get("unit_price"),
            line.get("amount"))])
    return buf.getvalue()


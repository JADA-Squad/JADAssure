"""JSON snapshots of source records for finding evidence (GR-16). Snapshots are frozen with the finding."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.domains.contracts.models import Agreement, CommercialTerm
from app.domains.contracts.terms import TermBook
from app.domains.ingestion.models import BillableEvent, Credit, Customer, Invoice, InvoiceLine


def s(value: Any) -> Any:
    if isinstance(value, Decimal):
        text = format(value.normalize(), "f")
        return "0" if text in ("-0", "") else text
    if isinstance(value, (date, uuid.UUID)):
        return str(value)
    return value


def customer(c: Customer) -> dict[str, Any]:
    return {"id": s(c.id), "source_record_id": c.source_record_id, "name": c.name}


def agreement(a: Agreement | None) -> dict[str, Any] | None:
    if a is None:
        return None
    return {"id": s(a.id), "source_record_id": a.source_record_id, "title": a.title,
            "billing_frequency": a.billing_frequency, "currency": a.currency}


def term(t: CommercialTerm, book: TermBook) -> dict[str, Any]:
    return {
        "id": s(t.id), "source_record_id": t.source_record_id, "term_type": t.term_type, "item_code": t.item_code,
        "value": s(t.value), "unit": t.unit, "currency": t.currency, "effective_from": s(t.effective_from),
        "effective_to": s(t.effective_to), "approval_ref": t.approval_ref, "params": t.params,
        "version_no": book.version_no.get(t.agreement_version_id), "origin": t.origin,
        "source_passage": t.source_passage,
    }


def event(e: BillableEvent) -> dict[str, Any]:
    return {"id": s(e.id), "source_record_id": e.source_record_id, "item_code": e.item_code,
            "quantity": s(e.quantity), "unit": e.unit, "service_date": s(e.service_date),
            "billing_date": s(e.billing_date), "currency": e.currency}


def line(ln: InvoiceLine, inv: Invoice) -> dict[str, Any]:
    return {"id": s(ln.id), "source_record_id": ln.source_record_id, "invoice_id": s(inv.id),
            "invoice_number": inv.number, "invoice_date": s(inv.invoice_date), "item_code": ln.item_code,
            "quantity": s(ln.quantity), "unit_price": s(ln.unit_price), "discount_pct": s(ln.discount_pct),
            "net_amount": s(ln.net_amount), "tax_amount": s(ln.tax_amount), "currency": inv.currency,
            "service_period_start": s(ln.service_period_start), "service_period_end": s(ln.service_period_end)}


def credit(c: Credit, inv: Invoice | None) -> dict[str, Any]:
    return {"id": s(c.id), "source_record_id": c.source_record_id, "amount": s(c.amount), "currency": c.currency,
            "reason_code": c.reason_code, "approval_ref": c.approval_ref, "credit_date": s(c.credit_date),
            "invoice_number": inv.number if inv else None}

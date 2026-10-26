"""Delivered-versus-billed matcher (BE-013, FR-16).

Billable events and invoice lines are grouped into buckets keyed by
(customer, agreement, item, billing period, currency) and their quantities summed. Split
invoices, aggregated lines and partial delivery therefore need no special cases: only the totals
per bucket are compared. All arithmetic is Decimal (GR-09).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.contracts.models import Agreement
from app.domains.contracts.terms import TermBook
from app.domains.ingestion.models import BillableEvent, Credit, Customer, Invoice, InvoiceLine
from app.domains.matching.periods import period_for

ZERO = Decimal("0")


@dataclass
class OrgData:
    customers: dict[uuid.UUID, Customer]
    agreements: dict[uuid.UUID, Agreement]
    events: list[BillableEvent]
    invoices: dict[uuid.UUID, Invoice]
    lines: list[InvoiceLine]
    credits: list[Credit]
    agreements_by_customer: dict[uuid.UUID, list[Agreement]] = field(default_factory=dict)
    lines_by_invoice: dict[uuid.UUID, list[InvoiceLine]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        by_customer: dict[uuid.UUID, list[Agreement]] = defaultdict(list)
        for a in self.agreements.values():
            by_customer[a.customer_id].append(a)
        self.agreements_by_customer = dict(by_customer)
        by_invoice: dict[uuid.UUID, list[InvoiceLine]] = defaultdict(list)
        for line in self.lines:
            by_invoice[line.invoice_id].append(line)
        self.lines_by_invoice = dict(by_invoice)

    @classmethod
    def load(cls, session: Session, org_id: uuid.UUID) -> "OrgData":
        def all_of(model):
            return list(session.scalars(select(model).where(model.org_id == org_id)))

        return cls(
            customers={c.id: c for c in all_of(Customer)},
            agreements={a.id: a for a in all_of(Agreement)},
            events=all_of(BillableEvent),
            invoices={i.id: i for i in all_of(Invoice)},
            lines=all_of(InvoiceLine),
            credits=all_of(Credit),
        )


@dataclass(frozen=True)
class AgreementMatch:
    agreement_id: uuid.UUID | None
    inferred: bool


def match_agreement(data: OrgData, book: TermBook, customer_id: uuid.UUID, explicit: uuid.UUID | None,
                    item_code: str, on: date) -> AgreementMatch:
    """Explicit reference if it belongs to the customer; otherwise the single agreement of that customer
    with a confirmed rate for the item on the date. Ambiguous or none → unmatched."""
    if explicit is not None and explicit in data.agreements and data.agreements[explicit].customer_id == customer_id:
        return AgreementMatch(explicit, False)
    candidates = [a.id for a in data.agreements_by_customer.get(customer_id, [])
                  if book.first(a.id, on, "rate", item_code) is not None]
    return AgreementMatch(candidates[0], True) if len(candidates) == 1 else AgreementMatch(None, False)


def line_service_date(line: InvoiceLine, invoice: Invoice) -> date:
    return line.service_period_start or invoice.invoice_date


BucketKey = tuple[uuid.UUID, uuid.UUID | None, str, date, str]


@dataclass
class Bucket:
    customer_id: uuid.UUID
    agreement_id: uuid.UUID | None
    item_code: str
    period_start: date
    period_end: date
    currency: str
    delivered: Decimal = ZERO
    billed: Decimal = ZERO
    events: list[BillableEvent] = field(default_factory=list)
    lines: list[InvoiceLine] = field(default_factory=list)
    inferred: bool = False
    billing_due: date | None = None

    @property
    def key(self) -> BucketKey:
        return (self.customer_id, self.agreement_id, self.item_code, self.period_start, self.currency)

    @property
    def unbilled_quantity(self) -> Decimal:
        return self.delivered - self.billed

    def anchor(self) -> str:
        """Stable identity of this bucket across runs (decision 0001 D-8)."""
        return "|".join(str(p) for p in self.key)


def _frequency(data: OrgData, agreement_id: uuid.UUID | None) -> str:
    return data.agreements[agreement_id].billing_frequency if agreement_id else "monthly"


def build_buckets(data: OrgData, book: TermBook) -> dict[BucketKey, Bucket]:
    buckets: dict[BucketKey, Bucket] = {}

    def bucket_for(customer_id, match: AgreementMatch, item_code, on, currency) -> Bucket:
        start, end = period_for(_frequency(data, match.agreement_id), on)
        key = (customer_id, match.agreement_id, item_code, start, currency)
        if key not in buckets:
            buckets[key] = Bucket(customer_id, match.agreement_id, item_code, start, end, currency)
        b = buckets[key]
        b.inferred = b.inferred or match.inferred
        return b

    for e in data.events:
        match = match_agreement(data, book, e.customer_id, e.agreement_id, e.item_code, e.service_date)
        b = bucket_for(e.customer_id, match, e.item_code, e.service_date, e.currency)
        b.delivered += e.quantity
        b.events.append(e)
        due = e.billing_date or b.period_end
        b.billing_due = max(b.billing_due, due) if b.billing_due else due

    for line in data.lines:
        invoice = data.invoices[line.invoice_id]
        on = line_service_date(line, invoice)
        match = match_agreement(data, book, invoice.customer_id, line.agreement_id, line.item_code, on)
        b = bucket_for(invoice.customer_id, match, line.item_code, on, invoice.currency)
        b.billed += line.quantity
        b.lines.append(line)

    return buckets

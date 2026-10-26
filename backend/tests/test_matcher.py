"""BE-013: matcher buckets across billing frequencies, split/aggregated invoices and partial delivery."""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.domains.contracts.models import Agreement, AgreementVersion, CommercialTerm
from app.domains.contracts.terms import TermBook, resolve_terms
from app.domains.ingestion.models import BillableEvent, Customer, Invoice, InvoiceLine
from app.domains.matching.matcher import OrgData, build_buckets, match_agreement
from app.domains.matching.periods import period_for
from app.domains.matching.pricing import expected_price

ORG = uuid.uuid4()
D = Decimal


def _id():
    return uuid.uuid4()


class World:
    """Builds unsaved model objects; the matcher is pure logic over them."""

    def __init__(self):
        self.customer = Customer(id=_id(), org_id=ORG, name="C", currency="USD")
        self.agreements: dict = {}
        self.book = TermBook()
        self.events: list = []
        self.invoices: dict = {}
        self.lines: list = []

    def agreement(self, frequency, rates: dict[str, str], customer=None):
        a = Agreement(id=_id(), org_id=ORG, customer_id=(customer or self.customer).id, title="A",
                      start_date=date(2026, 1, 1), billing_frequency=frequency, currency="USD")
        v = AgreementVersion(id=_id(), org_id=ORG, agreement_id=a.id, version_no=1, effective_from=date(2026, 1, 1))
        self.agreements[a.id] = a
        self.book.versions[a.id] = [v]
        self.book.terms[v.id] = [
            CommercialTerm(id=_id(), org_id=ORG, agreement_version_id=v.id, item_code=item, term_type="rate",
                           value=D(r), currency="USD", effective_from=date(2026, 1, 1), status="confirmed")
            for item, r in rates.items()
        ]
        return a

    def event(self, agreement, item, qty, on, explicit=True):
        self.events.append(BillableEvent(id=_id(), org_id=ORG, customer_id=self.customer.id,
                                         agreement_id=agreement.id if explicit else None, item_code=item,
                                         quantity=D(qty), service_date=on, billing_date=on, currency="USD"))

    def line(self, agreement, item, qty, on, invoice_on=None, explicit=True):
        inv = Invoice(id=_id(), org_id=ORG, customer_id=self.customer.id, number="X",
                      invoice_date=invoice_on or on, currency="USD")
        self.invoices[inv.id] = inv
        self.lines.append(InvoiceLine(id=_id(), org_id=ORG, invoice_id=inv.id,
                                      agreement_id=agreement.id if explicit else None, item_code=item,
                                      quantity=D(qty), unit_price=D("1"), discount_pct=D("0"), net_amount=D(qty),
                                      tax_amount=D("0"), service_period_start=on, service_period_end=on))

    def buckets(self):
        data = OrgData(customers={self.customer.id: self.customer}, agreements=self.agreements, events=self.events,
                       invoices=self.invoices, lines=self.lines, credits=[])
        return list(build_buckets(data, self.book).values()), data


@pytest.mark.parametrize("frequency,on,expected", [
    ("monthly", date(2026, 4, 17), (date(2026, 4, 1), date(2026, 4, 30))),
    ("monthly", date(2026, 2, 3), (date(2026, 2, 1), date(2026, 2, 28))),
    ("quarterly", date(2026, 5, 9), (date(2026, 4, 1), date(2026, 6, 30))),
    ("annual", date(2026, 11, 2), (date(2026, 1, 1), date(2026, 12, 31))),
    ("per_event", date(2026, 6, 10), (date(2026, 6, 10), date(2026, 6, 10))),
    ("milestone", date(2026, 3, 31), (date(2026, 3, 31), date(2026, 3, 31))),
])
def test_periods(frequency, on, expected):
    assert period_for(frequency, on) == expected


def test_monthly_partial_billing_sums_events():
    w = World()
    a = w.agreement("monthly", {"HOURS": "180"})
    w.event(a, "HOURS", "40", date(2026, 4, 15))
    w.event(a, "HOURS", "12", date(2026, 4, 28))
    w.line(a, "HOURS", "40", date(2026, 4, 1), invoice_on=date(2026, 5, 3))
    [b], _ = w.buckets()
    assert (b.delivered, b.billed, b.unbilled_quantity) == (D("52"), D("40"), D("12"))
    assert b.billing_due == date(2026, 4, 28) and len(b.events) == 2


def test_split_invoice_matches_one_delivery():
    w = World()
    a = w.agreement("per_event", {"W": "30"})
    w.event(a, "W", "100", date(2026, 6, 10))
    w.line(a, "W", "60", date(2026, 6, 10))
    w.line(a, "W", "40", date(2026, 6, 10))
    [b], _ = w.buckets()
    assert b.unbilled_quantity == 0 and len(b.lines) == 2


def test_aggregated_line_matches_several_deliveries():
    w = World()
    a = w.agreement("per_event", {"W": "12.5"})
    w.event(a, "W", "50", date(2026, 7, 8))
    w.event(a, "W", "50.5", date(2026, 7, 8))
    w.line(a, "W", "100.5", date(2026, 7, 8))
    [b], _ = w.buckets()
    assert b.unbilled_quantity == D("0") and isinstance(b.delivered, Decimal)


def test_quarterly_groups_three_months():
    w = World()
    a = w.agreement("quarterly", {"SVC": "10"})
    for m in (4, 5, 6):
        w.event(a, "SVC", "10", date(2026, m, 5))
    w.line(a, "SVC", "20", date(2026, 4, 1))
    [b], _ = w.buckets()
    assert (b.period_start, b.period_end, b.unbilled_quantity) == (date(2026, 4, 1), date(2026, 6, 30), D("10"))


def test_different_periods_do_not_offset():
    w = World()
    a = w.agreement("monthly", {"SEAT": "45"})
    w.event(a, "SEAT", "10", date(2026, 3, 1))
    w.line(a, "SEAT", "10", date(2026, 4, 1))
    buckets, _ = w.buckets()
    assert sorted(b.unbilled_quantity for b in buckets) == [D("-10"), D("10")]


def test_agreement_inferred_when_unambiguous_and_flagged():
    w = World()
    a = w.agreement("monthly", {"SEAT": "45"})
    w.agreement("monthly", {"OTHER": "1"})
    w.event(a, "SEAT", "5", date(2026, 3, 1), explicit=False)
    w.line(a, "SEAT", "5", date(2026, 3, 1), explicit=False)
    [b], data = w.buckets()
    assert b.agreement_id == a.id and b.inferred and b.unbilled_quantity == 0


def test_ambiguous_agreement_is_left_unmatched():
    w = World()
    w.agreement("monthly", {"SEAT": "45"})
    w.agreement("monthly", {"SEAT": "50"})
    _, data = w.buckets()
    m = match_agreement(data, w.book, w.customer.id, None, "SEAT", date(2026, 3, 1))
    assert m.agreement_id is None


def test_explicit_agreement_of_another_customer_is_not_trusted():
    w = World()
    other = Customer(id=_id(), org_id=ORG, name="Other", currency="USD")
    foreign = w.agreement("monthly", {"SEAT": "45"}, customer=other)
    _, data = w.buckets()
    m = match_agreement(data, w.book, w.customer.id, foreign.id, "SEAT", date(2026, 3, 1))
    assert m.agreement_id is None


def test_expected_price_applies_escalation_and_caps_discount():
    w = World()
    a = w.agreement("monthly", {"SEAT": "45"})
    v_id = w.book.versions[a.id][0].id
    w.book.terms[v_id] += [
        CommercialTerm(id=_id(), org_id=ORG, agreement_version_id=v_id, item_code="SEAT", term_type="escalation",
                       value=D("5"), unit="pct", effective_from=date(2026, 7, 1), status="confirmed"),
        CommercialTerm(id=_id(), org_id=ORG, agreement_version_id=v_id, item_code="SEAT", term_type="discount",
                       value=D("10"), unit="pct", effective_from=date(2026, 1, 1), effective_to=date(2026, 3, 31),
                       status="confirmed"),
    ]
    june = expected_price(w.book, a.id, "SEAT", date(2026, 6, 1))
    july = expected_price(w.book, a.id, "SEAT", date(2026, 7, 1))
    feb = expected_price(w.book, a.id, "SEAT", date(2026, 2, 1))
    assert (june.list_price, june.escalation_term) == (D("45.000000"), None)
    assert july.list_price == D("47.250000") and july.base_rate == D("45.000000")
    assert feb.net_unit(D("10")) == D("40.500000") and feb.net_unit(D("25")) == D("40.500000")
    assert june.net_unit(D("10")) == D("45.000000")  # no discount authorized in June
    assert expected_price(w.book, a.id, "NOPE", date(2026, 2, 1)) is None


def test_term_book_matches_resolve_terms(client, session):
    """The in-memory TermBook must answer exactly like the database query (GR-03)."""
    from tests.test_terms import AGREEMENT, TERMS, VERSIONS
    from tests.factories import signup
    from tests.ingest_helpers import CUSTOMERS, create_source, load
    from sqlalchemy import select

    admin = signup(client)
    src = create_source(client, admin)
    for record_type, text in (("customer", CUSTOMERS), ("agreement", AGREEMENT), ("agreement_version", VERSIONS),
                              ("commercial_term", TERMS)):
        load(client, admin, src, record_type, text)
    agreement = session.scalar(select(Agreement))
    book = TermBook.load(session, agreement.org_id)
    for on in (date(2025, 12, 31), date(2026, 3, 31), date(2026, 4, 1), date(2026, 7, 1), date(2027, 1, 1)):
        for item in (None, "SEAT"):
            db = [t.id for t in resolve_terms(session, agreement.org_id, agreement.id, on, item_code=item)]
            mem = [t.id for t in book.terms_on(agreement.id, on, item_code=item)]
            assert sorted(db) == sorted(mem), on

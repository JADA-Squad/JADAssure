"""BE-011: effective-dated term resolution across amendments; only confirmed terms (FR-12, GR-03)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.contracts.models import Agreement, AgreementVersion, CommercialTerm
from app.domains.contracts.terms import resolve_terms
from tests.factories import add_user, signup
from tests.ingest_helpers import CUSTOMERS, create_source, load

AGREEMENT = "agreement_id,customer_id,title,start_date,billing_frequency,currency\nA1,C1,Seats,2026-01-01,monthly,USD\n"
VERSIONS = (
    "version_id,agreement_id,version_no,effective_from,effective_to,reason\n"
    "V1,A1,1,2026-01-01,2026-06-30,Original\n"
    "V2,A1,2,2026-07-01,,Renewal with increase\n"
)
TERMS = (
    "term_id,version_id,item_code,term_type,value,unit,currency,effective_from,effective_to\n"
    "T1,V1,SEAT,rate,45,seat,USD,2026-01-01,\n"
    "T2,V1,SEAT,discount,10,pct,,2026-01-01,2026-03-31\n"
    "T3,V1,,credit_policy,500,,USD,2026-01-01,\n"
    "T4,V2,SEAT,rate,47.25,seat,USD,2026-07-01,\n"
)


@pytest.fixture
def seeded(client, session):
    admin = signup(client)
    src = create_source(client, admin)
    for record_type, text in (("customer", CUSTOMERS), ("agreement", AGREEMENT), ("agreement_version", VERSIONS),
                              ("commercial_term", TERMS)):
        load(client, admin, src, record_type, text)
    agreement = session.scalar(select(Agreement))
    v2 = session.scalar(select(AgreementVersion).where(AgreementVersion.version_no == 2))
    # A proposed (e.g. AI-extracted) and a rejected term that must never resolve (GR-03).
    for status_, value in (("proposed", "99"), ("rejected", "1")):
        session.add(CommercialTerm(
            org_id=agreement.org_id, agreement_version_id=v2.id, item_code="SEAT", term_type="rate",
            value=Decimal(value), effective_from=date(2026, 7, 1), status=status_, origin="extraction",
            ambiguous=status_ == "proposed", params={},
        ))
    session.commit()
    return admin, agreement


def _rates(session, agreement, on):
    return [(t.term_type, t.value) for t in resolve_terms(session, agreement.org_id, agreement.id, on, item_code="SEAT")]


@pytest.mark.parametrize("on,expected", [
    (date(2025, 12, 31), []),  # before the agreement
    (date(2026, 2, 15), [("discount", Decimal("10")), ("rate", Decimal("45")), ("credit_policy", Decimal("500"))]),
    (date(2026, 3, 31), [("discount", Decimal("10")), ("rate", Decimal("45")), ("credit_policy", Decimal("500"))]),
    (date(2026, 4, 1), [("rate", Decimal("45")), ("credit_policy", Decimal("500"))]),  # discount expired
    (date(2026, 6, 30), [("rate", Decimal("45")), ("credit_policy", Decimal("500"))]),
    (date(2026, 7, 1), [("rate", Decimal("47.25"))]),  # amendment: only V2's confirmed terms
    (date(2027, 1, 1), [("rate", Decimal("47.25"))]),
])
def test_resolves_terms_by_date_and_amendment(seeded, session, on, expected):
    _, agreement = seeded
    assert sorted(_rates(session, agreement, on)) == sorted(expected)
    # item-specific terms come before agreement-wide ones
    terms = resolve_terms(session, agreement.org_id, agreement.id, on, item_code="SEAT")
    assert [t.item_code is None for t in terms] == sorted(t.item_code is None for t in terms)


def test_non_confirmed_terms_never_resolve(seeded, session):
    _, agreement = seeded
    for on in (date(2026, 7, 1), date(2026, 12, 31)):
        assert all(t.status == "confirmed" for t in resolve_terms(session, agreement.org_id, agreement.id, on))


def test_terms_in_effect_endpoint(seeded, client):
    admin, agreement = seeded
    res = client.get(f"/api/agreements/{agreement.id}/terms?on=2026-08-15&item_code=SEAT", headers=admin.headers)
    assert res.status_code == 200
    assert [(t["term_type"], t["value"]) for t in res.json()] == [("rate", "47.250000")]


def test_agreement_detail_shows_all_terms_with_status(seeded, client):
    admin, agreement = seeded
    analyst = add_user(client, admin, "analyst")
    listing = client.get("/api/agreements", headers=analyst.headers).json()
    assert listing[0]["customer_name"] == "Halcyon Retail"
    assert listing[0]["term_counts"] == {"confirmed": 4, "proposed": 1, "rejected": 1}
    detail = client.get(f"/api/agreements/{agreement.id}", headers=analyst.headers).json()
    assert [v["version_no"] for v in detail["versions"]] == [1, 2]
    assert len(detail["versions"][1]["terms"]) == 3


def test_agreements_are_org_scoped_and_role_checked(seeded, client):
    admin, agreement = seeded
    other = signup(client)
    assert client.get("/api/agreements", headers=other.headers).json() == []
    assert client.get(f"/api/agreements/{agreement.id}", headers=other.headers).status_code == 404
    assert client.get(f"/api/agreements/{agreement.id}/terms?on=2026-08-01",
                      headers=other.headers).status_code == 404
    executive = add_user(client, admin, "executive")
    assert client.get("/api/agreements", headers=executive.headers).status_code == 403

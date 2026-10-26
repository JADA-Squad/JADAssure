"""DATA-001 / FR-42: the same engine finds exactly the planted discrepancies in all three demo datasets (in two demo orgs).

Expected values are the table in demo-data/README.md. Anything extra is a false positive.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.domains.access.models import Organization
from app.seed_demo import main as seed
from tests.engine_helpers import findings, run

AS_OF = date(2026, 10, 26)

EXPECTED = {
    # JM carries the professional-services (Northwind) and subscription (Cirrus) datasets.
    "JM": sorted([
        ("delivered_not_billed", "SENIOR-CONSULT", "2026-04-01", Decimal("2160"), "USD"),
        ("delivered_not_billed", "ANALYST", "2026-06-01", Decimal("960"), "USD"),
        ("incorrect_rate", "PLATFORM-SEAT", "2026-03-01", Decimal("600"), "USD"),
        ("missed_increase", "PLATFORM-SEAT", "2026-07-01", Decimal("270"), "USD"),
        ("missed_increase", "PLATFORM-SEAT", "2026-08-01", Decimal("270"), "USD"),
        ("missed_increase", "PLATFORM-SEAT", "2026-09-01", Decimal("270"), "USD"),
    ]),
    # Beyon carries the distribution (Ridgeline) dataset.
    "Beyon": sorted([
        ("expired_discount", "WIDGET-A", "2026-04-14", Decimal("375"), "USD"),
        ("expired_discount", "WIDGET-A", "2026-05-20", Decimal("187.5"), "USD"),
        ("credit_outside_policy", None, "2026-03-20", Decimal("750"), "USD"),
        ("credit_outside_policy", None, "2026-06-25", Decimal("120"), "USD"),
    ]),
}


def test_demo_datasets_yield_exactly_the_planted_findings(client, session):
    seed([])
    orgs = {o.name: o for o in session.scalars(select(Organization))}
    for name, expected in EXPECTED.items():
        r = run(orgs[name].id, AS_OF)
        assert r.status == "succeeded", (name, r.error)
        got = sorted((f.check_type, f.item_code, f.period_start.isoformat(), f.value.normalize(), f.currency)
                     for f in findings(session, orgs[name].id))
        assert got == [(c, i, p, v.normalize(), ccy) for c, i, p, v, ccy in expected], name
        assert r.stats["duration_ms"] < 30_000  # NFR-04
        assert all(f.confidence == "high" for f in findings(session, orgs[name].id))

    # Missed increases are one finding per line, with incorrect_rate absorbed (FR-23).
    jm = findings(session, orgs["JM"].id)
    assert all(f.also_detected_by == ["incorrect_rate"] for f in jm if f.check_type == "missed_increase")

    # Re-running every org changes nothing (scenario 7 for findings).
    for org in orgs.values():
        again = run(org.id, AS_OF)
        assert again.stats["new"] == 0 and again.stats["refreshed"] == 0

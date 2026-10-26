"""QA-001: the eight acceptance scenarios (requirements §11), end to end through the API on seeded demo data.

    docker compose exec api pytest -m acceptance

Runs as real users would: demo logins, check runs, workflow, the DEMO billing simulation, re-sync.
Also asserts NFR-04 (a full check run over the demo data in under 30 seconds).
"""

import time
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.core import jobs
from app.domains.access.models import Organization
from app.domains.ingestion.models import DataSource
from app.seed_demo import DEMO_PASSWORD, demo_email, main as seed
from tests.doc_helpers import DEMO_CONTRACT
from tests.factories import Actor

pytestmark = pytest.mark.acceptance
D = Decimal


def login(client, role: str, domain: str) -> Actor:
    body = client.post("/api/auth/login", json={"email": demo_email(role, domain), "password": DEMO_PASSWORD}).json()
    return Actor(body["access_token"], body["me"]["user"]["id"], body["me"]["organization"]["id"], role, "")


def run_checks(client, actor: Actor) -> dict:
    """Run checks now (FR-10) and wait for the worker; enforce NFR-04 on the way."""
    started = time.perf_counter()
    assert client.post("/api/check-runs", headers=actor.headers).status_code == 202
    jobs.drain()
    elapsed = time.perf_counter() - started
    run = client.get("/api/check-runs?limit=1", headers=actor.headers).json()[0]
    assert run["status"] == "succeeded", run
    assert elapsed < 30 and run["stats"]["duration_ms"] < 30_000  # NFR-04
    return run


def items(client, actor, **params):
    return client.get("/api/findings", headers=actor.headers, params={"limit": 100, **params}).json()["items"]


def one(found, **match):
    hits = [f for f in found if all(f[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, [(f["check_type"], f["value"], f["period_start"]) for f in found])
    return hits[0]


def act(client, actor, fid, action, body=None):
    r = client.post(f"/api/findings/{fid}/{action}", headers=actor.headers, json=body or {})
    assert r.status_code == 200, (action, r.text)
    return r.json()


def outcomes(client, actor):
    body = client.get("/api/reports/outcomes", headers=actor.headers).json()
    return {c["currency"]: {k: D(v) for k, v in c.items() if k != "currency"} for c in body["currencies"]}, body


def snapshot(session) -> dict[str, int]:
    tables = ("customer", "agreement", "billable_event", "invoice", "invoice_line", "credit", "payment",
              "payment_allocation", "commercial_term", "finding", "correction", "recovery_event")
    return {t: session.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables}


def test_eight_acceptance_scenarios(client, session):
    seed([])
    analyst, approver, commercial, executive = (login(client, r, "jm.com")
                                                for r in ("analyst", "approver", "commercial", "executive"))
    b_analyst, b_approver = login(client, "analyst", "beyon.com"), login(client, "approver", "beyon.com")
    run_checks(client, analyst)
    run_checks(client, b_analyst)
    jm, beyon = items(client, analyst), items(client, b_analyst)

    # 1. A delivered item omitted from billing.
    unbilled = one(jm, check_type="delivered_not_billed", item_code="SENIOR-CONSULT")
    assert unbilled["value"] == "2160.0000" and unbilled["period_start"] == "2026-04-01"

    # 2. An invoice using the wrong contracted rate.
    wrong_rate = one(jm, check_type="incorrect_rate", period_start="2026-03-01")
    assert wrong_rate["value"] == "600.0000"

    # 3. A discount applied after its expiry date.
    expired = one(beyon, check_type="expired_discount", period_start="2026-04-14")
    assert expired["value"] == "375.0000"

    # 4. An ambiguous contract term held for human confirmation.
    orchard = next(a for a in client.get("/api/agreements", headers=commercial.headers).json()
                   if a["title"] == "Data strategy SOW")
    r = client.post(f"/api/agreements/{orchard['id']}/documents", headers=commercial.headers,
                    files={"file": ("orchard-sow-amendment-1.txt", DEMO_CONTRACT.read_bytes(), "text/plain")})
    assert r.status_code == 201
    jobs.drain()
    proposed = [t for t in client.get("/api/terms?status=proposed", headers=commercial.headers).json()
                if t["agreement_id"] == orchard["id"]]
    held = [t for t in proposed if t["ambiguous"]]
    assert len(proposed) == 3 and len(held) == 2
    assert any("subject to a further agreement" in (t["ambiguity_reason"] or "") for t in held)
    run_checks(client, analyst)
    assert not [f for f in items(client, analyst) if f["agreement_title"] == "Data strategy SOW"]  # held = no effect
    senior = next(t for t in proposed if t["item_code"] == "SENIOR-CONSULT" and not t["ambiguous"])
    assert client.post(f"/api/terms/{senior['id']}/confirm", headers=commercial.headers, json={}).status_code == 200
    run_checks(client, analyst)
    orchard_found = sorted(f["value"] for f in items(client, analyst) if f["agreement_title"] == "Data strategy SOW")
    assert orchard_found == ["240.0000", "300.0000"]
    still_held = client.get("/api/terms?status=proposed", headers=commercial.headers).json()
    assert {t["id"] for t in still_held} >= {t["id"] for t in held}

    # 5. A finding rejected by a reviewer is not counted as recovered revenue.
    before, _ = outcomes(client, executive)
    workshop = one(items(client, analyst), check_type="delivered_not_billed", item_code="ANALYST")
    act(client, analyst, workshop["id"], "reject", {"note": "Non-billable workshop prep agreed with Halcyon"})
    after, body = outcomes(client, executive)
    assert after["USD"]["potential"] == before["USD"]["potential"] - D("960")
    assert after["USD"]["confirmed"] == after["USD"]["cash_recovered"] == after["USD"]["corrected_billing"] == 0
    assert body["counts"]["rejected"] == 1

    # 6. Approved correction: identified → corrected billing → cash only after a matching payment.
    act(client, analyst, wrong_rate["id"], "assign", {"owner_id": analyst.user_id})
    act(client, analyst, wrong_rate["id"], "propose",
        {"root_cause_category": "price_not_updated", "root_cause": "March price book entry was 40 instead of 45"})
    assert client.post(f"/api/findings/{wrong_rate['id']}/approve", headers=analyst.headers, json={}).status_code == 403
    correction = act(client, approver, wrong_rate["id"], "approve")["correction"]
    figures, _ = outcomes(client, executive)
    assert (figures["USD"]["confirmed"], figures["USD"]["corrected_billing"], figures["USD"]["cash_recovered"]) == (
        D("600"), 0, 0)
    sim = lambda stage: client.post(f"/api/recovery/corrections/{correction['id']}/simulate",  # noqa: E731
                                    headers=analyst.headers, json={"stage": stage})
    assert sim("billing").status_code == 200
    figures, _ = outcomes(client, executive)
    assert (figures["USD"]["corrected_billing"], figures["USD"]["cash_recovered"]) == (D("600"), 0)  # unpaid ≠ cash
    assert sim("payment").status_code == 200
    figures, _ = outcomes(client, executive)
    assert figures["USD"]["cash_recovered"] == D("600")
    assert client.get(f"/api/findings/{wrong_rate['id']}", headers=analyst.headers).json()["status"] == "recovered"

    # 7. A repeated import duplicates no source records, findings or recovery totals.
    snap, figures_before = snapshot(session), outcomes(client, executive)[0]
    admin = login(client, "admin", "jm.com")
    for src in client.get("/api/data-sources", headers=admin.headers).json():
        if src["kind"] == "connector":
            assert client.post(f"/api/data-sources/{src['id']}/sync", headers=admin.headers,
                               json={"stage": "baseline"}).status_code == 202
    jobs.drain()
    again = run_checks(client, analyst)
    assert again["stats"]["new"] == 0
    assert snapshot(session) == snap and outcomes(client, executive)[0] == figures_before

    # 8. A user can't view or approve another organization's findings.
    assert client.get(f"/api/findings/{wrong_rate['id']}", headers=b_analyst.headers).status_code == 404
    assert client.post(f"/api/findings/{unbilled['id']}/approve", headers=b_approver.headers, json={}).status_code == 404
    assert client.post(f"/api/recovery/corrections/{correction['id']}/simulate", headers=b_analyst.headers,
                       json={"stage": "payment"}).status_code == 404
    assert all(f["agreement_title"] != "Data strategy SOW" for f in items(client, b_analyst))
    jm_org = session.scalar(select(Organization.id).where(Organization.name == "JM"))
    assert session.scalar(select(func.count()).select_from(DataSource).where(DataSource.org_id == jm_org)) >= 3

"""BE-023: correction → billed → cash, only from payments against the corrected invoice (FR-30, GR-04, GR-11)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core import jobs
from app.domains.access.models import Organization
from app.seed_demo import DEMO_PASSWORD, demo_email, main as seed
from tests.engine_helpers import run
from tests.factories import Actor
from tests.ingest_helpers import create_source, load
from tests.test_workflow import PROPOSAL, post, team  # noqa: F401  (fixture)

INV_HEAD = "invoice_id,customer_id,number,invoice_date,currency,correction_reference\n"
LINE_HEAD = "line_id,invoice_id,agreement_id,item_code,quantity,unit_price,net_amount,tax_amount,service_period_start\n"
PAY_HEAD = "payment_id,customer_id,amount,currency,payment_date\n"
ALLOC_HEAD = "allocation_id,payment_id,invoice_id,amount\n"


def _approve(client, t, fid):
    a, ap = t["analyst"], t["approver"]
    post(client, a, fid, "assign", {"owner_id": a.user_id})
    post(client, a, fid, "propose", PROPOSAL)
    return post(client, ap, fid, "approve").json()["correction"]


def _tracker(client, actor):
    return {c["reference"]: c for c in client.get("/api/recovery/corrections", headers=actor.headers).json()["corrections"]}


def _finding(client, actor, fid):
    return client.get(f"/api/findings/{fid}", headers=actor.headers).json()


def test_billed_then_cash_capped_at_correction_amount(client, team):  # noqa: F811
    t = team
    ref = _approve(client, t, t["rate"])["reference"]
    src = create_source(client, t["admin"], "Billing system")

    load(client, t["admin"], src, "invoice", INV_HEAD + f"X1,C1,INV-9,2026-10-27,USD,{ref}\nX2,C1,INV-10,2026-10-27,USD,\n")
    load(client, t["admin"], src, "invoice_line", LINE_HEAD + "XL1,X1,A1,SEAT,1,600,600,48,2026-03-01\n"
                                                              "XL2,X2,A1,SEAT,1,45,45,0,2026-10-01\n")
    jobs.drain()  # recovery_reconcile queued by the import
    c = _tracker(client, t["analyst"])[ref]
    assert (c["status"], c["billed"], c["cash_recovered"], c["invoice_numbers"]) == ("billed", "600.0000", "0", ["INV-9"])
    assert _finding(client, t["analyst"], t["rate"])["status"] == "billed"

    # A payment to an unrelated invoice never counts (GR-04).
    load(client, t["admin"], src, "payment", PAY_HEAD + "P0,C1,45,USD,2026-10-28\nP1,C1,300,USD,2026-10-28\n")
    load(client, t["admin"], src, "payment_allocation", ALLOC_HEAD + "A0,P0,X2,45\nA1,P1,X1,300\n")
    jobs.drain()
    c = _tracker(client, t["analyst"])[ref]
    assert (c["status"], c["cash_received"], c["cash_recovered"]) == ("partially_paid", "300.0000", "300.0000")
    assert _finding(client, t["analyst"], t["rate"])["status"] == "billed"

    # Paying the rest including tax: received 648, recovered capped at the 600 correction.
    load(client, t["admin"], src, "payment", PAY_HEAD + "P2,C1,348,USD,2026-10-30\n")
    load(client, t["admin"], src, "payment_allocation", ALLOC_HEAD + "A2,P2,X1,348\n")
    jobs.drain()
    c = _tracker(client, t["analyst"])[ref]
    assert (c["status"], c["cash_received"], c["cash_recovered"]) == ("paid", "648.0000", "600.0000")
    f = _finding(client, t["analyst"], t["rate"])
    assert f["status"] == "recovered" and f["available_actions"] == ["comment"]
    assert [e["data"]["to"] for e in f["timeline"] if e["kind"] == "status"][-2:] == ["billed", "recovered"]

    # Re-importing everything changes nothing (GR-11).
    load(client, t["admin"], src, "invoice_line", LINE_HEAD + "XL1,X1,A1,SEAT,1,600,600,48,2026-03-01\n")
    load(client, t["admin"], src, "payment_allocation", ALLOC_HEAD + "A1,P1,X1,300\nA2,P2,X1,348\n")
    jobs.drain()
    c = _tracker(client, t["analyst"])[ref]
    assert (c["billed"], c["cash_received"], c["cash_recovered"], len(c["events"])) == ("600.0000", "648.0000",
                                                                                         "600.0000", 3)


def test_written_off_finding_stays_closed_when_invoice_arrives(client, team):  # noqa: F811
    t = team
    ref = _approve(client, t, t["rate"])["reference"]
    post(client, t["approver"], t["rate"], "write-off", {"note": "Customer refused"})
    src = create_source(client, t["admin"], "Billing system")
    load(client, t["admin"], src, "invoice", INV_HEAD + f"X1,C1,INV-9,2026-10-27,USD,{ref}\n")
    load(client, t["admin"], src, "invoice_line", LINE_HEAD + "XL1,X1,A1,SEAT,1,600,600,0,2026-03-01\n")
    jobs.drain()
    assert _finding(client, t["analyst"], t["rate"])["status"] == "closed_no_recovery"
    assert _tracker(client, t["analyst"])[ref]["status"] == "billed"


def test_simulation_is_refused_outside_demo_orgs(client, team):  # noqa: F811
    t = team
    cid = _approve(client, t, t["rate"])["id"]
    r = client.post(f"/api/recovery/corrections/{cid}/simulate", headers=t["analyst"].headers, json={"stage": "billing"})
    assert r.status_code == 403
    assert client.get("/api/recovery/corrections", headers=t["commercial"].headers).status_code == 403
    assert client.get("/api/recovery/corrections", headers=t["executive"].headers).status_code == 200


def _demo(client, role: str, domain: str) -> Actor:
    body = client.post("/api/auth/login", json={"email": demo_email(role, domain), "password": DEMO_PASSWORD}).json()
    return Actor(body["access_token"], body["me"]["user"]["id"], body["me"]["organization"]["id"], role, "")


def test_scenario_6_on_demo_org_via_simulation(client, session):
    """Approved correction: confirmed → corrected billing → cash recovered only after the payment."""
    seed([])
    jm = session.scalar(select(Organization).where(Organization.name == "JM"))
    run(jm.id, date(2026, 10, 26))
    analyst, approver = _demo(client, "analyst", "jm.com"), _demo(client, "approver", "jm.com")
    fid = next(i["id"] for i in client.get("/api/findings", headers=analyst.headers).json()["items"]
               if i["check_type"] == "incorrect_rate")
    post(client, analyst, fid, "assign", {"owner_id": analyst.user_id})
    post(client, analyst, fid, "propose", PROPOSAL)
    c = post(client, approver, fid, "approve").json()["correction"]
    assert c["reference"] == "JA-JM-0001"

    sim = lambda stage: client.post(f"/api/recovery/corrections/{c['id']}/simulate",  # noqa: E731
                                    headers=analyst.headers, json={"stage": stage})
    assert sim("payment").status_code == 409  # can't pay before billing
    row = sim("billing").json()["corrections"][0]
    assert (row["status"], row["billed"], row["cash_recovered"]) == ("billed", "600.0000", "0")
    assert _finding(client, analyst, fid)["status"] == "billed"
    row = sim("payment").json()["corrections"][0]
    assert (row["status"], row["cash_recovered"]) == ("paid", "600.0000")
    assert _finding(client, analyst, fid)["status"] == "recovered"
    assert sim("billing").status_code == 409
    # The simulated supplementary line covers March, so a re-run finds no new discrepancies.
    again = run(jm.id, date(2026, 10, 26))
    assert again.stats["new"] == 0 and Decimal(row["amount"]) == Decimal("600")

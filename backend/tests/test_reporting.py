"""BE-025: the six outcome figures, separately computed; rejected findings never in money (FR-32, GR-04, GR-05)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.domains.access.models import Organization
from app.seed_demo import main as seed
from tests.engine_helpers import run
from tests.test_recovery import _demo
from tests.test_workflow import PROPOSAL, post, team  # noqa: F401  (fixture)

D = Decimal


def _figures(client, actor):
    body = client.get("/api/reports/outcomes", headers=actor.headers).json()
    return {c["currency"]: {k: D(v) for k, v in c.items() if k != "currency"} for c in body["currencies"]}, body


def test_figures_move_through_scenarios_5_and_6(client, session):
    seed([])
    jm = session.scalar(select(Organization).where(Organization.name == "JM"))
    run(jm.id, date(2026, 10, 26))
    an, ap, ex = (_demo(client, r, "jm.com") for r in ("analyst", "approver", "executive"))
    items = client.get("/api/findings", headers=an.headers).json()["items"]
    rate = next(i["id"] for i in items if i["check_type"] == "incorrect_rate")
    analyst_hours = next(i["id"] for i in items if i["value"] == "960.0000")

    usd, body = _figures(client, ex)
    assert usd["USD"]["potential"] == D("4530") and usd["USD"]["confirmed"] == 0
    assert body["counts"]["open"] == 6

    # Scenario 5: rejected finding leaves every money figure (GR-05).
    post(client, an, analyst_hours, "reject", {"note": "Non-billable workshop prep"})
    usd, body = _figures(client, ex)
    assert usd["USD"]["potential"] == D("3570") and body["counts"]["rejected"] == 1
    assert all(v == 0 for k, v in usd["USD"].items() if k != "potential")

    # Scenario 6: approve → confirmed; simulate billing → corrected billing; payment → cash recovered.
    post(client, an, rate, "assign", {"owner_id": an.user_id})
    post(client, an, rate, "propose", PROPOSAL)
    cid = post(client, ap, rate, "approve").json()["correction"]["id"]
    usd, _ = _figures(client, ex)
    assert (usd["USD"]["potential"], usd["USD"]["confirmed"], usd["USD"]["corrected_billing"],
            usd["USD"]["cash_recovered"]) == (D("2970"), D("600"), 0, 0)
    client.post(f"/api/recovery/corrections/{cid}/simulate", headers=an.headers, json={"stage": "billing"})
    usd, _ = _figures(client, ex)
    assert (usd["USD"]["corrected_billing"], usd["USD"]["cash_recovered"]) == (D("600"), 0)  # unpaid ≠ cash
    client.post(f"/api/recovery/corrections/{cid}/simulate", headers=an.headers, json={"stage": "payment"})
    usd, body = _figures(client, ex)
    assert (usd["USD"]["confirmed"], usd["USD"]["corrected_billing"], usd["USD"]["cash_recovered"]) == (
        D("600"), D("600"), D("600"))
    assert body["counts"]["recovered"] == 1
    month = date.today().strftime("%Y-%m")
    assert D(next(p for p in body["trend"] if p["month"] == month)["recovered"]) == D("600")
    assert body["root_causes"] == [{"category": "price_not_updated", "currency": "USD", "count": 1,
                                    "value": "600.0000"}]


def test_cash_is_capped_per_correction_and_write_off_counts_separately(client, team):
    from app.core import jobs
    from tests.ingest_helpers import create_source, load
    from tests.test_recovery import ALLOC_HEAD, INV_HEAD, LINE_HEAD, PAY_HEAD, _approve

    t = team
    ref = _approve(client, t, t["rate"])["reference"]
    src = create_source(client, t["admin"], "Billing")
    load(client, t["admin"], src, "invoice", INV_HEAD + f"X1,C1,INV-9,2026-10-27,USD,{ref}\n")
    load(client, t["admin"], src, "invoice_line", LINE_HEAD + "XL1,X1,A1,SEAT,1,600,600,48,2026-03-01\n")
    load(client, t["admin"], src, "payment", PAY_HEAD + "P1,C1,648,USD,2026-10-28\n")
    load(client, t["admin"], src, "payment_allocation", ALLOC_HEAD + "A1,P1,X1,648\n")
    jobs.drain()
    usd, _ = _figures(client, t["executive"])
    assert usd["USD"]["cash_recovered"] == D("600")  # 648 received, capped at the correction

    unbilled = t["unbilled"]
    post(client, t["analyst"], unbilled, "assign", {"owner_id": t["analyst"].user_id})
    post(client, t["analyst"], unbilled, "propose", PROPOSAL | {"root_cause_category": "delivery_not_billed"})
    post(client, t["approver"], unbilled, "approve")
    post(client, t["approver"], unbilled, "write-off", {"note": "Goodwill"})
    usd, _ = _figures(client, t["executive"])
    assert usd["USD"]["closed_without_recovery"] == D("1800") and usd["USD"]["confirmed"] == D("2400")
    assert usd["USD"]["cash_recovered"] == D("600")


def test_reports_are_org_scoped(client, team):
    from tests.factories import signup

    other = signup(client)
    body = client.get("/api/reports/outcomes", headers=other.headers).json()
    assert body["currencies"] == [] and body["counts"]["total"] == 0

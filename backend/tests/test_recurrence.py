"""BE-024: root cause required, recurrence flagged on later runs, prevented-recurrence estimate (FR-31)."""

from datetime import date
from decimal import Decimal

from tests.engine_helpers import run
from tests.ingest_helpers import create_source, load
from tests.test_checks import INVOICES_HEAD, LINES_HEAD
from tests.test_workflow import PROPOSAL, post, team  # noqa: F401  (fixture)

LATER = (INVOICES_HEAD + "I2,C1,INV-4,2026-04-01,USD\nI3,C1,INV-5,2026-05-01,USD\nI4,C1,INV-6,2026-06-01,USD\n",
         LINES_HEAD + "L2,I2,A1,SEAT,120,40,,4800,0,2026-04-01,2026-04-30\n"     # wrong rate again
                      "L3,I3,A1,SEAT,120,45,,5400,0,2026-05-01,2026-05-31\n"     # clean
                      "L4,I4,A1,SEAT,120,45,,5400,0,2026-06-01,2026-06-30\n")    # clean


def _confirm(client, t, fid):
    a, ap = t["analyst"], t["approver"]
    post(client, a, fid, "assign", {"owner_id": a.user_id})
    assert post(client, a, fid, "propose", {"root_cause_category": "price_not_updated", "root_cause": ""}).status_code == 422
    assert post(client, a, fid, "propose", PROPOSAL).status_code == 200  # root cause required (FR-31)
    assert post(client, ap, fid, "approve").status_code == 200


def _load_later(client, t):
    src = create_source(client, t["admin"], "Later billing")
    load(client, t["admin"], src, "invoice", LATER[0])
    load(client, t["admin"], src, "invoice_line", LATER[1])
    return run(t["admin"].org_id, date(2026, 10, 26))


def _items(client, actor):
    return client.get("/api/findings?limit=50", headers=actor.headers).json()["items"]


def test_later_run_flags_recurrence_of_confirmed_cause(client, team):  # noqa: F811
    t = team
    _confirm(client, t, t["rate"])
    r = _load_later(client, t)
    assert r.stats["new"] == 1 and r.stats["recurrences"] == 1
    april = next(i for i in _items(client, t["analyst"])
                 if i["period_start"] == "2026-04-01" and i["check_type"] == "incorrect_rate")
    detail = client.get(f"/api/findings/{april['id']}", headers=t["analyst"].headers).json()
    assert detail["check_type"] == "incorrect_rate"
    assert detail["recurrence_of"]["id"] == t["rate"]
    assert detail["recurrence_of"]["root_cause_category"] == "price_not_updated"

    body = client.get("/api/reports/outcomes", headers=t["executive"].headers).json()
    assert body["counts"]["recurring"] == 1
    usd = next(c for c in body["currencies"] if c["currency"] == "USD")
    # March confirmed at 600; May and June were billed correctly (April recurred, so it doesn't count).
    assert Decimal(usd["prevented_recurrence"]) == Decimal("1200")


def test_unconfirmed_or_rejected_findings_do_not_create_recurrences(client, team):  # noqa: F811
    t = team
    post(client, t["analyst"], t["rate"], "reject", {"note": "Agreed one-off price"})
    r = _load_later(client, t)
    assert r.stats["recurrences"] == 0
    april = next(i for i in _items(client, t["analyst"])
                 if i["period_start"] == "2026-04-01" and i["check_type"] == "incorrect_rate")
    assert client.get(f"/api/findings/{april['id']}", headers=t["analyst"].headers).json()["recurrence_of"] is None
    usd = next(c for c in client.get("/api/reports/outcomes", headers=t["executive"].headers).json()["currencies"]
               if c["currency"] == "USD")
    assert Decimal(usd["prevented_recurrence"]) == 0


def test_different_cause_is_not_a_recurrence(client, team):  # noqa: F811
    """A missed escalation after a wrong-rate fix is a new cause, not a recurrence."""
    t = team
    _confirm(client, t, t["rate"])
    src = create_source(client, t["admin"], "Later billing")
    load(client, t["admin"], src, "invoice", INVOICES_HEAD + "I7,C1,INV-7,2026-07-01,USD\n")
    load(client, t["admin"], src, "invoice_line", LINES_HEAD + "L7,I7,A1,SEAT,120,45,,5400,0,2026-07-01,2026-07-31\n")
    r = run(t["admin"].org_id, date(2026, 10, 26))
    assert r.stats["new"] == 1 and r.stats["recurrences"] == 0

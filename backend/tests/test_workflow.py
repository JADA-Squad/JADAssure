"""BE-021 / BE-022: workflow transitions, separation of duties, immutability, prepared corrections."""

import csv
import io
from datetime import date

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from app.domains.cases.models import Correction
from app.domains.rules.models import Finding
from tests.engine_helpers import load_world, run
from tests.factories import add_user, signup
from tests.test_checks import EVENTS_HEAD, INVOICES_HEAD, LINES_HEAD, RATE_TERMS

PROPOSAL = {"root_cause_category": "price_not_updated", "root_cause": "March price book entry was wrong"}


@pytest.fixture
def team(client):
    """An org with one wrong-rate finding (600.00) and one unbilled finding, plus a full team."""
    admin = signup(client)
    load_world(client, admin, {
        "commercial_term": RATE_TERMS,
        "billable_event": EVENTS_HEAD + "E1,C1,A1,HOURS,10,hour,2026-04-15,2026-04-30,USD\n",
        "invoice": INVOICES_HEAD + "I1,C1,INV-3,2026-03-01,USD\n",
        "invoice_line": LINES_HEAD + "L1,I1,A1,SEAT,120,40,,4800,0,2026-03-01,2026-03-31\n",
    })
    run(admin.org_id, date(2026, 10, 26))
    t = {"admin": admin}
    for role in ("analyst", "approver", "commercial", "executive"):
        t[role] = add_user(client, admin, role)
    t["approver2"] = add_user(client, admin, "approver")
    items = client.get("/api/findings", headers=t["analyst"].headers).json()["items"]
    t["rate"] = next(i["id"] for i in items if i["check_type"] == "incorrect_rate")
    t["unbilled"] = next(i["id"] for i in items if i["check_type"] == "delivered_not_billed")
    return t


def post(client, actor, fid, action, body=None):
    return client.post(f"/api/findings/{fid}/{action}", headers=actor.headers, json=body or {})


def test_happy_path_to_approval_creates_one_correction(client, session, team):
    a, ap = team["analyst"], team["approver"]
    fid = team["rate"]
    assert post(client, a, fid, "propose", PROPOSAL).status_code == 409  # must be in review first
    r = post(client, a, fid, "assign", {"owner_id": a.user_id})
    assert r.status_code == 200 and r.json()["status"] == "in_review" and r.json()["owner_name"]
    r = post(client, a, fid, "propose", PROPOSAL)
    assert r.json()["status"] == "proposed" and r.json()["root_cause_category"] == "price_not_updated"
    assert "approve" not in r.json()["available_actions"]

    r = post(client, ap, fid, "approve", {"note": "Agreed with sales"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "approved" and d["available_actions"] == ["comment", "assign", "write_off"]
    c = d["correction"]
    assert c["reference"].startswith("JA-") and c["reference"].endswith("-0001")
    assert (c["amount"], c["status"], c["kind"]) == ("600.0000", "prepared", "supplementary_invoice")
    statuses = [t["data"]["to"] for t in d["timeline"] if t["kind"] == "status"]
    assert statuses == ["in_review", "proposed", "approved"]
    assert [t["kind"] for t in d["timeline"]][:2] == ["detected", "assign"]
    assert any(t["kind"] == "approval" and t["data"]["decision"] == "approved" for t in d["timeline"])
    assert session.scalar(select(Correction).where(Correction.finding_id == fid)) is not None

    # Approving again is impossible: the state has moved on (no double approval).
    assert post(client, team["approver2"], fid, "approve").status_code == 409
    assert len(session.scalars(select(Correction)).all()) == 1


def test_proposer_cannot_approve(client, session, team):
    fid = team["rate"]
    # A commercial manager proposes; then gets re-roled to approver and tries to approve their own proposal.
    com = team["commercial"]
    post(client, com, fid, "assign", {"owner_id": com.user_id})
    post(client, com, fid, "propose", PROPOSAL)
    client.patch(f"/api/users/{com.user_id}", headers=team["admin"].headers, json={"role": "approver"})
    r = post(client, com, fid, "approve")
    assert r.status_code == 403 and "separation of duties" in r.json()["detail"]
    detail = client.get(f"/api/findings/{fid}", headers=com.headers).json()
    assert "approve" not in detail["available_actions"] and "send_back" in detail["available_actions"]
    assert post(client, team["approver"], fid, "approve").status_code == 200


def test_reject_and_send_back_need_reasons_and_respect_states(client, team):
    a, ap = team["analyst"], team["approver"]
    fid = team["unbilled"]
    assert post(client, a, fid, "reject", {"note": ""}).status_code == 422
    r = post(client, a, fid, "reject", {"note": "Non-billable workshop prep agreed with customer"})
    assert r.json()["status"] == "rejected" and r.json()["available_actions"] == ["comment"]
    for action, actor in (("propose", a), ("approve", ap), ("write-off", ap), ("send-back", ap)):
        assert post(client, actor, fid, action, PROPOSAL | {"note": "x"}).status_code == 409, action
    assert post(client, a, fid, "assign", {"owner_id": a.user_id}).status_code == 409

    rate = team["rate"]
    client.post(f"/api/findings/{rate}/comments", headers=a.headers, json={"body": "Looking into it"})
    post(client, a, rate, "propose", PROPOSAL)
    assert post(client, ap, rate, "send-back", {"note": ""}).status_code == 422
    r = post(client, ap, rate, "send-back", {"note": "Attach the price book extract"})
    assert r.json()["status"] == "in_review"
    assert post(client, a, rate, "propose", {"root_cause_category": "made_up", "root_cause": "x"}).status_code == 422


def test_role_permissions_on_actions(client, team):
    fid = team["rate"]
    assert post(client, team["executive"], fid, "assign", {"owner_id": None}).status_code == 403
    assert post(client, team["admin"], fid, "reject", {"note": "x"}).status_code == 403
    assert post(client, team["approver"], fid, "reject", {"note": "x"}).status_code == 403
    assert post(client, team["analyst"], fid, "approve").status_code == 403
    r = post(client, team["analyst"], fid, "assign", {"owner_id": team["executive"].user_id})
    assert r.status_code == 422  # executives can't own case work
    other = signup(client)
    assert post(client, add_user(client, other, "analyst"), fid, "assign", {"owner_id": None}).status_code == 404


def test_write_off_and_terminal_immutability(client, session, team):
    a, ap = team["analyst"], team["approver"]
    fid = team["rate"]
    post(client, a, fid, "assign", {"owner_id": a.user_id})
    post(client, a, fid, "propose", PROPOSAL)
    post(client, ap, fid, "approve")
    assert post(client, ap, fid, "write-off", {"note": "Customer disputes; commercial decision"}).json()["status"] \
        == "closed_no_recovery"

    # GR-13: even a direct database update can't change a terminal finding.
    for sql in ("UPDATE finding SET value = 1 WHERE id = :id", "UPDATE finding SET status = 'open' WHERE id = :id",
                "UPDATE finding SET evidence = '{}' WHERE id = :id"):
        with pytest.raises(DBAPIError, match="final"):
            session.execute(text(sql), {"id": fid})
        session.rollback()
    session.execute(update(Finding).where(Finding.id == fid).values(owner_id=None))  # non-money fields may change
    session.commit()


def test_correction_export_and_no_outbound_path(client, team):
    a, ap = team["analyst"], team["approver"]
    fid = team["unbilled"]
    post(client, a, fid, "assign", {"owner_id": a.user_id})
    post(client, a, fid, "propose", PROPOSAL | {"root_cause_category": "delivery_not_billed"})
    cid = post(client, ap, fid, "approve").json()["correction"]["id"]

    j = client.get(f"/api/corrections/{cid}/export.json", headers=a.headers).json()
    assert j["lines"][0]["quantity"] == "10" and j["amount"] == "1800.0000" and j["customer"]["source_record_id"] == "C1"
    assert j["reference"] in j["instructions"]
    rows = list(csv.reader(io.StringIO(client.get(f"/api/corrections/{cid}/export.csv", headers=ap.headers).text)))
    assert rows[0][0] == "reference" and rows[1][0] == j["reference"] and rows[1][-1] == "1800.0000"
    assert client.get(f"/api/corrections/{cid}/export.csv", headers=team["commercial"].headers).status_code == 403

    # GR-01: the API offers no way to send a correction anywhere.
    from app.main import app

    send_like = [r.path for r in app.routes if any(w in r.path for w in ("send", "email", "post-invoice", "issue"))]
    assert send_like == [] or all("send-back" in p for p in send_like)


def test_comment_starts_review(client, team):
    r = client.post(f"/api/findings/{team['rate']}/comments", headers=team["approver"].headers, json={"body": "Hm"})
    assert r.json()["status"] == "in_review"

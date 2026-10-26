"""BE-004: hash-chained audit log and verification (GR-10)."""

import uuid

from sqlalchemy import text

from app.domains.audit import service as audit
from tests.factories import add_user, signup


def test_state_changes_append_chained_events(client):
    admin = signup(client)
    add_user(client, admin, "analyst")

    events = client.get("/api/audit", headers=admin.headers).json()
    assert [e["action"] for e in reversed(events)] == ["organization.created", "user.created", "user.created"]
    assert [e["seq"] for e in reversed(events)] == [1, 2, 3]
    assert client.get("/api/audit/verify", headers=admin.headers).json() == {"ok": True, "events": 3, "first_bad_seq": None}


def test_tampered_payload_is_detected(client, session):
    admin = signup(client)
    add_user(client, admin, "analyst")
    session.execute(
        text("UPDATE audit_event SET payload = '{\"role\": \"admin\"}' WHERE org_id = :o AND seq = 3"),
        {"o": admin.org_id},
    )
    session.commit()

    result = client.get("/api/audit/verify", headers=admin.headers).json()
    assert result["ok"] is False and result["first_bad_seq"] == 3


def test_deleted_event_is_detected(client, session):
    admin = signup(client)
    add_user(client, admin, "analyst")
    session.execute(text("DELETE FROM audit_event WHERE org_id = :o AND seq = 2"), {"o": admin.org_id})
    session.commit()

    result = client.get("/api/audit/verify", headers=admin.headers).json()
    assert result["ok"] is False and result["first_bad_seq"] == 3


def test_audit_event_rolls_back_with_failed_change(client, session):
    admin = signup(client)
    org_id = uuid.UUID(admin.org_id)
    audit.record(session, org_id=org_id, actor_id=None, action="test.event", entity="test", payload={"n": 1})
    session.rollback()
    assert audit.count_events(session, org_id) == 2
    assert audit.verify(session, org_id)["ok"]


def test_approver_can_view_audit(client):
    admin = signup(client)
    approver = add_user(client, admin, "approver")
    assert client.get("/api/audit/verify", headers=approver.headers).status_code == 200

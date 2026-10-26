"""BE-010: run checks now, scheduled refresh, visible failures (FR-10, FR-11)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.core import jobs
from app.core.db import new_session
from app.domains.access.models import Organization
from app.domains.rules import engine
from app.domains.rules.models import CheckRun
from tests.factories import add_user, signup


def test_run_checks_now_runs_in_worker(client):
    admin = signup(client)
    analyst = add_user(client, admin, "analyst")
    res = client.post("/api/check-runs", headers=analyst.headers)
    assert res.status_code == 202 and res.json()["status"] == "queued"
    assert client.post("/api/check-runs", headers=admin.headers).status_code == 409  # one at a time
    jobs.drain()
    runs = client.get("/api/check-runs", headers=analyst.headers).json()
    assert runs[0]["status"] == "succeeded" and runs[0]["trigger"] == "manual"
    assert runs[0]["stats"]["detected"] == 0 and "duration_ms" in runs[0]["stats"]


def test_run_permissions_and_scope(client):
    admin = signup(client)
    for role, code in (("commercial", 403), ("executive", 403), ("approver", 403)):
        assert client.post("/api/check-runs", headers=add_user(client, admin, role).headers).status_code == code
    approver = add_user(client, admin, "approver")
    client.post("/api/check-runs", headers=admin.headers)
    jobs.drain()
    assert len(client.get("/api/check-runs", headers=approver.headers).json()) == 1  # approvers can view runs
    other = signup(client)
    assert client.get("/api/check-runs", headers=other.headers).json() == []


def test_schedule_enqueues_when_interval_elapsed(client, session):
    admin = signup(client)
    org_id = uuid.UUID(admin.org_id)
    with new_session() as s:
        assert engine.enqueue_due(s) == 0  # no interval configured
        s.execute(update(Organization).where(Organization.id == org_id)
                  .values(settings={"refresh_interval_minutes": 60}))
        s.commit()
        assert engine.enqueue_due(s) == 1
        s.commit()
        assert engine.enqueue_due(s) == 0  # already queued
    jobs.drain()
    with new_session() as s:
        assert engine.enqueue_due(s) == 0  # ran just now
        later = datetime.now(UTC) + timedelta(minutes=61)
        assert engine.enqueue_due(s, now=later) == 1
        s.commit()
    jobs.drain()
    runs = client.get("/api/check-runs", headers=admin.headers).json()
    assert [r["trigger"] for r in runs] == ["schedule", "schedule"]


def test_failed_run_is_visible_and_retryable(client, monkeypatch):
    admin = signup(client)

    def boom(*a, **k):
        raise jobs.JobError("Rule configuration could not be loaded")

    monkeypatch.setattr(engine, "evaluate", boom)
    client.post("/api/check-runs", headers=admin.headers)
    jobs.drain()
    run = client.get("/api/check-runs", headers=admin.headers).json()[0]
    assert run["status"] == "failed" and run["error"] == "Rule configuration could not be loaded"
    job = client.get("/api/jobs?status=failed", headers=admin.headers).json()[0]
    monkeypatch.undo()
    client.post(f"/api/jobs/{job['id']}/retry", headers=admin.headers)
    jobs.drain()
    with new_session() as s:
        assert s.get(CheckRun, uuid.UUID(run["id"])).status == "succeeded"

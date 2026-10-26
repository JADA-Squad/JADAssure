"""BE-008: Postgres job queue with SKIP LOCKED, visible failures and retry (FR-11)."""

import uuid

from app.core import jobs
from app.core.db import new_session
from app.core.models import Job
from tests.factories import add_user, signup

CALLS: list[str] = []
FAIL_NEXT = {"flaky": True}


@jobs.register("test.ok")
def _ok(session, job):
    CALLS.append(job.payload["n"])


def _mark_failed(session, job):
    job.payload = {**job.payload, "hook": "failed"}


def _mark_retried(session, job):
    job.payload = {**job.payload, "hook": "retried"}


@jobs.register("test.flaky", on_failure=_mark_failed, on_retry=_mark_retried)
def _flaky(session, job):
    if FAIL_NEXT["flaky"]:
        FAIL_NEXT["flaky"] = False
        raise jobs.JobError("Source file is missing required column 'name'")


@jobs.register("test.crash")
def _crash(session, job):
    raise RuntimeError("secret row content must not leak")


def _enqueue(org_id, kind, **payload):
    with new_session() as s:
        job = jobs.enqueue(s, kind=kind, org_id=uuid.UUID(org_id), payload=payload)
        s.commit()
        return job.id


def test_jobs_run_in_order(client):
    admin = signup(client)
    CALLS.clear()
    for n in range(3):
        _enqueue(admin.org_id, "test.ok", n=n)
    assert jobs.drain() == 3
    assert CALLS == [0, 1, 2]


def test_skip_locked_claims_distinct_jobs(client):
    admin = signup(client)
    a, b = _enqueue(admin.org_id, "test.ok", n=1), _enqueue(admin.org_id, "test.ok", n=2)
    s1, s2 = new_session(), new_session()
    try:
        # Hold s1's row lock open while s2 claims.
        from sqlalchemy import select

        locked = s1.scalar(select(Job).where(Job.status == "queued").order_by(Job.created_at, Job.id)
                           .limit(1).with_for_update(skip_locked=True))
        claimed = jobs.claim_next(s2)
        assert {locked.id, claimed.id} == {a, b}
    finally:
        s1.rollback()
        s1.close()
        s2.close()


def test_failed_job_is_visible_and_retryable(client):
    admin = signup(client)
    FAIL_NEXT["flaky"] = True
    job_id = _enqueue(admin.org_id, "test.flaky")
    jobs.drain()

    failed = client.get("/api/jobs?status=failed", headers=admin.headers).json()
    assert [j["id"] for j in failed] == [str(job_id)]
    assert failed[0]["last_error"] == "Source file is missing required column 'name'"
    assert failed[0]["payload"]["hook"] == "failed"

    res = client.post(f"/api/jobs/{job_id}/retry", headers=admin.headers)
    assert res.status_code == 200 and res.json()["status"] == "queued"
    assert res.json()["payload"]["hook"] == "retried"
    jobs.drain()
    job = client.get("/api/jobs", headers=admin.headers).json()[0]
    assert job["status"] == "succeeded" and job["attempts"] == 2 and job["last_error"] is None


def test_unexpected_errors_do_not_leak_details(client):
    admin = signup(client)
    _enqueue(admin.org_id, "test.crash")
    jobs.drain()
    job = client.get("/api/jobs", headers=admin.headers).json()[0]
    assert job["status"] == "failed"
    assert "secret" not in job["last_error"] and "RuntimeError" in job["last_error"]


def test_only_failed_jobs_can_be_retried(client):
    admin = signup(client)
    job_id = _enqueue(admin.org_id, "test.ok", n=0)
    assert client.post(f"/api/jobs/{job_id}/retry", headers=admin.headers).status_code == 409


def test_jobs_are_org_scoped_and_admin_only(client):
    a = signup(client)
    job_id = _enqueue(a.org_id, "test.crash")
    jobs.drain()
    b = signup(client)
    assert client.get("/api/jobs", headers=b.headers).json() == []
    assert client.post(f"/api/jobs/{job_id}/retry", headers=b.headers).status_code == 404
    analyst = add_user(client, a, "analyst")
    assert client.get("/api/jobs", headers=analyst.headers).status_code == 403

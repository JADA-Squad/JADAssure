"""INFRA-001 / INFRA-002: health and OpenAPI."""

from datetime import UTC, datetime, timedelta

from app.core.models import WorkerHeartbeat


def test_health_ok_with_fresh_worker_heartbeat(client, session):
    session.add(WorkerHeartbeat(worker_id="test", last_seen=datetime.now(UTC)))
    session.commit()

    res = client.get("/api/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok", "worker": "ok"}


def test_health_degraded_when_worker_stale(client, session):
    session.add(WorkerHeartbeat(worker_id="test", last_seen=datetime.now(UTC) - timedelta(minutes=5)))
    session.commit()

    res = client.get("/api/health")

    assert res.status_code == 503
    assert res.json()["worker"] == "stale"


def test_health_degraded_when_no_worker(client):
    res = client.get("/api/health")

    assert res.status_code == 503
    assert res.json()["worker"] == "missing"


def test_openapi_is_served(client):
    res = client.get("/api/openapi.json")

    assert res.status_code == 200
    assert res.json()["info"]["title"] == "JADAssure API"

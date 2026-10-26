"""Decision 0004: Render-style database URLs, SPA serving and the embedded worker."""

import pathlib
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


@pytest.mark.parametrize("given,expected", [
    ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
])
def test_database_url_gets_psycopg_driver(given, expected):
    assert Settings(database_url=given, jwt_secret="x" * 40).database_url == expected


@pytest.fixture
def spa_client(tmp_path: pathlib.Path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>JADAssure</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    monkeypatch.setattr(get_settings(), "frontend_dist_path", str(tmp_path))
    from app.main import create_app

    return TestClient(create_app())


def test_spa_routes_serve_index_and_api_stays_json(spa_client):
    for path in ("/", "/findings", "/findings/123", "/data-setup"):
        res = spa_client.get(path)
        assert res.status_code == 200 and "<title>JADAssure</title>" in res.text, path
    assert spa_client.get("/assets/app.js").text == "console.log(1)"
    assert spa_client.get("/favicon.svg").text == "<svg/>"
    assert spa_client.get("/api/nope").status_code == 404
    assert spa_client.get("/api/openapi.json").json()["info"]["title"] == "JADAssure API"
    assert spa_client.get("/../../etc/passwd").text.startswith("<!doctype html>")  # never escapes dist


def test_embedded_worker_reports_healthy(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedded_worker", True)
    monkeypatch.setattr(get_settings(), "worker_poll_seconds", 0.1)
    from app.main import create_app

    with TestClient(create_app()) as client:
        for _ in range(50):
            if client.get("/api/health").status_code == 200:
                break
            time.sleep(0.1)
        assert client.get("/api/health").json()["worker"] == "ok"

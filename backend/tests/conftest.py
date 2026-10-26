"""Test harness: a fresh Postgres test database per session, truncated between tests (INFRA-002)."""

import pathlib
import subprocess
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core import db
from app.core.config import get_settings

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]


def _test_url() -> str:
    settings = get_settings()
    if settings.test_database_url:
        return settings.test_database_url
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


@pytest.fixture(scope="session", autouse=True)
def test_database() -> Iterator[str]:
    url = _test_url()
    name = make_url(url).database
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()

    subprocess.run(["alembic", "-x", f"url={url}", "upgrade", "head"], cwd=BACKEND_DIR, check=True, capture_output=True)
    db.configure_engine(url)
    yield url


@pytest.fixture(autouse=True)
def clean_tables(test_database: str) -> Iterator[None]:
    yield
    engine = db.get_engine()
    with engine.begin() as conn:
        tables = conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
        ).all()
        if tables:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))


@pytest.fixture
def session() -> Iterator[Session]:
    s = db.new_session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client() -> TestClient:
    from app.main import app

    return TestClient(app)

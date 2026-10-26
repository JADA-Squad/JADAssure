"""DATA-001 (data part): seed creates three labelled DEMO orgs, users per role, clean baseline loads."""

from sqlalchemy import func, select

from app.core.config import get_settings
from app.domains.access.models import Organization, User
from app.domains.ingestion.models import BillableEvent, ImportBatch
from app.seed_demo import DEMO_ORGS, DEMO_PASSWORD, demo_email, main


def test_seed_is_complete_clean_and_idempotent(client, session, capsys):
    assert main() == 0
    orgs = session.scalars(select(Organization)).all()
    assert {o.name for o in orgs} == {d.name for d in DEMO_ORGS}
    assert all(o.is_demo for o in orgs)
    assert {o.business_type for o in orgs} == {"professional_services", "subscription_software", "distribution"}
    assert session.scalar(select(func.count()).select_from(User)) == 15
    rejected = sum(b.counts.get("rejected", 0) for b in session.scalars(select(ImportBatch)))
    assert rejected == 0
    events_before = session.scalar(select(func.count()).select_from(BillableEvent))

    assert main() == 0
    assert "already present, skipped" in capsys.readouterr().out
    assert session.scalar(select(func.count()).select_from(Organization)) == 3
    assert session.scalar(select(func.count()).select_from(BillableEvent)) == events_before

    res = client.post("/api/auth/login", json={"email": demo_email("approver", "cirrus"), "password": DEMO_PASSWORD})
    assert res.status_code == 200
    assert res.json()["me"]["organization"]["is_demo"] is True


def test_demo_accounts_are_hidden_unless_enabled(client, monkeypatch):
    main()
    monkeypatch.setattr(get_settings(), "show_demo_accounts", False)
    assert client.get("/api/auth/demo-accounts").json() == []
    monkeypatch.setattr(get_settings(), "show_demo_accounts", True)
    accounts = client.get("/api/auth/demo-accounts").json()
    assert len(accounts) == 15 and {a["password"] for a in accounts} == {DEMO_PASSWORD}


def test_demo_accounts_never_list_non_demo_orgs(client, monkeypatch):
    from tests.factories import signup

    signup(client, "Real Customer Ltd")
    monkeypatch.setattr(get_settings(), "show_demo_accounts", True)
    assert client.get("/api/auth/demo-accounts").json() == []

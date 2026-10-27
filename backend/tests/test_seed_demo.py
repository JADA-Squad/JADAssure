"""DATA-001 (data part): seed creates the labelled DEMO orgs JM and Beyon with role-based logins."""

from sqlalchemy import func, select

from app.core.config import get_settings
from app.domains.access.models import Organization, User
from app.domains.ingestion.models import BillableEvent, DataSource, ImportBatch
from app.seed_demo import DEMO_PASSWORD, demo_email, main
from tests.factories import signup


def test_seed_is_complete_clean_and_idempotent(client, session, capsys):
    assert main([]) == 0
    orgs = {o.name: o for o in session.scalars(select(Organization))}
    assert set(orgs) == {"JM", "Beyon"} and all(o.is_demo for o in orgs.values())
    assert {o.business_type for o in orgs.values()} == {"professional_services", "distribution"}
    emails = set(session.scalars(select(User.email).where(User.org_id == orgs["JM"].id)))
    assert emails == {"admin@jm.com", "financeanalyst@jm.com", "financeapprover@jm.com", "commercialmanager@jm.com",
                      "executive@jm.com"}
    assert session.scalar(select(func.count()).select_from(User)) == 10
    # JM holds two business-type datasets, each through its own labelled demo connector source.
    jm_connectors = session.scalars(select(DataSource).where(DataSource.org_id == orgs["JM"].id,
                                                            DataSource.kind == "connector")).all()
    assert len(jm_connectors) == 2 and all(s.is_demo for s in jm_connectors)
    assert sum(b.counts.get("rejected", 0) for b in session.scalars(select(ImportBatch))) == 0
    events_before = session.scalar(select(func.count()).select_from(BillableEvent))

    assert main([]) == 0
    assert "already present, skipped" in capsys.readouterr().out
    assert session.scalar(select(func.count()).select_from(Organization)) == 2
    assert session.scalar(select(func.count()).select_from(BillableEvent)) == events_before

    for role, domain in (("approver", "jm.com"), ("analyst", "beyon.com")):
        res = client.post("/api/auth/login", json={"email": demo_email(role, domain), "password": DEMO_PASSWORD})
        assert res.status_code == 200, (role, domain)
        assert res.json()["me"]["organization"]["is_demo"] is True
    assert demo_email("analyst", "beyon.com") == "financeanalyst@beyon.com"


def test_changed_demo_password_is_applied_to_existing_demo_users(client, session, monkeypatch, capsys):
    import app.seed_demo as seed_module

    main([])
    real = signup(client, "Real Customer Ltd")
    monkeypatch.setattr(seed_module, "DEMO_PASSWORD", "Another-Pass-99")
    assert main([]) == 0
    assert "5 demo passwords updated" in capsys.readouterr().out
    ok = client.post("/api/auth/login", json={"email": "admin@jm.com", "password": "Another-Pass-99"})
    old = client.post("/api/auth/login", json={"email": "admin@jm.com", "password": DEMO_PASSWORD})
    assert ok.status_code == 200 and old.status_code == 401
    # Non-demo users keep their own passwords.
    from tests.factories import PASSWORD

    assert client.post("/api/auth/login", json={"email": real.email, "password": PASSWORD}).status_code == 200


def test_remove_obsolete_only_touches_old_demo_orgs(client, session, capsys):
    from app.domains.access import service as access

    real = signup(client, "Real Customer Ltd")
    old = access.create_organization(session, name="Old Demo Co (demo)", business_type="subscription_software",
                                     is_demo=True)
    session.commit()
    old_id = old.id
    assert main(["--remove-obsolete"]) == 0
    assert "Removed obsolete demo orgs: Old Demo Co (demo)" in capsys.readouterr().out
    session.expire_all()
    names = set(session.scalars(select(Organization.name)))
    assert names == {"JM", "Beyon", "Real Customer Ltd"}
    assert session.get(Organization, old_id) is None
    assert client.get("/api/auth/me", headers=real.headers).status_code == 200


def test_reset_reseeds_only_the_named_demo_org(client, session, capsys):
    import pytest

    main([])
    jm, beyon = (session.scalar(select(Organization.id).where(Organization.name == n)) for n in ("JM", "Beyon"))
    real = signup(client, "Real Customer Ltd")
    assert main(["--reset", "JM"]) == 0
    assert "Reset demo orgs: JM" in capsys.readouterr().out
    session.expire_all()
    new_jm = session.scalar(select(Organization.id).where(Organization.name == "JM"))
    assert new_jm != jm  # JM recreated from scratch
    assert session.scalar(select(Organization.id).where(Organization.name == "Beyon")) == beyon  # untouched
    with pytest.raises(SystemExit):
        main(["--reset", "Real Customer Ltd"])
    assert client.get("/api/auth/me", headers=real.headers).status_code == 200


def test_demo_accounts_are_hidden_unless_enabled(client, monkeypatch):
    main([])
    monkeypatch.setattr(get_settings(), "show_demo_accounts", False)
    assert client.get("/api/auth/demo-accounts").json() == []
    monkeypatch.setattr(get_settings(), "show_demo_accounts", True)
    accounts = client.get("/api/auth/demo-accounts").json()
    assert len(accounts) == 10 and {a["password"] for a in accounts} == {DEMO_PASSWORD}
    assert {a["organization"] for a in accounts} == {"JM", "Beyon"}


def test_demo_accounts_never_list_non_demo_orgs(client, monkeypatch):
    signup(client, "Real Customer Ltd")
    monkeypatch.setattr(get_settings(), "show_demo_accounts", True)
    assert client.get("/api/auth/demo-accounts").json() == []

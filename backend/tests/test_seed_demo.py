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


def test_remove_obsolete_only_touches_old_demo_orgs(client, session, capsys):
    from app.domains.access import service as access

    real = signup(client, "Real Customer Ltd")
    old = access.create_organization(session, name="Cirrus Cloud (demo)", business_type="subscription_software",
                                     is_demo=True)
    session.commit()
    old_id = old.id
    assert main(["--remove-obsolete"]) == 0
    assert "Removed obsolete demo orgs: Cirrus Cloud (demo)" in capsys.readouterr().out
    session.expire_all()
    names = set(session.scalars(select(Organization.name)))
    assert names == {"JM", "Beyon", "Real Customer Ltd"}
    assert session.get(Organization, old_id) is None
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

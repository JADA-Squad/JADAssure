"""BE-032: settings, retention purge, and organization data deletion with a tombstone (FR-38, FR-41)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text

from app.core.storage import get_store
from app.domains.access import settings as org_settings
from app.domains.access.models import Organization
from app.domains.audit import service as audit
from app.domains.contracts.models import Document
from app.domains.ingestion.models import ImportBatch
from tests.doc_helpers import DEMO_CONTRACT, agreement_world, upload
from tests.factories import add_user, signup


def test_settings_defaults_update_and_audit(client):
    admin = signup(client)
    s = client.get("/api/settings", headers=admin.headers).json()
    assert (s["refresh_interval_minutes"], s["ai_provider"], s["retention_days"]) == (0, "stub", None)
    r = client.put("/api/settings", headers=admin.headers, json={"refresh_interval_minutes": 60, "retention_days": 365})
    assert r.status_code == 200 and (r.json()["refresh_interval_minutes"], r.json()["retention_days"]) == (60, 365)
    event = client.get("/api/audit", headers=admin.headers).json()[0]
    assert event["action"] == "settings.updated" and event["payload"]["changes"] == {
        "refresh_interval_minutes": 60, "retention_days": 365}
    assert client.put("/api/settings", headers=admin.headers, json={"retention_days": 5}).status_code == 422
    assert client.put("/api/settings", headers=admin.headers, json={"clear_retention": True}).json()["retention_days"] is None
    for role in ("approver", "analyst", "executive"):
        actor = add_user(client, admin, role)
        assert client.get("/api/settings", headers=actor.headers).status_code == 403


def test_retention_purges_old_raw_files_only(client, session):
    admin = signup(client)
    agreement = agreement_world(client, session, admin)  # creates import batches with stored files
    doc_id = upload(client, admin, agreement.id, "a.txt", DEMO_CONTRACT.read_bytes()).json()["id"]
    client.put("/api/settings", headers=admin.headers, json={"retention_days": 30})

    assert org_settings.purge_expired_files(session) == {"import_files": 0, "documents": 0}  # nothing old yet
    later = datetime.now(UTC) + timedelta(days=31)
    totals = org_settings.purge_expired_files(session, now=later)
    session.commit()
    assert totals["documents"] == 1 and totals["import_files"] >= 4
    assert client.get(f"/api/documents/{doc_id}/original", headers=admin.headers).status_code == 410
    session.expire_all()
    assert session.get(Document, uuid.UUID(doc_id)).text_extracted is None
    assert {b.file_ref for b in session.scalars(select(ImportBatch))} == {"purged"}
    # Canonical records (and so agreements, terms and evidence) are kept.
    assert len(client.get("/api/agreements", headers=admin.headers).json()) == 1
    assert "retention.purged" in {e["action"] for e in client.get("/api/audit", headers=admin.headers).json()}


def _org_row_counts(session, org_id) -> dict[str, int]:
    tables = session.execute(text(
        "SELECT table_name FROM information_schema.columns WHERE column_name = 'org_id' AND table_schema = 'public'"
    )).scalars().all()
    return {t: session.execute(text(f'SELECT count(*) FROM "{t}" WHERE org_id = :o'), {"o": org_id}).scalar()
            for t in tables}


def test_delete_organization_data_leaves_only_a_tombstone(client, session):
    admin = signup(client, "Doomed Ltd")
    agreement = agreement_world(client, session, admin)
    upload(client, admin, agreement.id, "a.txt", DEMO_CONTRACT.read_bytes())
    analyst = add_user(client, admin, "analyst")
    keeper = signup(client, "Unaffected Ltd")
    keeper_before = _org_row_counts(session, keeper.org_id)

    r = client.post("/api/settings/delete-organization-data", headers=admin.headers, json={"confirm_short_code": "nope"})
    assert r.status_code == 422
    r = client.post("/api/settings/delete-organization-data", headers=admin.headers,
                    json={"confirm_short_code": "doomedlt"})
    assert r.status_code == 200 and r.json()["files_removed"] >= 5

    session.expire_all()
    counts = _org_row_counts(session, admin.org_id)
    assert counts.pop("audit_event") == 1
    assert all(n == 0 for n in counts.values()), counts
    org = session.get(Organization, uuid.UUID(admin.org_id))
    assert org.name == "Doomed Ltd" and "data_deleted_at" in org.settings
    tombstone = session.scalar(select(func.min(text("action"))).select_from(text("audit_event"))
                               .where(text("org_id = :o")).params(o=admin.org_id))
    assert tombstone == "organization.data_deleted"
    assert audit.verify(session, org.id) == {"ok": True, "events": 1, "first_bad_seq": None}
    assert not (get_store().root / admin.org_id).exists()  # type: ignore[attr-defined]
    for actor in (admin, analyst):
        assert client.get("/api/auth/me", headers=actor.headers).status_code == 401
    assert _org_row_counts(session, keeper.org_id) == keeper_before

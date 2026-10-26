"""BE-031: AI mapping suggestions (never auto-applied) and labelled finding summaries never read by calculations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.domains.access.models import Organization
from app.domains.ai.assist import MappingSuggestion
from app.domains.ai.stub import StubProvider
from app.domains.ingestion.models import DataSource
from app.domains.rules.models import Finding
from app.seed_demo import main as seed
from tests.engine_helpers import findings, run
from tests.ingest_helpers import upload
from tests.test_recovery import _demo
from tests.test_workflow import post

MESSY = ("Shipment Ref,Account,Contract,SKU,Qty,Ship Date,Bill By,Currency\n"
         "SHP-1040,RS-C1,RS-A1,WIDGET-B,70,2026-09-03,2026-09-03,USD\n"
         "SHP-1041,RS-C1,RS-A1,WIDGET-A,120,2026-09-17,2026-09-17,USD\n")


def _beyon_upload(client, session):
    seed([])
    admin = _demo(client, "admin", "beyon.com")
    src = session.scalar(select(DataSource).where(DataSource.name == "Manual uploads",
                                                  DataSource.org_id == admin.org_id))
    return admin, upload(client, admin, str(src.id), "billable_event", MESSY)


def test_suggestions_cover_unmapped_columns_and_are_not_applied(client, session):
    admin, batch = _beyon_upload(client, session)
    assert set(batch["profile"]["unmapped_columns"]) == {"Shipment Ref", "Account"}
    r = client.get(f"/api/imports/{batch['id']}/mapping-suggestions", headers=admin.headers)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "stub" and body["external"] is False
    got = {s["column"]: (s["field"], s["reason"]) for s in body["suggestions"]}
    assert got["Account"][0] == "customer_id" and "matches an existing customer id" in got["Account"][1]
    assert got["Shipment Ref"][0] == "event_id"
    # Not applied: the import's mapping and missing fields are unchanged until the admin saves.
    after = client.get(f"/api/imports/{batch['id']}", headers=admin.headers).json()
    assert after["profile"]["mapping"] == batch["profile"]["mapping"]
    assert after["profile"]["missing_required_fields"] == ["event_id", "customer_id"]


def test_untrusted_provider_suggestions_are_filtered(client, session, monkeypatch):
    admin, batch = _beyon_upload(client, session)
    # Remove deterministic evidence so the provider's answer is what's left.
    monkeypatch.setattr("app.domains.ai.router.value_evidence", lambda *a, **k: [])

    def bad(self, columns, samples, spec, taken):
        return [MappingSuggestion(column="Shipment Ref", field="event_id", confidence=0.9, reason="ok"),
                MappingSuggestion(column="Not a column", field="customer_id", confidence=1, reason="invented"),
                MappingSuggestion(column="Account", field="drop_table", confidence=1, reason="invented field"),
                MappingSuggestion(column="Account", field="item_code", confidence=1, reason="already mapped")]

    monkeypatch.setattr(StubProvider, "suggest_mapping", bad)
    got = client.get(f"/api/imports/{batch['id']}/mapping-suggestions", headers=admin.headers).json()["suggestions"]
    assert [(s["column"], s["field"]) for s in got] == [("Shipment Ref", "event_id")]
    analyst = _demo(client, "analyst", "beyon.com")
    assert client.get(f"/api/imports/{batch['id']}/mapping-suggestions", headers=analyst.headers).status_code == 403


def test_summary_is_stored_labelled_and_never_affects_values(client, session):
    seed([])
    jm = session.scalar(select(Organization).where(Organization.name == "JM"))
    run(jm.id, date(2026, 10, 26))
    analyst = _demo(client, "analyst", "jm.com")
    fid = next(i["id"] for i in client.get("/api/findings", headers=analyst.headers).json()["items"]
               if i["check_type"] == "incorrect_rate")
    r = client.post(f"/api/findings/{fid}/summary", headers=analyst.headers)
    assert r.status_code == 200 and r.json()["provider"] == "stub"
    assert "Wrong contracted rate for Bluefin Logistics" in r.json()["ai_summary"]
    assert client.get(f"/api/findings/{fid}", headers=analyst.headers).json()["ai_summary"] == r.json()["ai_summary"]

    # A summary claiming a different amount changes nothing: calculations never read ai_summary (GR-02).
    f = session.get(Finding, fid)
    f.ai_summary = "AI says the customer owes 999999.00 and the rate should be 0."
    session.commit()
    again = run(jm.id, date(2026, 10, 26))
    assert again.stats["new"] == 0
    session.expire_all()
    assert session.get(Finding, fid).value == Decimal("600")
    assert "ai.summary_generated" in {e["action"] for e in
                                      client.get("/api/audit", headers=_demo(client, "admin", "jm.com").headers).json()}

    # Allowed on a final finding too (it's not evidence), and isolated per org.
    post(client, analyst, fid, "reject", {"note": "test"})
    assert client.post(f"/api/findings/{fid}/summary", headers=analyst.headers).status_code == 200
    beyon = _demo(client, "analyst", "beyon.com")
    assert client.post(f"/api/findings/{fid}/summary", headers=beyon.headers).status_code == 404
    assert client.post(f"/api/findings/{fid}/summary",
                       headers=_demo(client, "executive", "jm.com").headers).status_code == 403
    assert len(findings(session, jm.id)) == 6

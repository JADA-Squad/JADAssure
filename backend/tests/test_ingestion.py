"""BE-006 / BE-007: sources, mapping, profiling, validated idempotent commit (FR-05..FR-08, GR-11)."""

import csv
import io
import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.core import jobs
from app.core.storage import get_store
from app.domains.contracts.models import CommercialTerm
from app.domains.ingestion.models import Customer, ImportBatch, InvoiceLine
from tests.factories import add_user, signup
from tests.ingest_helpers import CUSTOMERS, commit, create_source, load, upload


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model))


# ---------------------------------------------------------------- profiling (FR-06) and mapping (FR-05)

def test_profile_suggests_mapping_and_reports_gaps(client):
    admin = signup(client)
    src = create_source(client, admin)
    load(client, admin, src, "customer", CUSTOMERS)

    csv_text = (
        "Invoice Number,date,customer_id,ccy,Notes\n"
        "INV-1,2026-01-31,C1,USD,first\n"
        "INV-2,31/01/2026,C9,USD,\n"
    )
    batch = upload(client, admin, src, "invoice", csv_text)
    p = batch["profile"]

    assert batch["status"] == "profiled"
    assert p["mapping"] == {"Invoice Number": "number", "date": "invoice_date", "customer_id": "customer_id",
                            "ccy": "currency"}
    assert p["unmapped_columns"] == ["Notes"]
    assert p["missing_required_fields"] == ["invoice_id"]
    assert p["can_commit"] is False
    date_stat = next(f for f in p["fields"] if f["field"] == "invoice_date")
    assert date_stat["invalid_count"] == 1 and date_stat["invalid_samples"][0]["row"] == 3
    assert p["unmatched_references"] == [
        {"field": "customer_id", "target": "customer", "distinct": 1, "rows": 1, "samples": ["C9"]}
    ]


def test_saved_mapping_is_reused_for_next_upload_from_same_source(client):
    admin = signup(client)
    src = create_source(client, admin)
    odd = "Acct Ref,Acct,Money\nC1,Halcyon,USD\n"
    batch = upload(client, admin, src, "customer", odd)
    assert batch["profile"]["missing_required_fields"]  # nothing recognisable

    mapping = {"Acct Ref": "customer_id", "Acct": "name", "Money": "currency"}
    res = client.put(f"/api/imports/{batch['id']}/mapping", headers=admin.headers, json={"mapping": mapping})
    assert res.status_code == 200 and res.json()["profile"]["can_commit"] is True

    again = upload(client, admin, src, "customer", odd)
    assert again["profile"]["mapping"] == mapping
    other_source = create_source(client, admin, "Other system")
    assert upload(client, admin, other_source, "customer", odd)["profile"]["mapping"] == {}


def test_invalid_mappings_are_rejected(client):
    admin = signup(client)
    src = create_source(client, admin)
    batch = upload(client, admin, src, "customer", CUSTOMERS)
    for bad in ({"nope": "name"}, {"name": "not_a_field"}, {"customer_id": "name", "name": "name"}):
        assert client.put(f"/api/imports/{batch['id']}/mapping", headers=admin.headers,
                          json={"mapping": bad}).status_code == 422


def test_unreadable_files_are_rejected(client):
    admin = signup(client)
    src = create_source(client, admin)
    res = client.post(f"/api/data-sources/{src}/imports", headers=admin.headers, data={"record_type": "customer"},
                      files={"file": ("x.csv", "naïve".encode("latin-1"), "text/csv")})
    assert res.status_code == 422 and "UTF-8" in res.json()["detail"]
    res = client.post(f"/api/data-sources/{src}/imports", headers=admin.headers, data={"record_type": "customer"},
                      files={"file": ("x.csv", b"a,a\n1,2\n", "text/csv")})
    assert res.status_code == 422 and "duplicate" in res.json()["detail"]


# ---------------------------------------------------------------- commit (FR-07)

def test_commit_validates_rows_and_reports_errors(client, session):
    admin = signup(client)
    src = create_source(client, admin)
    load(client, admin, src, "customer", CUSTOMERS)
    load(client, admin, src, "invoice", "invoice_id,customer_id,number,invoice_date,currency\nI1,C1,INV-1,2026-02-01,USD\n")

    lines = (
        "line_id,invoice_id,item_code,quantity,unit_price,discount_pct,net_amount,tax_amount\n"
        "L1,I1,SEAT,10,45.00,,450.00,90.00\n"
        "L2,I1,SEAT,ten,45.00,,450.00,\n"
        "L3,I404,SEAT,1,45,,45,\n"
        "=HYPERLINK(\"x\"),I1,,1,1,,1,\n"
    )
    batch = load(client, admin, src, "invoice_line", lines)
    assert batch["counts"] == {"inserted": 1, "updated": 0, "unchanged": 0, "rejected": 3}
    assert batch["has_error_report"] is True

    text = client.get(f"/api/imports/{batch['id']}/errors.csv", headers=admin.headers).text
    report = list(csv.reader(io.StringIO(text)))
    assert report[0] == ["row_number", "source_record_id", "errors"]
    assert report[1] == ["3", "L2", "quantity: not a number"]
    assert report[2] == ["4", "L3", "invoice_id: no invoice with id 'I404'"]
    assert report[3] == ["5", "'=HYPERLINK(\"x\")", "item_code: required"]  # formula neutralised (GR-07)

    line = session.scalar(select(InvoiceLine))
    assert line.net_amount == Decimal("450.0000") and line.discount_pct == Decimal("0")
    assert line.source_payload["unit_price"] == "45.00" and line.import_id == uuid.UUID(batch["id"])

    history = client.get(f"/api/imports?data_source_id={src}", headers=admin.headers).json()
    assert [h["record_type"] for h in history] == ["invoice_line", "invoice", "customer"]


def test_commit_requires_complete_mapping_and_runs_once(client):
    admin = signup(client)
    src = create_source(client, admin)
    incomplete = upload(client, admin, src, "customer", "customer_id,name\nC1,X\n")
    assert client.post(f"/api/imports/{incomplete['id']}/commit", headers=admin.headers).status_code == 422
    ok = upload(client, admin, src, "customer", CUSTOMERS)
    commit(client, admin, ok["id"])
    assert client.post(f"/api/imports/{ok['id']}/commit", headers=admin.headers).status_code == 409
    assert client.put(f"/api/imports/{ok['id']}/mapping", headers=admin.headers,
                      json={"mapping": {}}).status_code == 409


# ---------------------------------------------------------------- idempotency (FR-08, GR-11)

def test_reimport_creates_no_duplicates_and_detects_changes(client, session):
    admin = signup(client)
    src = create_source(client, admin)
    first = load(client, admin, src, "customer", CUSTOMERS)
    assert first["counts"]["inserted"] == 2

    again = upload(client, admin, src, "customer", CUSTOMERS)
    assert again["profile"]["existing_records"] == 2 and again["profile"]["new_records"] == 0
    assert commit(client, admin, again["id"])["counts"] == {"inserted": 0, "updated": 0, "unchanged": 2, "rejected": 0}
    assert _count(session, Customer) == 2

    # Formatting-only differences (case, trailing zeros) are not changes; a real change is.
    changed = "customer_id,name,currency\nC1,Halcyon Retail,usd\nC2,Bluefin Logistics Ltd,USD\n"
    assert load(client, admin, src, "customer", changed)["counts"] == {"inserted": 0, "updated": 1, "unchanged": 1,
                                                                        "rejected": 0}
    session.expire_all()
    assert {c.name for c in session.scalars(select(Customer))} == {"Halcyon Retail", "Bluefin Logistics Ltd"}


def test_same_ids_from_different_sources_are_separate_records(client, session):
    admin = signup(client)
    load(client, admin, create_source(client, admin, "A"), "customer", CUSTOMERS)
    load(client, admin, create_source(client, admin, "B"), "customer", CUSTOMERS)
    assert _count(session, Customer) == 4


def test_imported_terms_are_confirmed(client, session):
    admin = signup(client)
    src = create_source(client, admin)
    load(client, admin, src, "customer", CUSTOMERS)
    load(client, admin, src, "agreement",
         "agreement_id,customer_id,title,start_date,billing_frequency,currency\nA1,C1,MSA,2026-01-01,monthly,USD\n")
    load(client, admin, src, "agreement_version",
         "version_id,agreement_id,version_no,effective_from\nV1,A1,1,2026-01-01\n")
    batch = load(client, admin, src, "commercial_term",
                 "term_id,version_id,term_type,value,effective_from,max_value\n"
                 "T1,V1,credit_policy,500,2026-01-01,2000.00\n"
                 "T2,V1,rate,45,2026-03-01,\n")
    assert batch["counts"]["inserted"] == 2
    terms = {t.source_record_id: t for t in session.scalars(select(CommercialTerm))}
    assert {t.status for t in terms.values()} == {"confirmed"}
    assert terms["T1"].origin == "import" and str(terms["T1"].confirmed_by) == admin.user_id
    assert terms["T1"].params == {"max_value": "2000"}


def test_date_order_is_validated(client):
    admin = signup(client)
    src = create_source(client, admin)
    load(client, admin, src, "customer", CUSTOMERS)
    batch = load(client, admin, src, "agreement",
                 "agreement_id,customer_id,title,start_date,end_date,billing_frequency,currency\n"
                 "A1,C1,MSA,2026-06-01,2026-01-01,monthly,USD\n")
    assert batch["counts"]["rejected"] == 1


# ---------------------------------------------------------------- failures and retry (FR-11)

def test_failed_import_is_visible_and_retryable(client, session):
    admin = signup(client)
    src = create_source(client, admin)
    batch = upload(client, admin, src, "customer", CUSTOMERS)
    stored = session.get(ImportBatch, uuid.UUID(batch["id"]))
    data = get_store().get(stored.file_ref)
    get_store().delete(stored.file_ref)

    failed = commit(client, admin, batch["id"])
    assert failed["status"] == "failed" and "Could not read the uploaded file" in failed["error"]

    path = get_store()._path(stored.file_ref)  # type: ignore[attr-defined]
    path.write_bytes(data)  # the file is back (e.g. storage recovered)
    assert client.post(f"/api/jobs/{failed['job_id']}/retry", headers=admin.headers).status_code == 200
    assert client.get(f"/api/imports/{batch['id']}", headers=admin.headers).json()["status"] == "queued"
    jobs.drain()
    done = client.get(f"/api/imports/{batch['id']}", headers=admin.headers).json()
    assert done["status"] == "succeeded" and done["counts"]["inserted"] == 2 and done["error"] is None


# ---------------------------------------------------------------- isolation (GR-06)

def test_sources_and_imports_are_org_scoped(client):
    a = signup(client)
    src = create_source(client, a)
    batch = upload(client, a, src, "customer", CUSTOMERS)
    b = signup(client)
    assert client.get("/api/data-sources", headers=b.headers).json() == []
    assert client.get(f"/api/data-sources/{src}", headers=b.headers).status_code == 404
    assert client.get(f"/api/imports/{batch['id']}", headers=b.headers).status_code == 404
    assert client.post(f"/api/imports/{batch['id']}/commit", headers=b.headers).status_code == 404
    res = client.post(f"/api/data-sources/{src}/imports", headers=b.headers, data={"record_type": "customer"},
                      files={"file": ("x.csv", CUSTOMERS.encode(), "text/csv")})
    assert res.status_code == 404
    analyst = add_user(client, a, "analyst")
    assert client.get("/api/data-sources", headers=analyst.headers).status_code == 403


def test_references_never_resolve_across_orgs(client, session):
    a = signup(client)
    load(client, a, create_source(client, a), "customer", CUSTOMERS)
    b = signup(client)
    src_b = create_source(client, b)
    batch = upload(client, b, src_b, "invoice",
                   "invoice_id,customer_id,number,invoice_date,currency\nI1,C1,INV-1,2026-02-01,USD\n")
    assert batch["profile"]["unmatched_references"][0]["samples"] == ["C1"]
    assert commit(client, b, batch["id"])["counts"]["rejected"] == 1

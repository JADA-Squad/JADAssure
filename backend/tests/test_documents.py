"""BE-027: contract upload via DocumentStore with sha256, size/type limits and text extraction (FR-13, GR-07)."""

import hashlib

from app.domains.contracts.models import Document
from tests.doc_helpers import DEMO_CONTRACT, agreement_world, minimal_docx, minimal_pdf, upload
from tests.factories import add_user, signup


def test_txt_docx_and_pdf_are_stored_and_text_extracted(client, session):
    admin = signup(client)
    agreement = agreement_world(client, session, admin)
    txt = DEMO_CONTRACT.read_bytes()
    files = {
        "amendment.txt": (txt, "Senior consultant rate: USD 195.00 per hour"),
        "amendment.docx": (minimal_docx(["Analyst rate: USD 130.00 per hour.", "Signed."]), "Analyst rate: USD 130.00"),
        "amendment.pdf": (minimal_pdf("Senior consultant rate: USD 200.00 per hour"), "USD 200.00 per hour"),
    }
    for name, (data, expected_text) in files.items():
        r = upload(client, admin, agreement.id, name, data)
        assert r.status_code == 201, (name, r.text)
        body = r.json()
        assert body["sha256"] == hashlib.sha256(data).hexdigest() and body["size_bytes"] == len(data)
        doc = session.get(Document, body["id"])
        assert expected_text in doc.text_extracted, name
        original = client.get(f"/api/documents/{body['id']}/original", headers=admin.headers)
        assert original.status_code == 200 and original.content == data
    listed = client.get(f"/api/agreements/{agreement.id}/documents", headers=admin.headers).json()
    assert {d["filename"] for d in listed} == set(files)
    assert "document.uploaded" in {e["action"] for e in client.get("/api/audit", headers=admin.headers).json()}


def test_type_spoofing_size_and_duplicates_are_rejected(client, session):
    admin = signup(client)
    agreement = agreement_world(client, session, admin)
    cases = {
        "malware.pdf": b"MZ\x90\x00 this is an exe",
        "fake.docx": b"PK\x03\x04 not really a zip",
        "notes.exe": b"hello",
        "binary.txt": b"abc\x00def",
        "scan.pdf": minimal_pdf(""),
    }
    for name, data in cases.items():
        r = upload(client, admin, agreement.id, name, data)
        assert r.status_code == 422, (name, r.text)
    big = b"%PDF-" + b"0" * (10 * 1024 * 1024)
    assert upload(client, admin, agreement.id, "big.pdf", big).status_code == 413
    data = DEMO_CONTRACT.read_bytes()
    assert upload(client, admin, agreement.id, "a.txt", data).status_code == 201
    assert upload(client, admin, agreement.id, "copy.txt", data).status_code == 409


def test_document_roles_and_isolation(client, session):
    admin = signup(client)
    agreement = agreement_world(client, session, admin)
    data = DEMO_CONTRACT.read_bytes()
    analyst = add_user(client, admin, "analyst")
    assert upload(client, analyst, agreement.id, "a.txt", data).status_code == 403
    commercial = add_user(client, admin, "commercial")
    doc_id = upload(client, commercial, agreement.id, "a.txt", data).json()["id"]
    assert client.get(f"/api/agreements/{agreement.id}/documents", headers=analyst.headers).status_code == 200
    other = signup(client)
    assert upload(client, other, agreement.id, "b.txt", data).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/original", headers=other.headers).status_code == 404

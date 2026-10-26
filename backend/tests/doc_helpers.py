"""Builders for real PDF/DOCX/TXT test documents and an agreement to attach them to."""

import io
import pathlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.contracts.models import Agreement
from tests.factories import Actor
from tests.ingest_helpers import CUSTOMERS, create_source, load

DEMO_CONTRACT = pathlib.Path("/demo-data/northwind-advisory/contracts/orchard-sow-amendment-1.txt")


def minimal_pdf(text: str) -> bytes:
    """A small valid single-page PDF with a text layer (no external libraries)."""
    stream = f"BT /F1 11 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def minimal_docx(paragraphs: list[str]) -> bytes:
    import docx

    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def agreement_world(client, session: Session, admin: Actor) -> Agreement:
    src = create_source(client, admin)
    load(client, admin, src, "customer", CUSTOMERS)
    load(client, admin, src, "agreement",
         "agreement_id,customer_id,title,start_date,billing_frequency,currency\nA1,C1,Advisory SOW,2026-01-01,monthly,USD\n")
    load(client, admin, src, "agreement_version", "version_id,agreement_id,version_no,effective_from\nV1,A1,1,2026-01-01\n")
    load(client, admin, src, "commercial_term",
         "term_id,version_id,item_code,term_type,value,unit,currency,effective_from\n"
         "T1,V1,SENIOR-CONSULT,rate,180,hour,USD,2026-01-01\nT2,V1,ANALYST,rate,120,hour,USD,2026-01-01\n")
    session.expire_all()
    return session.scalar(select(Agreement).where(Agreement.org_id == admin.org_id))


def upload(client, actor: Actor, agreement_id, filename: str, data: bytes):
    return client.post(f"/api/agreements/{agreement_id}/documents", headers=actor.headers,
                       files={"file": (filename, data, "application/octet-stream")})

"""Helpers to load small CSV worlds and run checks synchronously."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.db import new_session
from app.domains.rules import engine
from app.domains.rules.models import CheckRun, Finding
from tests.factories import Actor
from tests.ingest_helpers import create_source, load

BASE = {
    "customer": "customer_id,name,currency\nC1,Acme,USD\n",
    "agreement": "agreement_id,customer_id,title,start_date,billing_frequency,currency\n"
                 "A1,C1,Monthly MSA,2026-01-01,monthly,USD\nA2,C1,Supply,2026-01-01,per_event,USD\n",
    "agreement_version": "version_id,agreement_id,version_no,effective_from\nV1,A1,1,2026-01-01\nV2,A2,1,2026-01-01\n",
}


def load_world(client, admin: Actor, extra: dict[str, str]) -> str:
    src = create_source(client, admin)
    for record_type in ("customer", "agreement", "agreement_version", "commercial_term", "billable_event",
                        "invoice", "invoice_line", "credit"):
        text = extra.get(record_type, BASE.get(record_type))
        if text:
            batch = load(client, admin, src, record_type, text)
            assert batch["counts"]["rejected"] == 0, (record_type, batch["counts"])
    return src


def run(org_id: str | uuid.UUID, as_of: date) -> CheckRun:
    with new_session() as s:
        r = engine.request_run(s, uuid.UUID(str(org_id)), trigger="manual", requested_by=None, as_of=as_of)
        s.commit()
        run_id = r.id
    jobs.drain()
    with new_session() as s:
        return s.get(CheckRun, run_id)


def findings(session: Session, org_id: str | uuid.UUID) -> list[Finding]:
    session.expire_all()
    return list(session.scalars(select(Finding).where(Finding.org_id == uuid.UUID(str(org_id)))
                                .order_by(Finding.check_type, Finding.value)))

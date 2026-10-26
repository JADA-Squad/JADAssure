"""Proposed-term extraction and human confirmation (BE-029, BE-030, FR-13, FR-14, GR-02, GR-03, GR-07).

Every provider result is untrusted. A proposed term survives only if it is schema-valid, its
passage appears verbatim in the document (whitespace-insensitive) and an agreement version covers
its start date. Survivors are stored `proposed`, so the engine can't see them (confirmed_terms
only). A person with manage_contracts confirms (optionally editing) or rejects each one, and both
actions are audited.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.models import Job
from app.core.tenancy import TenantContext
from app.domains.access.models import Organization
from app.domains.ai.provider import AIProvider, ExtractionContext, ProviderError
from app.domains.ai.registry import provider_for
from app.domains.audit import service as audit
from app.domains.contracts.models import Agreement, AgreementVersion, CommercialTerm, Document
from app.domains.contracts.terms import applicable_version
from app.domains.ingestion.models import BillableEvent, Invoice, InvoiceLine

EXTRACT_JOB = "extract_terms"


def _norm(s: str) -> str:
    return " ".join(s.split())


def _known_items(session: Session, agreement: Agreement) -> tuple[str, ...]:
    codes: set[str] = set()
    versions = select(AgreementVersion.id).where(AgreementVersion.agreement_id == agreement.id)
    codes.update(c for c in session.scalars(select(CommercialTerm.item_code).where(
        CommercialTerm.agreement_version_id.in_(versions), CommercialTerm.item_code.is_not(None))))
    codes.update(session.scalars(select(BillableEvent.item_code).where(BillableEvent.customer_id == agreement.customer_id)))
    codes.update(session.scalars(select(InvoiceLine.item_code).join(Invoice, Invoice.id == InvoiceLine.invoice_id)
                                 .where(Invoice.customer_id == agreement.customer_id)))
    return tuple(sorted(codes))


def request_extraction(session: Session, ctx: TenantContext, doc: Document) -> None:
    doc.extraction_status = "queued"
    doc.extraction_error = None
    jobs.enqueue(session, kind=EXTRACT_JOB, org_id=ctx.org_id, payload={"document_id": str(doc.id)})


def run_extraction(session: Session, doc: Document, provider: AIProvider | None = None) -> dict[str, Any]:
    org = session.get(Organization, doc.org_id)
    agreement = session.get(Agreement, doc.agreement_id)
    if org is None or agreement is None or not doc.text_extracted:
        raise jobs.JobError("The document or its agreement is no longer available")
    provider = provider or provider_for(org.settings)
    ctx = ExtractionContext(org_id=org.id, agreement_title=agreement.title, currency=agreement.currency,
                            known_item_codes=_known_items(session, agreement))
    doc.extraction_status = "running"
    try:
        result = provider.extract_terms(doc.text_extracted, ctx)
    except ProviderError as exc:
        raise jobs.JobError(str(exc)) from None

    text = _norm(doc.text_extracted)
    existing = {(t.term_type, _norm(t.source_passage or ""), t.value) for t in session.scalars(
        select(CommercialTerm).where(CommercialTerm.document_id == doc.id))}
    stats: dict[str, Any] = {"provider": provider.name, "external": provider.external, "proposed": 0,
                             "ambiguous": 0, "discarded": 0, "discard_reasons": []}

    def discard(reason: str) -> None:
        stats["discarded"] += 1
        if reason not in stats["discard_reasons"]:
            stats["discard_reasons"].append(reason)

    for t in result.terms:
        if _norm(t.passage) not in text:
            discard("passage not found verbatim in the document")  # fabricated or paraphrased (GR-07)
            continue
        try:
            value = Decimal(t.value.replace(",", ""))
        except InvalidOperation:
            discard("value is not a number")
            continue
        if value < 0 or (t.effective_to and t.effective_from and t.effective_to < t.effective_from):
            discard("negative value or inverted dates")
            continue
        if (t.term_type, _norm(t.passage), value) in existing:
            discard("already proposed from this document")
            continue
        effective_from = t.effective_from or agreement.start_date
        version = applicable_version(session, org.id, agreement.id, effective_from)
        if version is None:
            discard("no agreement version covers the term's start date")
            continue
        item = t.item_code if t.item_code in ctx.known_item_codes else None
        ambiguous, reason = t.ambiguous, t.ambiguity_reason
        if t.item_code and item is None:
            ambiguous, reason = True, reason or f"Unknown item '{t.item_code}'"
        session.add(CommercialTerm(
            org_id=org.id, agreement_version_id=version.id, item_code=item, term_type=t.term_type, value=value,
            unit=t.unit, currency=t.currency or (agreement.currency if t.term_type in ("rate", "credit_policy") else None),
            effective_from=effective_from, effective_to=t.effective_to, params={}, status="proposed",
            ambiguous=ambiguous, ambiguity_reason=reason if ambiguous else None, source_passage=t.passage,
            document_id=doc.id, origin="extraction",
        ))
        existing.add((t.term_type, _norm(t.passage), value))
        stats["proposed"] += 1
        stats["ambiguous"] += int(ambiguous)
    doc.extraction_status = "succeeded"
    doc.extraction_stats = stats
    session.flush()
    audit.record(session, org_id=org.id, actor_id=None, action="document.terms_proposed", entity="document",
                 entity_id=doc.id, payload={k: stats[k] for k in ("provider", "external", "proposed", "ambiguous",
                                                                   "discarded")})
    return stats


def _handler(session: Session, job: Job) -> None:
    doc = session.get(Document, uuid.UUID(job.payload["document_id"]))
    if doc is None or doc.org_id != job.org_id:
        raise jobs.JobError("Document not found")
    run_extraction(session, doc)


def _on_failure(session: Session, job: Job) -> None:
    doc = session.get(Document, uuid.UUID(job.payload["document_id"]))
    if doc is not None:
        doc.extraction_status = "failed"
        doc.extraction_error = job.last_error


def _on_retry(session: Session, job: Job) -> None:
    doc = session.get(Document, uuid.UUID(job.payload["document_id"]))
    if doc is not None:
        doc.extraction_status = "queued"
        doc.extraction_error = None


jobs.register(EXTRACT_JOB, on_failure=_on_failure, on_retry=_on_retry)(_handler)


# ---------------------------------------------------------------- confirmation (BE-030)

EDITABLE = ("value", "item_code", "unit", "currency", "effective_from", "effective_to")


def _proposed(session: Session, ctx: TenantContext, term_id: uuid.UUID) -> CommercialTerm:
    term = session.scalar(select(CommercialTerm).where(CommercialTerm.id == term_id,
                                                       CommercialTerm.org_id == ctx.org_id).with_for_update())
    if term is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if term.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This term is already {term.status}")
    return term


def confirm(session: Session, ctx: TenantContext, term_id: uuid.UUID, edits: dict[str, Any],
            note: str | None) -> CommercialTerm:
    term = _proposed(session, ctx, term_id)
    changed: dict[str, list[str | None]] = {}
    for field in EDITABLE:
        if field in edits and edits[field] != getattr(term, field):
            changed[field] = [None if getattr(term, field) is None else str(getattr(term, field)),
                              None if edits[field] is None else str(edits[field])]
            setattr(term, field, edits[field])
    if term.term_type in ("rate", "escalation") and not term.item_code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the item this rate applies to before confirming")
    if term.effective_to and term.effective_to < term.effective_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The end date is before the start date")
    if term.value < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Value can't be negative")
    term.status = "confirmed"
    term.confirmed_by = ctx.user_id
    term.confirmed_at = datetime.now(UTC)
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="term.confirmed", entity="commercial_term",
                 entity_id=term.id, payload={"edited": changed, "was_ambiguous": term.ambiguous,
                                             "note_length": len(note or "")})
    return term


def reject(session: Session, ctx: TenantContext, term_id: uuid.UUID, reason: str) -> CommercialTerm:
    if not reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A reason is required")
    term = _proposed(session, ctx, term_id)
    term.status = "rejected"
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="term.rejected", entity="commercial_term",
                 entity_id=term.id, payload={"reason_length": len(reason)})
    return term


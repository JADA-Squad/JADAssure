import uuid
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.permissions import Cap, require
from app.core.storage import get_store
from app.domains.contracts import documents
from app.domains.contracts.models import Agreement, AgreementVersion, CommercialTerm, Document
from app.domains.contracts.schemas import AgreementDetailOut, AgreementSummaryOut, DocumentOut, TermOut, VersionOut
from app.domains.contracts.terms import resolve_terms
from app.domains.ingestion.models import Customer

router = APIRouter(prefix="/api/agreements", tags=["agreements"])

ViewAgreements = Depends(require(Cap.VIEW_AGREEMENTS))


def _summary(agreement: Agreement, customer_name: str, versions: list[AgreementVersion],
             terms: list[CommercialTerm]) -> dict:
    return {
        "id": agreement.id,
        "source_record_id": agreement.source_record_id,
        "title": agreement.title,
        "customer_id": agreement.customer_id,
        "customer_name": customer_name,
        "start_date": agreement.start_date,
        "end_date": agreement.end_date,
        "billing_frequency": agreement.billing_frequency,
        "currency": agreement.currency,
        "version_count": len(versions),
        "term_counts": dict(Counter(t.status for t in terms)),
    }


@router.get("", response_model=list[AgreementSummaryOut])
def list_agreements(ctx: TenantContext = ViewAgreements, session: Session = Depends(get_session)):
    rows = session.execute(
        scoped(Agreement, ctx).add_columns(Customer.name).join(Customer, Customer.id == Agreement.customer_id)
        .order_by(Customer.name, Agreement.title)
    ).all()
    versions = list(session.scalars(scoped(AgreementVersion, ctx)))
    terms = list(session.scalars(scoped(CommercialTerm, ctx)))
    version_agreement = {v.id: v.agreement_id for v in versions}
    out = []
    for agreement, customer_name in rows:
        a_versions = [v for v in versions if v.agreement_id == agreement.id]
        a_terms = [t for t in terms if version_agreement.get(t.agreement_version_id) == agreement.id]
        out.append(_summary(agreement, customer_name, a_versions, a_terms))
    return out


@router.get("/{agreement_id}", response_model=AgreementDetailOut)
def get_agreement(agreement_id: uuid.UUID, ctx: TenantContext = ViewAgreements, session: Session = Depends(get_session)):
    agreement = get_scoped(session, Agreement, agreement_id, ctx)
    customer = session.get(Customer, agreement.customer_id)
    versions = list(session.scalars(
        scoped(AgreementVersion, ctx).where(AgreementVersion.agreement_id == agreement.id)
        .order_by(AgreementVersion.version_no)
    ))
    terms = list(session.scalars(
        scoped(CommercialTerm, ctx).where(CommercialTerm.agreement_version_id.in_([v.id for v in versions]))
        .order_by(CommercialTerm.term_type, CommercialTerm.item_code, CommercialTerm.effective_from)
    )) if versions else []
    detail = _summary(agreement, customer.name if customer else "", versions, terms)
    detail["versions"] = [
        VersionOut.model_validate(v).model_copy(
            update={"terms": [TermOut.model_validate(t) for t in terms if t.agreement_version_id == v.id]}
        )
        for v in versions
    ]
    return detail


@router.get("/{agreement_id}/terms", response_model=list[TermOut])
def terms_in_effect(
    agreement_id: uuid.UUID,
    on: date = Query(..., description="Date to resolve terms for (YYYY-MM-DD)"),
    item_code: str | None = Query(None, max_length=80),
    ctx: TenantContext = ViewAgreements,
    session: Session = Depends(get_session),
):
    """The confirmed terms the engine would apply on a date (FR-12)."""
    agreement = get_scoped(session, Agreement, agreement_id, ctx)
    return resolve_terms(session, ctx.org_id, agreement.id, on, item_code=item_code)



# ---------------------------------------------------------------- contract documents (BE-027)

@router.post("/{agreement_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(agreement_id: uuid.UUID, file: UploadFile = File(...),
                          ctx: TenantContext = Depends(require(Cap.MANAGE_CONTRACTS)),
                          session: Session = Depends(get_session)):
    agreement = get_scoped(session, Agreement, agreement_id, ctx)
    data = await file.read(documents.MAX_BYTES + 1)
    if len(data) > documents.MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 10 MB")
    doc = documents.upload(session, ctx, agreement, file.filename or "contract", data)
    session.commit()
    return doc


@router.get("/{agreement_id}/documents", response_model=list[DocumentOut])
def list_documents(agreement_id: uuid.UUID, ctx: TenantContext = ViewAgreements, session: Session = Depends(get_session)):
    agreement = get_scoped(session, Agreement, agreement_id, ctx)
    return list(session.scalars(scoped(Document, ctx).where(Document.agreement_id == agreement.id)
                                .order_by(Document.created_at.desc())))


documents_router = APIRouter(prefix="/api/documents", tags=["agreements"])


@documents_router.get("/{document_id}/original", response_class=Response)
def download_original(document_id: uuid.UUID, ctx: TenantContext = ViewAgreements,
                      session: Session = Depends(get_session)):
    doc = get_scoped(session, Document, document_id, ctx)
    try:
        data = get_store().get(doc.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_410_GONE, "The original file is no longer stored (retention)") from None
    return Response(data, media_type=doc.media_type,
                    headers={"Content-Disposition": 'attachment; filename="' + doc.filename.replace('"', "") + '"'})

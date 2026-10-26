"""Effective-dated term resolution (BE-011, FR-12).

`confirmed_terms` is THE query through which the engine reads terms (GR-03). Nothing else in the
engine may select from commercial_term, so proposed, ambiguous or rejected terms can't reach a
calculation.
"""

import uuid
from datetime import date

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.domains.contracts.models import AgreementVersion, CommercialTerm


def confirmed_terms(org_id: uuid.UUID) -> Select[tuple[CommercialTerm]]:
    return select(CommercialTerm).where(CommercialTerm.org_id == org_id, CommercialTerm.status == "confirmed")


def applicable_version(session: Session, org_id: uuid.UUID, agreement_id: uuid.UUID, on: date) -> AgreementVersion | None:
    """The version in effect on `on`. If amendments overlap, the highest version number wins."""
    return session.scalar(
        select(AgreementVersion)
        .where(
            AgreementVersion.org_id == org_id,
            AgreementVersion.agreement_id == agreement_id,
            AgreementVersion.effective_from <= on,
            or_(AgreementVersion.effective_to.is_(None), AgreementVersion.effective_to >= on),
        )
        .order_by(AgreementVersion.version_no.desc())
        .limit(1)
    )


def resolve_terms(
    session: Session,
    org_id: uuid.UUID,
    agreement_id: uuid.UUID,
    on: date,
    *,
    item_code: str | None = None,
    term_type: str | None = None,
) -> list[CommercialTerm]:
    """Confirmed terms of the version in effect on `on`, themselves effective on `on`.

    With `item_code`, returns item-specific terms plus agreement-wide ones (item_code empty),
    item-specific first.
    """
    version = applicable_version(session, org_id, agreement_id, on)
    if version is None:
        return []
    stmt = confirmed_terms(org_id).where(
        CommercialTerm.agreement_version_id == version.id,
        CommercialTerm.effective_from <= on,
        or_(CommercialTerm.effective_to.is_(None), CommercialTerm.effective_to >= on),
    )
    if term_type:
        stmt = stmt.where(CommercialTerm.term_type == term_type)
    if item_code is not None:
        stmt = stmt.where(or_(CommercialTerm.item_code == item_code, CommercialTerm.item_code.is_(None)))
    terms = list(session.scalars(stmt.order_by(CommercialTerm.effective_from.desc(), CommercialTerm.id)))
    return sorted(terms, key=lambda t: t.item_code is None)

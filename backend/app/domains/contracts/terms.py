"""Effective-dated term resolution (BE-011, FR-12).

`confirmed_terms` is THE query through which the engine reads terms (GR-03). Nothing else in the
engine may select from commercial_term, so proposed, ambiguous or rejected terms can't reach a
calculation.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
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


def _effective(start: date, end: date | None, on: date) -> bool:
    return start <= on and (end is None or end >= on)


@dataclass
class TermBook:
    """In-memory equivalent of `resolve_terms` for a whole org, for check runs (NFR-04).

    Built only from `confirmed_terms` (GR-03); a test keeps its answers identical to resolve_terms.
    """

    versions: dict[uuid.UUID, list[AgreementVersion]] = field(default_factory=dict)
    terms: dict[uuid.UUID, list[CommercialTerm]] = field(default_factory=dict)
    version_no: dict[uuid.UUID, int] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session, org_id: uuid.UUID) -> "TermBook":
        book = cls()
        versions: dict[uuid.UUID, list[AgreementVersion]] = defaultdict(list)
        for v in session.scalars(select(AgreementVersion).where(AgreementVersion.org_id == org_id)):
            versions[v.agreement_id].append(v)
            book.version_no[v.id] = v.version_no
        book.versions = {a: sorted(vs, key=lambda v: v.version_no, reverse=True) for a, vs in versions.items()}
        terms: dict[uuid.UUID, list[CommercialTerm]] = defaultdict(list)
        for t in session.scalars(confirmed_terms(org_id)):
            terms[t.agreement_version_id].append(t)
        book.terms = dict(terms)
        return book

    def version_on(self, agreement_id: uuid.UUID, on: date) -> AgreementVersion | None:
        return next((v for v in self.versions.get(agreement_id, []) if _effective(v.effective_from, v.effective_to, on)),
                    None)

    def terms_on(self, agreement_id: uuid.UUID, on: date, *, item_code: str | None = None,
                 term_type: str | None = None) -> list[CommercialTerm]:
        version = self.version_on(agreement_id, on)
        if version is None:
            return []
        found = [
            t for t in self.terms.get(version.id, [])
            if _effective(t.effective_from, t.effective_to, on)
            and (term_type is None or t.term_type == term_type)
            and (item_code is None or t.item_code in (item_code, None))
        ]
        found.sort(key=lambda t: (t.item_code is None, -t.effective_from.toordinal(), str(t.id)))
        return found

    def first(self, agreement_id: uuid.UUID, on: date, term_type: str, item_code: str | None = None) -> CommercialTerm | None:
        terms = self.terms_on(agreement_id, on, item_code=item_code, term_type=term_type)
        return terms[0] if terms else None

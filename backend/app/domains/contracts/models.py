"""Agreements, versions, commercial terms and contract documents (design §3.2)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, CHAR, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, SourceMixin, one_of, source_key
from app.core.money import UnitPrice

BILLING_FREQUENCIES = ("monthly", "quarterly", "annual", "per_event", "milestone")
TERM_TYPES = ("rate", "discount", "escalation", "credit_policy", "minimum")
TERM_STATUSES = ("proposed", "confirmed", "rejected")
TERM_ORIGINS = ("import", "extraction", "manual")


class Document(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "document"

    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(CHAR(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    text_extracted: Mapped[str | None] = mapped_column(Text, nullable=True)


class Agreement(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "agreement"
    __table_args__ = (source_key("agreement"), one_of("billing_frequency", BILLING_FREQUENCIES))

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_frequency: Mapped[str] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(CHAR(3))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )


class AgreementVersion(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "agreement_version"
    __table_args__ = (source_key("agreement_version"),)

    agreement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agreement.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CommercialTerm(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    """Only status='confirmed' terms may reach the engine (GR-03, decision 0001 D-6)."""

    __tablename__ = "commercial_term"
    __table_args__ = (
        source_key("commercial_term"),
        one_of("term_type", TERM_TYPES),
        one_of("status", TERM_STATUSES),
        one_of("origin", TERM_ORIGINS),
    )

    agreement_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agreement_version.id", ondelete="CASCADE"), index=True
    )
    item_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    term_type: Mapped[str] = mapped_column(String(20))
    value: Mapped[Decimal] = mapped_column(UnitPrice)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    currency: Mapped[str | None] = mapped_column(CHAR(3), nullable=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Extra structured parameters (e.g. credit policy thresholds); never free text from documents.
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)
    ambiguous: Mapped[bool] = mapped_column(Boolean, default=False)
    ambiguity_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    origin: Mapped[str] = mapped_column(String(20))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

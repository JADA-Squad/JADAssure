"""Data sources, import batches and the canonical revenue records (design §3.2)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, SourceMixin, currency_column, one_of, source_key
from app.core.money import Money, Quantity, UnitPrice

RECORD_TYPES = (
    "customer",
    "agreement",
    "agreement_version",
    "commercial_term",
    "billable_event",
    "invoice",
    "invoice_line",
    "credit",
    "payment",
    "payment_allocation",
    "cost_record",
)
IMPORT_STATUSES = ("profiled", "queued", "running", "succeeded", "failed")


class DataSource(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "data_source"
    __table_args__ = (one_of("kind", ("csv", "connector")),)

    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    connector_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Connector settings, e.g. {"dataset": "cirrus-cloud"} for the demo connector (BE-009).
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # {record_type: {source_column: canonical_field}}
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ImportBatch(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "import_batch"
    __table_args__ = (one_of("record_type", RECORD_TYPES), one_of("status", IMPORT_STATUSES))

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id", ondelete="CASCADE"), index=True
    )
    record_type: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    file_ref: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_report_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job.id", ondelete="SET NULL"), nullable=True
    )


class Customer(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "customer"
    __table_args__ = (source_key("customer"),)

    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = currency_column()


class BillableEvent(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "billable_event"
    __table_args__ = (source_key("billable_event"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), index=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agreement.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_code: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    service_date: Mapped[date] = mapped_column(Date)
    billing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = currency_column()


class Invoice(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "invoice"
    __table_args__ = (source_key("invoice"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(80))
    invoice_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = currency_column()
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    correction_reference: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)


class InvoiceLine(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "invoice_line"
    __table_args__ = (source_key("invoice_line"),)

    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoice.id", ondelete="CASCADE"), index=True)
    agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agreement.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_code: Mapped[str] = mapped_column(String(80))
    quantity: Mapped[Decimal] = mapped_column(Quantity)
    unit_price: Mapped[Decimal] = mapped_column(UnitPrice)
    discount_pct: Mapped[Decimal] = mapped_column(UnitPrice, default=Decimal("0"))
    net_amount: Mapped[Decimal] = mapped_column(Money)
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    service_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    service_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)


class Credit(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "credit"
    __table_args__ = (source_key("credit"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = currency_column()
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    credit_date: Mapped[date] = mapped_column(Date)


class Payment(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "payment"
    __table_args__ = (source_key("payment"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = currency_column()
    payment_date: Mapped[date] = mapped_column(Date)


class PaymentAllocation(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "payment_allocation"
    __table_args__ = (source_key("payment_allocation"),)

    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoice.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)


class CostRecord(IdMixin, TimestampMixin, OrgScopedMixin, SourceMixin, Base):
    __tablename__ = "cost_record"
    __table_args__ = (source_key("cost_record"),)

    item_code: Mapped[str] = mapped_column(String(80), index=True)
    unit_cost: Mapped[Decimal] = mapped_column(UnitPrice)
    currency: Mapped[str] = currency_column()
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

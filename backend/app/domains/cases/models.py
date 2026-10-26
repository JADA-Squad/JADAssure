"""Investigation timeline, approvals and prepared corrections (design §3.2)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, currency_column, one_of
from app.core.money import Money

CORRECTION_STATUSES = ("prepared", "billed", "partially_paid", "paid")


class InvestigationEvent(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "investigation_event"
    # clock_timestamp(): real insert time, so several timeline events in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    __table_args__ = (one_of("kind", ("comment", "assign", "status")),)

    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("finding.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Approval(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    __tablename__ = "approval"
    # clock_timestamp(): real insert time, so several timeline events in one transaction keep their order.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    __table_args__ = (one_of("decision", ("approved", "sent_back", "written_off")),)

    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("finding.id", ondelete="CASCADE"), index=True)
    approver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("app_user.id"))
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Correction(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Prepared only; there is no outbound send path (GR-01)."""

    __tablename__ = "correction"
    __table_args__ = (
        one_of("kind", ("supplementary_invoice", "credit_reversal")),
        one_of("status", CORRECTION_STATUSES),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finding.id", ondelete="CASCADE"), unique=True
    )
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = currency_column()
    status: Mapped[str] = mapped_column(String(20))
    matched_invoice_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)

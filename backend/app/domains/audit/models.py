import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin


class AuditEvent(IdMixin, Base):
    """Append-only, hash-chained per organization (GR-10). Never updated or deleted."""

    __tablename__ = "audit_event"
    __table_args__ = (UniqueConstraint("org_id", "seq", name="uq_audit_event_org_seq"),)

    # No cascade: the tombstone event must survive organization data deletion (FR-41).
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organization.id"), index=True)
    seq: Mapped[int] = mapped_column(BigInteger)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    prev_hash: Mapped[str] = mapped_column(CHAR(64))
    hash: Mapped[str] = mapped_column(CHAR(64))

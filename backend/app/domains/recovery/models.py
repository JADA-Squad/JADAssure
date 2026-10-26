import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import OrgScopedMixin, one_of
from app.core.money import Money


class RecoveryEvent(IdMixin, TimestampMixin, OrgScopedMixin, Base):
    """Billed or cash evidence for a correction. Cash only from payment allocations (GR-04)."""

    __tablename__ = "recovery_event"
    __table_args__ = (
        one_of("kind", ("billed", "cash")),
        # One event per source record per correction, so re-imports never double count (GR-11).
        UniqueConstraint("correction_id", "kind", "source_entity_id", name="uq_recovery_event_source"),
    )

    correction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correction.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Money)
    source_entity: Mapped[str] = mapped_column(String(40))  # invoice_line | payment_allocation
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    occurred_on: Mapped[date] = mapped_column(Date)

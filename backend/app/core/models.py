"""Cross-cutting tables owned by core (not by a domain)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.db_mixins import one_of

JOB_STATUSES = ("queued", "running", "succeeded", "failed")


class Job(IdMixin, TimestampMixin, Base):
    """Background job, claimed with FOR UPDATE SKIP LOCKED (decision 0001 D-3, BE-008)."""

    __tablename__ = "job"
    __table_args__ = (one_of("status", JOB_STATUSES),)

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerHeartbeat(Base):
    """Last time each worker process checked in; read by /api/health (INFRA-001)."""

    __tablename__ = "worker_heartbeat"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

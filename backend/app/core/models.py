"""Cross-cutting tables owned by core (not by a domain)."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkerHeartbeat(Base):
    """Last time each worker process checked in; read by /api/health (INFRA-001)."""

    __tablename__ = "worker_heartbeat"

    worker_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))

"""Worker process: heartbeat plus job execution (INFRA-001, BE-008)."""

import logging
import os
import signal
import socket
import time
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

import app.job_handlers  # noqa: F401  (registers handlers)
import app.model_registry  # noqa: F401
from app.core import jobs
from app.core.config import get_settings
from app.core.db import new_session
from app.core.logging import configure_logging
from app.core.models import WorkerHeartbeat
from app.domains.rules import engine as rules_engine

log = logging.getLogger("jadassure.worker")
_running = True


def _stop(*_: object) -> None:
    global _running
    _running = False


def beat(worker_id: str) -> None:
    now = datetime.now(UTC)
    with new_session() as session:
        stmt = insert(WorkerHeartbeat).values(worker_id=worker_id, last_seen=now)
        session.execute(stmt.on_conflict_do_update(index_elements=["worker_id"], set_={"last_seen": now}))
        session.commit()


def schedule() -> None:
    """Queue scheduled check runs that are due (FR-10). Cheap; runs every loop."""
    with new_session() as session:
        if rules_engine.enqueue_due(session):
            session.commit()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("worker started", extra={"worker_id": worker_id})
    while _running:
        try:
            beat(worker_id)
            schedule()
            # Run queued jobs back to back, beating between them so long queues don't look stale.
            while _running and jobs.work_once():
                beat(worker_id)
        except Exception:
            log.exception("worker loop error")
        time.sleep(settings.worker_poll_seconds)
    log.info("worker stopped", extra={"worker_id": worker_id})


if __name__ == "__main__":
    main()

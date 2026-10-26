"""Worker process: heartbeat plus job execution (INFRA-001, BE-008)."""

import logging
import os
import signal
import socket
import threading
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
from app.domains.access import settings as org_settings
from app.domains.rules import engine as rules_engine

log = logging.getLogger("jadassure.worker")


def beat(worker_id: str) -> None:
    now = datetime.now(UTC)
    with new_session() as session:
        stmt = insert(WorkerHeartbeat).values(worker_id=worker_id, last_seen=now)
        session.execute(stmt.on_conflict_do_update(index_elements=["worker_id"], set_={"last_seen": now}))
        session.commit()


_last_purge: float = 0.0


def schedule() -> None:
    """Queue scheduled check runs that are due (FR-10); purge expired files hourly (FR-41)."""
    global _last_purge
    with new_session() as session:
        if rules_engine.enqueue_due(session):
            session.commit()
    if time.monotonic() - _last_purge > 3600:
        _last_purge = time.monotonic()
        with new_session() as session:
            org_settings.purge_expired_files(session)
            session.commit()


def run_loop(stop: threading.Event, worker_id: str) -> None:
    """Heartbeat, scheduled refresh and job execution until `stop` is set."""
    poll = get_settings().worker_poll_seconds
    log.info("worker started", extra={"worker_id": worker_id})
    while not stop.is_set():
        try:
            beat(worker_id)
            schedule()
            # Run queued jobs back to back, beating between them so long queues don't look stale.
            while not stop.is_set() and jobs.work_once():
                beat(worker_id)
        except Exception:
            log.exception("worker loop error")
        stop.wait(poll)
    log.info("worker stopped", extra={"worker_id": worker_id})


def make_worker_id(suffix: str = "") -> str:
    return f"{socket.gethostname()}:{os.getpid()}{suffix}"


def main() -> None:
    configure_logging(get_settings().log_level)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_loop(stop, make_worker_id())


if __name__ == "__main__":
    main()

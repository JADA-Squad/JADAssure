"""Postgres job queue (BE-008, decision 0001 D-3).

Jobs are rows claimed with FOR UPDATE SKIP LOCKED. Domains register a handler per job kind,
plus optional failure/retry hooks that keep their own status (e.g. an import batch) in step.
A failed job keeps its error and can be retried (FR-11).
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import new_session
from app.core.models import Job

log = logging.getLogger("jadassure.jobs")

Handler = Callable[[Session, Job], None]
Hook = Callable[[Session, Job], None]


class JobError(Exception):
    """A failure whose message is safe to show to users (no record content)."""


@dataclass(frozen=True)
class _Registration:
    handler: Handler
    on_failure: Hook | None
    on_retry: Hook | None


_HANDLERS: dict[str, _Registration] = {}


def register(kind: str, *, on_failure: Hook | None = None, on_retry: Hook | None = None):
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[kind] = _Registration(fn, on_failure, on_retry)
        return fn

    return decorator


def enqueue(session: Session, *, kind: str, org_id: uuid.UUID | None, payload: dict[str, Any]) -> Job:
    """Add a job in the caller's transaction; it becomes visible to workers when the caller commits."""
    if kind not in _HANDLERS:
        raise ValueError(f"no handler registered for job kind {kind!r}")
    job = Job(kind=kind, org_id=org_id, payload=payload, status="queued", attempts=0)
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session) -> Job | None:
    job = session.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= datetime.now(UTC))
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    session.commit()
    return job


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, JobError):
        return str(exc)[:2000]
    # Unexpected errors: show the type only; details stay in the worker log.
    return f"Unexpected error ({type(exc).__name__}). See worker logs."


def run(job_id: uuid.UUID) -> str:
    """Execute one claimed job in its own transaction. Returns the final status."""
    with new_session() as session:
        job = session.get(Job, job_id)
        assert job is not None
        reg = _HANDLERS.get(job.kind)
        try:
            if reg is None:
                raise JobError(f"No handler for job kind '{job.kind}'")
            reg.handler(session, job)
            job.status = "succeeded"
            job.last_error = None
            session.commit()
            log.info("job succeeded", extra={"job_id": str(job_id), "kind": job.kind})
            return "succeeded"
        except Exception as exc:
            session.rollback()
            log.exception("job failed", extra={"job_id": str(job_id), "kind": job.kind})
            job = session.get(Job, job_id)
            assert job is not None
            job.status = "failed"
            job.last_error = _safe_error(exc)
            if reg and reg.on_failure:
                reg.on_failure(session, job)
            session.commit()
            return "failed"


def work_once() -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    with new_session() as session:
        job = claim_next(session)
        job_id = job.id if job else None
    if job_id is None:
        return False
    run(job_id)
    return True


def drain(max_jobs: int = 1000) -> int:
    """Run queued jobs until none are left (used by the seed command and tests)."""
    n = 0
    while n < max_jobs and work_once():
        n += 1
    return n


def retry(session: Session, job: Job) -> Job:
    if job.status != "failed":
        raise JobError("Only failed jobs can be retried")
    job.status = "queued"
    job.run_after = datetime.now(UTC)
    reg = _HANDLERS.get(job.kind)
    if reg and reg.on_retry:
        reg.on_retry(session, job)
    return job

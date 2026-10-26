"""Check runs: evaluate every check, de-duplicate, upsert findings by fingerprint (BE-019, BE-010).

Fingerprint = sha256(org | family | anchor type | anchor id) (decision 0001 D-8). A finding is
refreshed by later runs only while it is `open` or `in_review`. Once a person has proposed or
decided on it, its value and evidence are frozen (decision 0003 D-2). Re-running never creates a
duplicate (FR-23, GR-11).
"""

import hashlib
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.models import Job
from app.domains.access.models import Organization
from app.domains.audit import service as audit
from app.domains.contracts.terms import TermBook
from app.domains.matching.matcher import OrgData, build_buckets
from app.domains.rules import checks, config
from app.domains.rules.models import CheckRun, Finding, RuleVersion

RUN_JOB = "run_checks"
REFRESHABLE = ("open", "in_review")
# Confirmed leakage: a later finding with the same recurrence key is a recurrence (FR-31, BE-024).
CONFIRMED = ("approved", "billed", "recovered", "closed_no_recovery")
_UPDATABLE = ("check_type", "also_detected_by", "value", "currency", "confidence", "reason", "recommended_action",
              "calculation", "evidence", "customer_id", "agreement_id", "item_code", "period_start", "period_end")


def fingerprint(org_id: uuid.UUID, family: str, anchor_type: str, anchor_id: str) -> str:
    return hashlib.sha256(f"{org_id}|{family}|{anchor_type}|{anchor_id}".encode()).hexdigest()


def recurrence_key(f: Any) -> tuple:
    """Same cause, same customer and term (FR-31): customer, agreement, check type and item."""
    return (f.customer_id, f.agreement_id, f.check_type, f.item_code)


def recurrence_of(confirmed: list[Finding], c: checks.Candidate) -> Finding | None:
    """The most recent confirmed finding with the same key whose period ended before this one began."""
    key = recurrence_key(c)
    earlier = [f for f in confirmed if recurrence_key(f) == key and f.period_end and c.period_start
               and f.period_end < c.period_start]
    return max(earlier, key=lambda f: f.period_end, default=None)


def evaluate(session: Session, org_id: uuid.UUID, versions: dict[str, RuleVersion], as_of: date) -> tuple[list[checks.Candidate], dict[str, int]]:
    """Pure evaluation: no writes. Returns candidates and skip counters."""
    data = OrgData.load(session, org_id)
    book = TermBook.load(session, org_id)
    ctx = checks.CheckContext(data=data, book=book, params={ct: config.typed(ct, v.params) for ct, v in versions.items()},
                              as_of=as_of)
    found: list[checks.Candidate] = []
    for bucket in build_buckets(data, book).values():
        if (c := checks.delivered_not_billed(ctx, bucket)) is not None:
            found.append(c)
    for line in data.lines:
        if (c := checks.price_line(ctx, line)) is not None:
            found.append(c)
    for credit in data.credits:
        if (c := checks.credit_outside_policy(ctx, credit)) is not None:
            found.append(c)
    return found, ctx.skipped


def upsert_findings(session: Session, org_id: uuid.UUID, run: CheckRun, versions: dict[str, RuleVersion],
                    candidates: list[checks.Candidate]) -> dict[str, int]:
    by_fp: dict[str, checks.Candidate] = {}
    for c in candidates:
        fp = fingerprint(org_id, c.family, c.anchor_type, c.anchor_id)
        by_fp.setdefault(fp, c)  # an anchor appears once per family; first wins defensively
    existing = {f.fingerprint: f for f in session.scalars(
        select(Finding).where(Finding.org_id == org_id, Finding.fingerprint.in_(list(by_fp)))
    )} if by_fp else {}

    stats = {"new": 0, "refreshed": 0, "unchanged": 0, "frozen": 0, "recurrences": 0}
    confirmed = list(session.scalars(select(Finding).where(Finding.org_id == org_id, Finding.status.in_(CONFIRMED))))
    for fp, c in by_fp.items():
        attrs: dict[str, Any] = {k: getattr(c, k) for k in _UPDATABLE}
        attrs["rule_version_id"] = versions[c.check_type].id
        f = existing.get(fp)
        if f is None:
            prior = recurrence_of(confirmed, c)
            session.add(Finding(org_id=org_id, fingerprint=fp, family=c.family, status="open",
                                first_run_id=run.id, last_run_id=run.id,
                                recurrence_of_id=prior.id if prior else None, **attrs))
            stats["new"] += 1
            stats["recurrences"] += prior is not None
        elif f.status not in REFRESHABLE:
            stats["frozen"] += 1
        else:
            changed = any(getattr(f, k) != v for k, v in attrs.items())
            for k, v in attrs.items():
                setattr(f, k, v)
            f.last_run_id = run.id
            stats["refreshed" if changed else "unchanged"] += 1
    session.flush()
    return stats


def execute_run(session: Session, run: CheckRun, as_of: date) -> None:
    org = session.get(Organization, run.org_id)
    assert org is not None
    started = time.perf_counter()
    run.status = "running"
    run.started_at = datetime.now(UTC)
    versions = config.ensure_rules(session, org.id, org.business_type, None)
    run.rule_version_ids = [str(v.id) for v in versions.values()]
    candidates, skipped = evaluate(session, org.id, versions, as_of)
    upserted = upsert_findings(session, org.id, run, versions, candidates)
    by_check: dict[str, int] = {}
    for c in candidates:
        by_check[c.check_type] = by_check.get(c.check_type, 0) + 1
    run.stats = {"detected": len(candidates), "by_check": by_check, **upserted, "skipped": skipped,
                 "as_of": as_of.isoformat(), "duration_ms": round((time.perf_counter() - started) * 1000)}
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    audit.record(session, org_id=org.id, actor_id=run.requested_by, action="check_run.completed", entity="check_run",
                 entity_id=run.id, payload={k: run.stats[k] for k in ("detected", "new", "refreshed", "frozen")})


# ------------------------------------------------------------------ runs as jobs (BE-010)

def request_run(session: Session, org_id: uuid.UUID, *, trigger: str, requested_by: uuid.UUID | None,
                as_of: date | None = None) -> CheckRun:
    """Queue a run unless one is already queued or running for the org (FR-10)."""
    active = session.scalar(select(CheckRun).where(CheckRun.org_id == org_id,
                                                   CheckRun.status.in_(("queued", "running"))))
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A check run is already in progress")
    run = CheckRun(org_id=org_id, trigger=trigger, status="queued", requested_by=requested_by, stats={},
                   rule_version_ids=[])
    session.add(run)
    session.flush()
    payload = {"run_id": str(run.id)}
    if as_of is not None:
        payload["as_of"] = as_of.isoformat()
    jobs.enqueue(session, kind=RUN_JOB, org_id=org_id, payload=payload)
    audit.record(session, org_id=org_id, actor_id=requested_by, action="check_run.requested", entity="check_run",
                 entity_id=run.id, payload={"trigger": trigger})
    return run


def _run_handler(session: Session, job: Job) -> None:
    run = session.get(CheckRun, uuid.UUID(job.payload["run_id"]))
    if run is None or run.org_id != job.org_id:
        raise jobs.JobError("Check run not found")
    as_of = date.fromisoformat(job.payload["as_of"]) if job.payload.get("as_of") else date.today()
    execute_run(session, run, as_of)


def _on_failure(session: Session, job: Job) -> None:
    run = session.get(CheckRun, uuid.UUID(job.payload["run_id"]))
    if run is not None:
        run.status = "failed"
        run.error = job.last_error
        run.finished_at = datetime.now(UTC)


def _on_retry(session: Session, job: Job) -> None:
    run = session.get(CheckRun, uuid.UUID(job.payload["run_id"]))
    if run is not None:
        run.status = "queued"
        run.error = None


jobs.register(RUN_JOB, on_failure=_on_failure, on_retry=_on_retry)(_run_handler)


def enqueue_due(session: Session, now: datetime | None = None) -> int:
    """Scheduled refresh: queue a run for each org whose refresh interval has elapsed (FR-10)."""
    now = now or datetime.now(UTC)
    queued = 0
    for org in session.scalars(select(Organization)):
        minutes = int((org.settings or {}).get("refresh_interval_minutes") or 0)
        if minutes <= 0:
            continue
        last = session.scalar(select(CheckRun).where(CheckRun.org_id == org.id)
                              .order_by(CheckRun.created_at.desc()).limit(1))
        if last is not None and (last.status in ("queued", "running")
                                 or last.created_at > now - timedelta(minutes=minutes)):
            continue
        request_run(session, org.id, trigger="schedule", requested_by=None)
        queued += 1
    return queued

"""Hash-chained audit log (GR-10, BE-004).

hash = sha256(prev_hash || canonical_json(event)). Events are appended in the caller's transaction,
so the audit record commits or rolls back together with the change it describes.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditEvent

GENESIS = "0" * 64


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _event_body(e: AuditEvent) -> dict[str, Any]:
    return {
        "org_id": str(e.org_id),
        "seq": e.seq,
        "actor_id": str(e.actor_id) if e.actor_id else None,
        "action": e.action,
        "entity": e.entity,
        "entity_id": e.entity_id,
        "payload": e.payload,
        "occurred_at": e.occurred_at.astimezone(UTC).isoformat(),
    }


def compute_hash(prev_hash: str, e: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + _canonical(_event_body(e))).encode("utf-8")).hexdigest()


def record(
    session: Session,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: Any = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the org's chain. Payloads hold ids and decisions, never sensitive content."""
    # Serialize appends per org so seq and prev_hash can't race.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{org_id}"})
    last = session.execute(
        select(AuditEvent.seq, AuditEvent.hash).where(AuditEvent.org_id == org_id).order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    seq, prev_hash = (last.seq + 1, last.hash) if last else (1, GENESIS)

    event = AuditEvent(
        org_id=org_id,
        seq=seq,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        # Round-trip through JSON so the hashed payload equals what JSONB stores.
        payload=json.loads(_canonical(payload or {})),
        occurred_at=datetime.now(UTC),
        prev_hash=prev_hash,
    )
    event.hash = compute_hash(prev_hash, event)
    session.add(event)
    session.flush()
    return event


def verify(session: Session, org_id: uuid.UUID) -> dict[str, Any]:
    """Recompute the org's chain. Reports the first broken sequence number, if any."""
    prev_hash = GENESIS
    expected_seq = 1
    count = 0
    for e in session.scalars(select(AuditEvent).where(AuditEvent.org_id == org_id).order_by(AuditEvent.seq)):
        count += 1
        if e.seq != expected_seq or e.prev_hash != prev_hash or compute_hash(prev_hash, e) != e.hash:
            return {"ok": False, "events": count, "first_bad_seq": e.seq}
        prev_hash = e.hash
        expected_seq += 1
    return {"ok": True, "events": count, "first_bad_seq": None}


def list_events(session: Session, org_id: uuid.UUID, limit: int, before_seq: int | None) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.org_id == org_id)
    if before_seq is not None:
        stmt = stmt.where(AuditEvent.seq < before_seq)
    return list(session.scalars(stmt.order_by(AuditEvent.seq.desc()).limit(limit)))


def count_events(session: Session, org_id: uuid.UUID) -> int:
    return session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.org_id == org_id)) or 0

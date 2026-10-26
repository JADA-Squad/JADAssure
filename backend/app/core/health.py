"""Health endpoint reporting database and worker status (INFRA-001, NFR-07)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.models import WorkerHeartbeat

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health(session: Session = Depends(get_session)) -> JSONResponse:
    try:
        session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"

    worker = "unknown"
    if database == "ok":
        last_seen = session.scalar(select(func.max(WorkerHeartbeat.last_seen)))
        stale_after = timedelta(seconds=get_settings().worker_heartbeat_stale_seconds)
        if last_seen is None:
            worker = "missing"
        elif datetime.now(UTC) - last_seen > stale_after:
            worker = "stale"
        else:
            worker = "ok"

    ok = database == "ok" and worker == "ok"
    body = {"status": "ok" if ok else "degraded", "database": database, "worker": worker}
    return JSONResponse(body, status_code=200 if ok else 503)

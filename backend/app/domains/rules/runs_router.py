import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.permissions import Cap, require, require_any
from app.domains.rules import engine
from app.domains.rules.models import CheckRun

router = APIRouter(prefix="/api/check-runs", tags=["check runs"])
ViewRuns = Depends(require_any(Cap.RUN_CHECKS, Cap.VIEW_FINDINGS))


class CheckRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: str
    status: str
    stats: dict[str, Any]
    error: str | None
    requested_by: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.post("", response_model=CheckRunOut, status_code=status.HTTP_202_ACCEPTED)
def run_checks_now(ctx: TenantContext = Depends(require(Cap.RUN_CHECKS)), session: Session = Depends(get_session)):
    run = engine.request_run(session, ctx.org_id, trigger="manual", requested_by=ctx.user_id)
    session.commit()
    return run


@router.get("", response_model=list[CheckRunOut])
def list_runs(limit: int = Query(20, ge=1, le=100), ctx: TenantContext = ViewRuns,
              session: Session = Depends(get_session)):
    return list(session.scalars(scoped(CheckRun, ctx).order_by(CheckRun.created_at.desc()).limit(limit)))


@router.get("/{run_id}", response_model=CheckRunOut)
def get_run(run_id: uuid.UUID, ctx: TenantContext = ViewRuns, session: Session = Depends(get_session)):
    return get_scoped(session, CheckRun, run_id, ctx)

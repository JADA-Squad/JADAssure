"""Jobs API: list jobs and retry failed ones (BE-008, FR-11)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.db import get_session
from app.core.models import Job
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.permissions import Cap, require
from app.domains.audit import service as audit

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    last_error: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[JobOut])
def list_jobs(
    status_: Literal["queued", "running", "succeeded", "failed"] | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    ctx: TenantContext = Depends(require(Cap.MANAGE_DATA)),
    session: Session = Depends(get_session),
):
    stmt = scoped(Job, ctx)
    if status_:
        stmt = stmt.where(Job.status == status_)
    return list(session.scalars(stmt.order_by(Job.created_at.desc()).limit(limit)))


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: uuid.UUID,
    ctx: TenantContext = Depends(require(Cap.MANAGE_DATA)),
    session: Session = Depends(get_session),
):
    job = get_scoped(session, Job, job_id, ctx)
    try:
        jobs.retry(session, job)
    except jobs.JobError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="job.retried", entity="job", entity_id=job.id,
                 payload={"kind": job.kind})
    session.commit()
    return job

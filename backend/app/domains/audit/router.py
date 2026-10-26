import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext
from app.domains.access.permissions import Cap, require
from app.domains.audit import service

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    seq: int
    actor_id: uuid.UUID | None
    action: str
    entity: str
    entity_id: str | None
    payload: dict[str, Any]
    occurred_at: datetime
    hash: str


class AuditVerifyOut(BaseModel):
    ok: bool
    events: int
    first_bad_seq: int | None


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    limit: int = Query(50, ge=1, le=500),
    before_seq: int | None = Query(None, ge=1),
    ctx: TenantContext = Depends(require(Cap.VIEW_AUDIT)),
    session: Session = Depends(get_session),
):
    return service.list_events(session, ctx.org_id, limit, before_seq)


@router.get("/verify", response_model=AuditVerifyOut)
def verify_audit_chain(
    ctx: TenantContext = Depends(require(Cap.VIEW_AUDIT)), session: Session = Depends(get_session)
):
    return service.verify(session, ctx.org_id)

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext
from app.domains.access.permissions import Cap, require
from app.domains.cases import service
from app.domains.cases.schemas import CommentIn, FindingDetail, FindingFilters, FindingPage

router = APIRouter(prefix="/api/findings", tags=["findings"])
ViewFindings = Depends(require(Cap.VIEW_FINDINGS))

Status = Literal["open", "in_review", "proposed", "approved", "billed", "recovered", "rejected", "closed_no_recovery"]


@router.get("", response_model=FindingPage)
def list_findings(
    min_value: Decimal | None = Query(None, ge=0),
    max_value: Decimal | None = Query(None, ge=0),
    customer_id: uuid.UUID | None = None,
    check_type: Literal["delivered_not_billed", "incorrect_rate", "expired_discount", "missed_increase",
                        "credit_outside_policy"] | None = None,
    confidence: Literal["high", "medium", "low"] | None = None,
    status_: list[Status] | None = Query(None, alias="status"),
    owner_id: uuid.UUID | None = None,
    unassigned: bool = False,
    min_age_days: int | None = Query(None, ge=0),
    max_age_days: int | None = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = ViewFindings,
    session: Session = Depends(get_session),
):
    return service.list_findings(
        session, ctx, min_value=min_value, max_value=max_value, customer_id=customer_id, check_type=check_type,
        confidence=confidence, statuses=status_, owner_id=owner_id, unassigned=unassigned,
        min_age_days=min_age_days, max_age_days=max_age_days, limit=limit, offset=offset,
    )


@router.get("/filters", response_model=FindingFilters)
def finding_filters(ctx: TenantContext = ViewFindings, session: Session = Depends(get_session)):
    return service.filters(session, ctx)


@router.get("/{finding_id}", response_model=FindingDetail)
def get_finding(finding_id: uuid.UUID, ctx: TenantContext = ViewFindings, session: Session = Depends(get_session)):
    return service.detail(session, ctx, finding_id)


@router.post("/{finding_id}/comments", status_code=status.HTTP_201_CREATED, response_model=FindingDetail)
def comment(finding_id: uuid.UUID, data: CommentIn, ctx: TenantContext = Depends(require(Cap.COMMENT_ASSIGN)),
            session: Session = Depends(get_session)):
    service.add_comment(session, ctx, finding_id, data.body)
    session.commit()
    return service.detail(session, ctx, finding_id)

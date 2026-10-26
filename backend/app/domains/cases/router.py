import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, get_scoped
from app.domains.access.permissions import Cap, require
from app.domains.cases import corrections, service, workflow
from app.domains.cases.models import Correction
from app.domains.cases.schemas import (
    AssignIn,
    CommentIn,
    DecisionIn,
    FindingDetail,
    FindingFilters,
    FindingPage,
    ProposeIn,
)
from app.domains.rules.models import Finding

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


# ---------------------------------------------------------------- workflow (BE-021)

@router.post("/{finding_id}/assign", response_model=FindingDetail)
def assign(finding_id: uuid.UUID, data: AssignIn, ctx: TenantContext = Depends(require(Cap.COMMENT_ASSIGN)),
           session: Session = Depends(get_session)):
    workflow.assign(session, ctx, finding_id, data.owner_id)
    session.commit()
    return service.detail(session, ctx, finding_id)


@router.post("/{finding_id}/propose", response_model=FindingDetail)
def propose(finding_id: uuid.UUID, data: ProposeIn, ctx: TenantContext = Depends(require(Cap.PROPOSE_REJECT)),
            session: Session = Depends(get_session)):
    workflow.transition(session, ctx, finding_id, "propose", note=data.note,
                        root_cause_category=data.root_cause_category, root_cause=data.root_cause)
    session.commit()
    return service.detail(session, ctx, finding_id)


def _decision_endpoint(action: str, cap: Cap):
    def endpoint(finding_id: uuid.UUID, data: DecisionIn, ctx: TenantContext = Depends(require(cap)),
                 session: Session = Depends(get_session)):
        workflow.transition(session, ctx, finding_id, action, note=data.note)
        session.commit()
        return service.detail(session, ctx, finding_id)

    endpoint.__name__ = action
    return endpoint


for _action, _cap in (("reject", Cap.PROPOSE_REJECT), ("send_back", Cap.APPROVE), ("approve", Cap.APPROVE),
                      ("write_off", Cap.APPROVE)):
    router.add_api_route("/{finding_id}/" + _action.replace("_", "-"), _decision_endpoint(_action, _cap),
                         methods=["POST"], response_model=FindingDetail, name=_action)


# ---------------------------------------------------------------- correction export (BE-022)

corrections_router = APIRouter(prefix="/api/corrections", tags=["corrections"])


def _correction(session: Session, ctx: TenantContext, correction_id: uuid.UUID) -> tuple[Correction, Finding]:
    c = get_scoped(session, Correction, correction_id, ctx)
    return c, session.get(Finding, c.finding_id)  # type: ignore[return-value]


@corrections_router.get("/{correction_id}/export.json")
def export_json(correction_id: uuid.UUID, ctx: TenantContext = Depends(require(Cap.EXPORT_CORRECTIONS)),
                session: Session = Depends(get_session)):
    c, f = _correction(session, ctx, correction_id)
    return corrections.export_dict(c, f)


@corrections_router.get("/{correction_id}/export.csv", response_class=Response)
def export_csv(correction_id: uuid.UUID, ctx: TenantContext = Depends(require(Cap.EXPORT_CORRECTIONS)),
               session: Session = Depends(get_session)):
    c, f = _correction(session, ctx, correction_id)
    return Response(corrections.export_csv(c, f), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="' + c.reference + '.csv"'})

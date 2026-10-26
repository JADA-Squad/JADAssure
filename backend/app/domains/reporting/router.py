from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext
from app.domains.access.permissions import Cap, require
from app.domains.reporting import service

router = APIRouter(prefix="/api/reports", tags=["reporting"])


class CurrencyFigures(BaseModel):
    currency: str
    potential: Decimal
    confirmed: Decimal
    corrected_billing: Decimal
    cash_recovered: Decimal
    prevented_recurrence: Decimal
    closed_without_recovery: Decimal


class Counts(BaseModel):
    open: int
    awaiting_approval: int
    in_recovery: int
    recovered: int
    rejected: int
    recurring: int
    total: int


class TrendPoint(BaseModel):
    month: str
    currency: str
    identified: Decimal
    recovered: Decimal


class RootCause(BaseModel):
    category: str
    currency: str
    count: int
    value: Decimal


class OutcomesOut(BaseModel):
    currencies: list[CurrencyFigures]
    counts: Counts
    trend: list[TrendPoint]
    root_causes: list[RootCause]
    notes: dict[str, str]


@router.get("/outcomes", response_model=OutcomesOut)
def outcomes(ctx: TenantContext = Depends(require(Cap.VIEW_REPORTS)), session: Session = Depends(get_session)):
    """The six outcome figures (FR-32), counts, 12-month trend and top root causes."""
    return service.outcomes(session, ctx.org_id)

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class FindingListItem(BaseModel):
    id: uuid.UUID
    check_type: str
    family: str
    status: str
    value: Decimal
    currency: str
    confidence: str
    priority: Decimal
    customer_id: uuid.UUID | None
    customer_name: str | None
    agreement_title: str | None
    item_code: str | None
    period_start: date | None
    period_end: date | None
    owner_id: uuid.UUID | None
    owner_name: str | None
    reason: str
    age_days: int
    created_at: datetime


class FindingPage(BaseModel):
    items: list[FindingListItem]
    total: int
    value_by_currency: dict[str, Decimal]


class TimelineEntry(BaseModel):
    at: datetime
    kind: str  # detected | comment | assign | status | approval
    actor_name: str | None
    body: str | None
    data: dict[str, Any] = {}


class RuleVersionRef(BaseModel):
    id: uuid.UUID
    version_no: int
    params: dict[str, Any]


class CorrectionRef(BaseModel):
    id: uuid.UUID
    reference: str
    kind: str
    status: str
    amount: Decimal
    currency: str


class FindingDetail(FindingListItem):
    also_detected_by: list[str]
    recommended_action: str
    calculation: dict[str, Any]
    evidence: dict[str, Any]
    rule_version: RuleVersionRef
    root_cause_category: str | None
    root_cause: str | None
    proposer_id: uuid.UUID | None
    proposer_name: str | None
    correction: CorrectionRef | None
    recurrence_of: dict[str, Any] | None
    available_actions: list[str]
    ai_summary: str | None
    first_detected_at: datetime
    last_checked_at: datetime
    timeline: list[TimelineEntry]


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class FilterOption(BaseModel):
    id: uuid.UUID
    name: str


class FindingFilters(BaseModel):
    customers: list[FilterOption]
    owners: list[FilterOption]
    check_types: list[str]
    statuses: list[str]


class AssignIn(BaseModel):
    owner_id: uuid.UUID | None


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ProposeIn(BaseModel):
    root_cause_category: str = Field(max_length=40)
    root_cause: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=2000)

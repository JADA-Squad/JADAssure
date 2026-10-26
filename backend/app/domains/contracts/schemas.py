import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_record_id: str | None
    item_code: str | None
    term_type: str
    value: Decimal
    unit: str | None
    currency: str | None
    effective_from: date
    effective_to: date | None
    approval_ref: str | None
    params: dict[str, Any]
    status: str
    ambiguous: bool
    ambiguity_reason: str | None
    source_passage: str | None
    origin: str
    confirmed_at: datetime | None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_no: int
    effective_from: date
    effective_to: date | None
    reason: str | None
    terms: list[TermOut] = []


class AgreementSummaryOut(BaseModel):
    id: uuid.UUID
    source_record_id: str | None
    title: str
    customer_id: uuid.UUID
    customer_name: str
    start_date: date
    end_date: date | None
    billing_frequency: str
    currency: str
    version_count: int
    term_counts: dict[str, int]


class AgreementDetailOut(AgreementSummaryOut):
    versions: list[VersionOut]

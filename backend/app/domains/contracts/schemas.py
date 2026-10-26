import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agreement_id: uuid.UUID | None
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    extraction_status: str
    extraction_error: str | None
    extraction_stats: dict[str, Any]
    created_at: datetime


class TermReviewOut(TermOut):
    agreement_id: uuid.UUID
    agreement_title: str
    customer_name: str
    version_no: int
    document_id: uuid.UUID | None
    document_filename: str | None


class ConfirmTermIn(BaseModel):
    value: Decimal | None = None
    item_code: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    effective_from: date | None = None
    effective_to: date | None = None
    clear_effective_to: bool = False
    note: str | None = Field(default=None, max_length=2000)


class RejectTermIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)

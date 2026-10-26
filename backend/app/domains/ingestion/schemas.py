import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RecordType = Literal[
    "customer", "agreement", "agreement_version", "commercial_term", "billable_event", "invoice",
    "invoice_line", "credit", "payment", "payment_allocation", "cost_record",
]


class DataSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class DataSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    connector_key: str | None
    is_demo: bool
    config: dict[str, Any]
    mapping: dict[str, dict[str, str]]
    created_at: datetime


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data_source_id: uuid.UUID
    record_type: str
    filename: str
    status: str
    counts: dict[str, int]
    profile: dict[str, Any]
    error: str | None
    job_id: uuid.UUID | None
    has_error_report: bool = False
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, batch: Any, is_demo: bool = False) -> "ImportOut":
        out = cls.model_validate(batch)
        out.has_error_report = batch.error_report_ref is not None
        out.is_demo = is_demo
        return out


class MappingIn(BaseModel):
    # {source column: canonical field}; empty string or omitted column = not mapped
    mapping: dict[str, str]

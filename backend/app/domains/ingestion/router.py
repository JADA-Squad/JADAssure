from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.tenancy import TenantContext
from app.domains.access.permissions import Cap, require
from app.domains.ingestion.registry import LOAD_ORDER, RECORDS, template_csv

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

RecordType = Literal[
    "customer", "agreement", "agreement_version", "commercial_term", "billable_event", "invoice",
    "invoice_line", "credit", "payment", "payment_allocation", "cost_record",
]


class FieldOut(BaseModel):
    name: str
    type: str
    required: bool
    description: str
    ref: str | None
    choices: list[str]


class RecordTypeOut(BaseModel):
    record_type: str
    label: str
    depends_on: list[str]
    fields: list[FieldOut]


@router.get("/record-types", response_model=list[RecordTypeOut])
def list_record_types(_: TenantContext = Depends(require(Cap.MANAGE_DATA))):
    return [
        RecordTypeOut(
            record_type=spec.record_type,
            label=spec.label,
            depends_on=list(spec.depends_on),
            fields=[
                FieldOut(name=f.name, type=f.type, required=f.required, description=f.description, ref=f.ref,
                         choices=list(f.choices))
                for f in spec.fields
            ],
        )
        for spec in (RECORDS[t] for t in LOAD_ORDER)
    ]


@router.get("/templates/{record_type}.csv", response_class=Response)
def download_template(record_type: RecordType, _: TenantContext = Depends(require(Cap.MANAGE_DATA))):
    return Response(
        template_csv(record_type),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="jadassure-{record_type}-template.csv"'},
    )

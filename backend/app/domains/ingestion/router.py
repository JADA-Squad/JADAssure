import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.storage import get_store
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.access.permissions import Cap, require
from app.domains.ingestion import service
from app.domains.ingestion.models import DataSource, ImportBatch
from app.domains.ingestion.parsing import MAX_BYTES
from app.domains.ingestion.registry import LOAD_ORDER, RECORDS, template_csv
from app.domains.ingestion.schemas import DataSourceIn, DataSourceOut, ImportOut, MappingIn, RecordType

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])
sources_router = APIRouter(prefix="/api/data-sources", tags=["ingestion"])
imports_router = APIRouter(prefix="/api/imports", tags=["ingestion"])

ManageData = Depends(require(Cap.MANAGE_DATA))


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
def list_record_types(_: TenantContext = ManageData):
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
def download_template(record_type: RecordType, _: TenantContext = ManageData):
    return Response(
        template_csv(record_type),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="jadassure-{record_type}-template.csv"'},
    )


def _out(session: Session, batch: ImportBatch) -> ImportOut:
    source = session.get(DataSource, batch.data_source_id)
    return ImportOut.build(batch, is_demo=bool(source and source.is_demo))


# ---------------------------------------------------------------- data sources

@sources_router.get("", response_model=list[DataSourceOut])
def list_sources(ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    return service.list_sources(session, ctx)


@sources_router.post("", response_model=DataSourceOut, status_code=status.HTTP_201_CREATED)
def create_source(data: DataSourceIn, ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    source = service.create_source(session, ctx, name=data.name)
    session.commit()
    return source


@sources_router.get("/{source_id}", response_model=DataSourceOut)
def get_source(source_id: uuid.UUID, ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    return get_scoped(session, DataSource, source_id, ctx)


@sources_router.post("/{source_id}/imports", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
async def upload_import(
    source_id: uuid.UUID,
    record_type: RecordType = Form(...),
    file: UploadFile = File(...),
    ctx: TenantContext = ManageData,
    session: Session = Depends(get_session),
):
    source = get_scoped(session, DataSource, source_id, ctx)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is larger than 10 MB")
    batch = service.start_import(session, ctx, source, record_type, file.filename or "upload.csv", data)
    session.commit()
    return _out(session, batch)


# ---------------------------------------------------------------- imports

@imports_router.get("", response_model=list[ImportOut])
def list_imports(
    data_source_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: TenantContext = ManageData,
    session: Session = Depends(get_session),
):
    stmt = scoped(ImportBatch, ctx)
    if data_source_id:
        stmt = stmt.where(ImportBatch.data_source_id == data_source_id)
    batches = session.scalars(stmt.order_by(ImportBatch.created_at.desc()).limit(limit))
    return [_out(session, b) for b in batches]


@imports_router.get("/{import_id}", response_model=ImportOut)
def get_import(import_id: uuid.UUID, ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    return _out(session, get_scoped(session, ImportBatch, import_id, ctx))


@imports_router.put("/{import_id}/mapping", response_model=ImportOut)
def update_mapping(
    import_id: uuid.UUID, data: MappingIn, ctx: TenantContext = ManageData, session: Session = Depends(get_session)
):
    batch = service.set_mapping(session, ctx, get_scoped(session, ImportBatch, import_id, ctx), data.mapping)
    session.commit()
    return _out(session, batch)


@imports_router.post("/{import_id}/commit", response_model=ImportOut)
def commit_import(import_id: uuid.UUID, ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    batch = service.request_commit(session, ctx, get_scoped(session, ImportBatch, import_id, ctx))
    session.commit()
    return _out(session, batch)


@imports_router.get("/{import_id}/errors.csv", response_class=Response)
def download_errors(import_id: uuid.UUID, ctx: TenantContext = ManageData, session: Session = Depends(get_session)):
    batch = get_scoped(session, ImportBatch, import_id, ctx)
    if batch.error_report_ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This import has no rejected rows")
    return Response(
        get_store().get(batch.error_report_ref),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="import-{batch.id}-errors.csv"'},
    )

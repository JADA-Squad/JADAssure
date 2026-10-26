import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.tenancy import TenantContext, get_scoped
from app.domains.access.permissions import Cap, require
from app.domains.connectors import service
from app.domains.ingestion.models import DataSource
from app.domains.ingestion.schemas import DataSourceOut

router = APIRouter(tags=["connectors"])
ManageData = Depends(require(Cap.MANAGE_DATA))


class ConnectorOut(BaseModel):
    key: str
    label: str
    description: str
    is_demo: bool
    options: dict[str, list[str]]


class ConnectorSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    connector_key: str = Field(max_length=80)
    config: dict[str, Any] = {}


class SyncIn(BaseModel):
    stage: str = Field("baseline", pattern=r"^[a-z0-9-]{1,40}$")


class SyncOut(BaseModel):
    job_id: uuid.UUID
    status: str
    is_demo: bool


@router.get("/api/connectors", response_model=list[ConnectorOut])
def list_connectors(_: TenantContext = ManageData):
    return [c.info().__dict__ for c in service.CONNECTORS.values()]


@router.post("/api/data-sources/connector", response_model=DataSourceOut, status_code=status.HTTP_201_CREATED)
def create_connector_source(data: ConnectorSourceIn, ctx: TenantContext = ManageData,
                            session: Session = Depends(get_session)):
    source = service.create_connector_source(session, ctx, name=data.name, connector_key=data.connector_key,
                                             config=data.config)
    session.commit()
    return source


@router.post("/api/data-sources/{source_id}/sync", response_model=SyncOut, status_code=status.HTTP_202_ACCEPTED)
def sync_source(source_id: uuid.UUID, data: SyncIn, ctx: TenantContext = ManageData,
                session: Session = Depends(get_session)):
    source = get_scoped(session, DataSource, source_id, ctx)
    job = service.request_sync(session, ctx, source, data.stage)
    session.commit()
    return SyncOut(job_id=job.id, status=job.status, is_demo=source.is_demo)

"""Connector registry and sync job (BE-009). Syncs feed the normal ingestion path."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.models import Job
from app.core.tenancy import TenantContext
from app.domains.audit import service as audit
from app.domains.connectors.base import Connector, ConnectorError
from app.domains.connectors.demo import DemoConnector
from app.domains.ingestion import service as ingestion
from app.domains.ingestion.models import DataSource, ImportBatch

SYNC_JOB = "connector_sync"

CONNECTORS: dict[str, Connector] = {c.key: c for c in (DemoConnector(),)}


def get_connector(key: str | None) -> Connector:
    if key not in CONNECTORS:
        raise ConnectorError("Unknown connector")
    return CONNECTORS[key]  # type: ignore[index]


def create_connector_source(session: Session, ctx: TenantContext, *, name: str, connector_key: str,
                            config: dict) -> DataSource:
    try:
        connector = get_connector(connector_key)
        clean = connector.validate_config(config)
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return ingestion.create_source(session, ctx, name=name, kind="connector", connector_key=connector_key,
                                   config=clean, is_demo=connector.is_demo)


def request_sync(session: Session, ctx: TenantContext, source: DataSource, stage: str) -> Job:
    if source.kind != "connector":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only connector sources can be synced")
    try:
        get_connector(source.connector_key).available(source.config, stage)
    except ConnectorError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    job = jobs.enqueue(session, kind=SYNC_JOB, org_id=ctx.org_id,
                       payload={"source_id": str(source.id), "stage": stage, "requested_by": str(ctx.user_id)})
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="connector.sync_requested",
                 entity="data_source", entity_id=source.id, payload={"stage": stage})
    return job


def run_sync(session: Session, source: DataSource, stage: str, actor_id: uuid.UUID,
             job_id: uuid.UUID | None = None) -> list[ImportBatch]:
    """Fetch every available record type in dependency order and commit each through ingestion.

    One transaction: a failure part-way leaves no partial sync behind.
    """
    connector = get_connector(source.connector_key)
    ctx = TenantContext(user_id=actor_id, org_id=source.org_id, role="admin")
    batches = []
    for record_type in connector.available(source.config, stage):
        filename, data = connector.fetch(source.config, stage, record_type)
        batch = ingestion.start_import(session, ctx, source, record_type, filename, data)
        if not batch.profile["can_commit"]:
            raise jobs.JobError(f"{record_type}: required fields missing from connector output")
        batch.job_id = job_id
        batch.status = "running"
        ingestion.commit_batch(session, batch)
        session.flush()
        batches.append(batch)
    audit.record(session, org_id=source.org_id, actor_id=actor_id, action="connector.synced", entity="data_source",
                 entity_id=source.id,
                 payload={"stage": stage, "is_demo": source.is_demo,
                          "counts": {b.record_type: b.counts for b in batches}})
    return batches


def _sync_handler(session: Session, job: Job) -> None:
    source = session.get(DataSource, uuid.UUID(job.payload["source_id"]))
    if source is None or source.org_id != job.org_id:
        raise jobs.JobError("Data source not found")
    try:
        run_sync(session, source, job.payload["stage"], uuid.UUID(job.payload["requested_by"]), job.id)
    except ConnectorError as exc:
        raise jobs.JobError(str(exc)) from None


jobs.register(SYNC_JOB)(_sync_handler)

"""Organization settings, retention and data deletion (BE-032, FR-38, FR-41, GR-08, GR-10).

Settings live in organization.settings:
    refresh_interval_minutes  scheduled check runs (0 = off)            (FR-10)
    ai_provider               "stub" (default, offline) | "anthropic"   (GR-08, audited opt-in)
    retention_days            uploaded raw files (import CSVs, error reports, contract originals and
                              their extracted text) older than this are purged; canonical records and
                              finding evidence stay until the org's data is deleted (decision 0007 D-4)
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.storage import get_store
from app.core.tenancy import TenantContext
from app.domains.access.models import Organization
from app.domains.ai.registry import EXTERNAL, configured, configured_external
from app.domains.audit import service as audit
from app.domains.audit.models import AuditEvent
from app.domains.contracts.models import Document
from app.domains.ingestion.models import ImportBatch

PURGED = "purged"


class SettingsOut(BaseModel):
    organization_name: str
    short_code: str
    is_demo: bool
    refresh_interval_minutes: int
    ai_provider: Literal["stub", "anthropic", "openai"]
    ai_external_available: bool  # is any external provider configured on this server?
    ai_available_providers: list[str]  # external providers with a key on this server (decision 0010)
    retention_days: int | None
    pricing_target_margin_pct: Decimal


class SettingsIn(BaseModel):
    refresh_interval_minutes: int | None = Field(default=None, ge=0, le=10080)
    ai_provider: Literal["stub", "anthropic", "openai"] | None = None
    retention_days: int | None = Field(default=None, ge=30, le=3650)
    clear_retention: bool = False
    pricing_target_margin_pct: Decimal | None = Field(default=None, ge=0, le=90)


def read(org: Organization) -> SettingsOut:
    s = org.settings or {}
    return SettingsOut(
        organization_name=org.name, short_code=org.short_code, is_demo=org.is_demo,
        refresh_interval_minutes=int(s.get("refresh_interval_minutes") or 0),
        ai_provider=s.get("ai_provider", "stub"), ai_external_available=bool(configured_external()),
        ai_available_providers=configured_external(),
        retention_days=s.get("retention_days"),
        pricing_target_margin_pct=Decimal(str(s.get("pricing_target_margin_pct", "20"))),
    )


def update(session: Session, ctx: TenantContext, data: SettingsIn) -> SettingsOut:
    org = session.get(Organization, ctx.org_id)
    assert org is not None
    current = dict(org.settings or {})
    changes: dict[str, Any] = {}
    if data.refresh_interval_minutes is not None:
        changes["refresh_interval_minutes"] = data.refresh_interval_minutes
    if data.ai_provider is not None:
        if data.ai_provider in EXTERNAL and not configured(data.ai_provider):
            label, env = EXTERNAL[data.ai_provider]
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{label} isn't configured on this server ({env} is unset)")
        changes["ai_provider"] = data.ai_provider
    if data.clear_retention:
        changes["retention_days"] = None
    elif data.retention_days is not None:
        changes["retention_days"] = data.retention_days
    if data.pricing_target_margin_pct is not None:
        changes["pricing_target_margin_pct"] = format(data.pricing_target_margin_pct.normalize(), "f")
    changes = {k: v for k, v in changes.items() if current.get(k) != v}
    if changes:
        org.settings = {**current, **changes}
        audit.record(session, org_id=org.id, actor_id=ctx.user_id, action="settings.updated", entity="organization",
                     entity_id=org.id, payload={"changes": changes, "previous": {k: current.get(k) for k in changes}})
        if "ai_provider" in changes:
            # GR-08: the opt-in (or opt-out) for sending document text to an external model is its own event.
            audit.record(session, org_id=org.id, actor_id=ctx.user_id,
                         action="ai.external_provider_enabled" if changes["ai_provider"] in EXTERNAL
                         else "ai.external_provider_disabled", entity="organization", entity_id=org.id,
                         payload={"provider": changes["ai_provider"]})
    return read(org)


def delete_organization_data(session: Session, ctx: TenantContext, confirm_short_code: str) -> dict[str, int]:
    """FR-41: remove all of the org's rows and files, leaving the org row and one tombstone audit event."""
    org = session.get(Organization, ctx.org_id)
    assert org is not None
    if confirm_short_code.strip().upper() != org.short_code:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type the organization code exactly to confirm")
    keep = {"id": org.id, "name": org.name, "short_code": org.short_code, "business_type": org.business_type,
            "is_demo": org.is_demo}
    files = get_store().delete_org(org.id)
    events = session.execute(delete(AuditEvent).where(AuditEvent.org_id == org.id)).rowcount  # type: ignore[attr-defined]
    session.delete(org)  # cascades to every tenant table (OrgScopedMixin, users, jobs)
    session.flush()
    deleted_at = datetime.now(UTC)
    session.add(Organization(**keep, settings={"data_deleted_at": deleted_at.isoformat()}))
    session.flush()
    # The chain restarts with a single tombstone; the deleting user no longer exists, so it's recorded by id.
    audit.record(session, org_id=keep["id"], actor_id=None, action="organization.data_deleted",
                 entity="organization", entity_id=keep["id"],
                 payload={"deleted_by_user_id": str(ctx.user_id), "files_removed": files,
                          "audit_events_removed": events, "deleted_at": deleted_at.isoformat()})
    return {"files_removed": files, "audit_events_removed": events}


def purge_expired_files(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Retention: delete uploaded raw files older than each org's retention period."""
    now = now or datetime.now(UTC)
    totals = {"import_files": 0, "documents": 0}
    for org in session.scalars(select(Organization)):
        days = (org.settings or {}).get("retention_days")
        if not days:
            continue
        cutoff = now - timedelta(days=int(days))
        store = get_store()
        purged = {"import_files": 0, "documents": 0}
        for b in session.scalars(select(ImportBatch).where(ImportBatch.org_id == org.id,
                                                           ImportBatch.created_at < cutoff,
                                                           ImportBatch.file_ref != PURGED)):
            for ref in (b.file_ref, b.error_report_ref):
                if ref and ref != PURGED:
                    store.delete(ref)
            b.file_ref = PURGED
            b.error_report_ref = None
            purged["import_files"] += 1
        for d in session.scalars(select(Document).where(Document.org_id == org.id, Document.created_at < cutoff,
                                                        Document.storage_key != PURGED)):
            store.delete(d.storage_key)
            d.storage_key = PURGED
            d.text_extracted = None
            purged["documents"] += 1
        if any(purged.values()):
            audit.record(session, org_id=org.id, actor_id=None, action="retention.purged", entity="organization",
                         entity_id=org.id, payload={"retention_days": days, **purged})
        for k in totals:
            totals[k] += purged[k]
    return totals


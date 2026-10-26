"""AI assistance endpoints (BE-031). Lives in `ai` so `cases`/`ingestion` never need to import it."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.storage import get_store
from app.core.tenancy import TenantContext, get_scoped
from app.domains.access.models import Organization
from app.domains.access.permissions import Cap, require
from app.domains.ai.assist import MappingSuggestion, finding_facts
from app.domains.ai.provider import ProviderError
from app.domains.ai.registry import provider_for
from app.domains.audit import service as audit
from app.domains.ingestion.models import ImportBatch
from app.domains.ingestion.parsing import CsvError, read_csv
from app.domains.ingestion.registry import RECORDS
from app.domains.ingestion.service import resolve_refs
from app.domains.rules.models import Finding

router = APIRouter(tags=["ai"])
MAX_SUMMARY = 1000


class SuggestionsOut(BaseModel):
    provider: str
    external: bool
    suggestions: list[MappingSuggestion]


class SummaryOut(BaseModel):
    provider: str
    ai_summary: str


_ID_LIKE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,79}$")


def value_evidence(session: Session, batch: ImportBatch, spec, columns: list[str], rows: list[dict[str, str]],
                   taken: set[str]) -> list[MappingSuggestion]:
    """Deterministic, offline: suggest from what the values are, not just what the header says."""
    out: list[MappingSuggestion] = []
    used = set(taken)
    for col in columns:
        values = [r.get(col, "").strip() for r in rows[:200]]
        present = {v for v in values if v}
        if not present:
            continue
        for f in spec.fields:
            if f.type != "ref" or f.name in used:
                continue
            found = resolve_refs(session, batch.org_id, batch.data_source_id, f.ref, present)
            if len(found) == len(present):
                out.append(MappingSuggestion(column=col, field=f.name, confidence=0.95,
                                             reason=f"every value matches an existing {f.ref.replace('_', ' ')} id"))
                used.add(f.name)
                break
        else:
            idf = spec.id_field
            filled = [v for v in values if v]
            unique_ids = len(present) == len(filled) == len(values) and all(_ID_LIKE.match(v) for v in present)
            if idf.name not in used and unique_ids:
                out.append(MappingSuggestion(column=col, field=idf.name, confidence=0.7,
                                             reason="values are unique identifiers"))
                used.add(idf.name)
    return out


@router.get("/api/imports/{import_id}/mapping-suggestions", response_model=SuggestionsOut)
def mapping_suggestions(import_id: uuid.UUID, ctx: TenantContext = Depends(require(Cap.MANAGE_DATA)),
                        session: Session = Depends(get_session)):
    """FR-39: suggestions for still-unmapped columns. Never applied; the admin applies and saves."""
    batch = get_scoped(session, ImportBatch, import_id, ctx)
    spec = RECORDS[batch.record_type]
    mapping = batch.profile.get("mapping", {})
    try:
        headers, rows = read_csv(get_store().get(batch.file_ref))
    except (CsvError, FileNotFoundError):
        raise HTTPException(status.HTTP_410_GONE, "The uploaded file is no longer available") from None
    unmapped = [h for h in headers if h not in mapping]
    taken = set(mapping.values())
    provider = provider_for(session.get(Organization, ctx.org_id).settings)  # type: ignore[union-attr]
    evidence = value_evidence(session, batch, spec, unmapped, rows, taken)
    rest = [h for h in unmapped if h not in {e.column for e in evidence}]
    taken_now = taken | {e.field for e in evidence}
    samples = {h: [r.get(h, "") for r in rows[:3]] for h in rest}
    try:
        raw = evidence + (provider.suggest_mapping(rest, samples, spec, taken_now) if rest else [])
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    valid, seen = [], set(taken)
    for s in raw:  # never trust: only real unmapped columns, real free fields, one each
        if s.column in unmapped and spec.get(s.field) and s.field not in seen:
            valid.append(s)
            seen.add(s.field)
    return SuggestionsOut(provider=provider.name, external=provider.external, suggestions=valid)


@router.post("/api/findings/{finding_id}/summary", response_model=SummaryOut)
def summarize(finding_id: uuid.UUID, ctx: TenantContext = Depends(require(Cap.VIEW_FINDINGS)),
              session: Session = Depends(get_session)):
    """FR-40: AI-generated summary stored in ai_summary; labelled in the UI; never read by any calculation."""
    f = get_scoped(session, Finding, finding_id, ctx)
    provider = provider_for(session.get(Organization, ctx.org_id).settings)  # type: ignore[union-attr]
    try:
        text = provider.summarize_finding(finding_facts(f))
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    f.ai_summary = " ".join(text.split())[:MAX_SUMMARY]
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="ai.summary_generated", entity="finding",
                 entity_id=f.id, payload={"provider": provider.name, "external": provider.external})
    session.commit()
    return SummaryOut(provider=provider.name, ai_summary=f.ai_summary)

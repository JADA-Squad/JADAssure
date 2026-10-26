"""Data sources, profiling, mapping and idempotent import commit (BE-006, BE-007).

Flow: upload → profile (status 'profiled') → optional mapping edit → commit (job) → upserted
canonical records, error report and import history. Re-importing the same rows changes nothing
(GR-11): rows upsert by (org, data source, source record id), and a content hash detects changes.
"""

import csv
import hashlib
import io
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import jobs
from app.core.models import Job
from app.core.storage import get_store
from app.core.tenancy import TenantContext, get_scoped, scoped
from app.domains.audit import service as audit
from app.domains.ingestion.models import DataSource, ImportBatch
from app.domains.ingestion.models_map import MODELS
from app.domains.ingestion.parsing import CsvError, canonical_text, csv_safe, parse_value, read_csv, suggest_mapping
from app.domains.ingestion.registry import RECORDS, FieldSpec, RecordSpec

IMPORT_JOB = "import_commit"
_DATE_PAIRS = (("start_date", "end_date"), ("effective_from", "effective_to"), ("service_period_start", "service_period_end"))
_ZERO_DEFAULTS = {"invoice_line": ("discount_pct", "tax_amount")}
_SAMPLE_LIMIT = 5


# ---------------------------------------------------------------- data sources

def create_source(session: Session, ctx: TenantContext, *, name: str, kind: str = "csv",
                  connector_key: str | None = None, config: dict | None = None, is_demo: bool = False) -> DataSource:
    source = DataSource(org_id=ctx.org_id, name=name, kind=kind, connector_key=connector_key, config=config or {},
                        is_demo=is_demo, mapping={})
    session.add(source)
    session.flush()
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="data_source.created",
                 entity="data_source", entity_id=source.id, payload={"kind": kind, "connector_key": connector_key})
    return source


def list_sources(session: Session, ctx: TenantContext) -> list[DataSource]:
    return list(session.scalars(scoped(DataSource, ctx).order_by(DataSource.created_at)))


# ---------------------------------------------------------------- references

def resolve_refs(session: Session, org_id: uuid.UUID, data_source_id: uuid.UUID, record_type: str,
                 source_ids: set[str]) -> dict[str, uuid.UUID]:
    """Map source ids to canonical ids within the org, preferring records from the same data source."""
    if not source_ids:
        return {}
    model = MODELS[record_type]
    out: dict[str, uuid.UUID] = {}
    ids = list(source_ids)
    for i in range(0, len(ids), 5000):
        rows = session.execute(
            select(model.source_record_id, model.id, model.data_source_id)
            .where(model.org_id == org_id, model.source_record_id.in_(ids[i:i + 5000]))
        )
        for sid, id_, ds in rows:
            if sid not in out or ds == data_source_id:
                out[sid] = id_
    return out


def _existing(session: Session, org_id: uuid.UUID, data_source_id: uuid.UUID, record_type: str,
              source_ids: set[str]) -> dict[str, Any]:
    model = MODELS[record_type]
    out: dict[str, Any] = {}
    ids = list(source_ids)
    for i in range(0, len(ids), 5000):
        for obj in session.scalars(select(model).where(
            model.org_id == org_id, model.data_source_id == data_source_id, model.source_record_id.in_(ids[i:i + 5000])
        )):
            out[obj.source_record_id] = obj
    return out


# ---------------------------------------------------------------- profiling

def _validate_mapping(spec: RecordSpec, headers: list[str], mapping: dict[str, str]) -> dict[str, str]:
    clean = {col: field for col, field in mapping.items() if field}
    unknown_cols = [c for c in clean if c not in headers]
    unknown_fields = [f for f in clean.values() if spec.get(f) is None]
    if unknown_cols or unknown_fields:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Mapping refers to unknown columns {unknown_cols} or fields {unknown_fields}")
    dupes = [f for f, n in Counter(clean.values()).items() if n > 1]
    if dupes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Fields mapped more than once: {dupes}")
    return clean


def build_profile(session: Session, org_id: uuid.UUID, source: DataSource, spec: RecordSpec, headers: list[str],
                  rows: list[dict[str, str]], mapping: dict[str, str], suggested: dict[str, str]) -> dict[str, Any]:
    """FR-06: what will happen if this file is committed with this mapping."""
    inverse = {field: col for col, field in mapping.items()}
    fields_out = []
    for f in spec.fields:
        col = inverse.get(f.name)
        stat: dict[str, Any] = {"field": f.name, "required": f.required, "mapped_from": col,
                                "empty_count": 0, "invalid_count": 0, "invalid_samples": []}
        if col is not None:
            for n, row in enumerate(rows, start=2):
                value, err = parse_value(f, row.get(col, ""))
                if err:
                    stat["invalid_count"] += 1
                    if len(stat["invalid_samples"]) < 3:
                        stat["invalid_samples"].append({"row": n, "value": row.get(col, "")[:60], "error": err})
                elif value is None:
                    stat["empty_count"] += 1
        fields_out.append(stat)

    unmatched = []
    for f in spec.fields:
        col = inverse.get(f.name)
        if f.type != "ref" or col is None:
            continue
        values = {row[col].strip() for row in rows if row.get(col, "").strip()}
        found = resolve_refs(session, org_id, source.id, f.ref, values)  # type: ignore[arg-type]
        missing = sorted(values - found.keys())
        if missing:
            affected = sum(1 for row in rows if row.get(col, "").strip() in set(missing))
            unmatched.append({"field": f.name, "target": f.ref, "distinct": len(missing), "rows": affected,
                              "samples": missing[:_SAMPLE_LIMIT]})

    id_col = inverse.get(spec.id_field.name)
    ids = [row[id_col].strip() for row in rows if id_col and row.get(id_col, "").strip()]
    existing = len(_existing(session, org_id, source.id, spec.record_type, set(ids))) if ids else 0

    missing_required = [f.name for f in spec.fields if f.required and f.name not in inverse]
    return {
        "row_count": len(rows),
        "headers": headers,
        "mapping": mapping,
        "suggested_columns": sorted(c for c in suggested if mapping.get(c) == suggested[c]),
        "unmapped_columns": [h for h in headers if h not in mapping],
        "missing_required_fields": missing_required,
        "fields": fields_out,
        "unmatched_references": unmatched,
        "duplicate_ids_in_file": sum(n - 1 for n in Counter(ids).values() if n > 1),
        "existing_records": existing,
        "new_records": len(set(ids)) - existing,
        "sample_rows": [{inverse_f: row.get(col, "") for inverse_f, col in inverse.items()} for row in rows[:_SAMPLE_LIMIT]],
        "can_commit": not missing_required,
    }


def _load_file(batch: ImportBatch) -> tuple[list[str], list[dict[str, str]]]:
    return read_csv(get_store().get(batch.file_ref))


def start_import(session: Session, ctx: TenantContext, source: DataSource, record_type: str, filename: str,
                 data: bytes) -> ImportBatch:
    """Store the upload and profile it with the saved mapping, or a suggested one (FR-05, FR-06)."""
    try:
        headers, rows = read_csv(data)
    except CsvError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    spec = RECORDS[record_type]
    suggested = suggest_mapping(headers, spec)
    saved = {c: f for c, f in (source.mapping or {}).get(record_type, {}).items() if c in headers and spec.get(f)}
    mapping = saved or suggested
    batch = ImportBatch(
        org_id=ctx.org_id, data_source_id=source.id, record_type=record_type, filename=filename[:255],
        file_ref=get_store().put(ctx.org_id, "imports", data, ".csv"), status="profiled", counts={},
        created_by=ctx.user_id,
    )
    batch.profile = build_profile(session, ctx.org_id, source, spec, headers, rows, mapping, suggested)
    session.add(batch)
    session.flush()
    return batch


def set_mapping(session: Session, ctx: TenantContext, batch: ImportBatch, mapping: dict[str, str]) -> ImportBatch:
    """Save the admin's mapping on the data source (reused next time) and re-profile."""
    if batch.status != "profiled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Mapping can only change before the import is committed")
    source = get_scoped(session, DataSource, batch.data_source_id, ctx)
    spec = RECORDS[batch.record_type]
    headers, rows = _load_file(batch)
    mapping = _validate_mapping(spec, headers, mapping)
    source.mapping = {**(source.mapping or {}), batch.record_type: mapping}
    batch.profile = build_profile(session, ctx.org_id, source, spec, headers, rows, mapping,
                                  suggest_mapping(headers, spec))
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="import.mapping_saved", entity="data_source",
                 entity_id=source.id, payload={"record_type": batch.record_type, "mapped_fields": sorted(mapping.values())})
    return batch


def request_commit(session: Session, ctx: TenantContext, batch: ImportBatch) -> ImportBatch:
    if batch.status != "profiled":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Import is already {batch.status}")
    if not batch.profile.get("can_commit"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Map every required field before committing: "
                            + ", ".join(batch.profile.get("missing_required_fields", [])))
    source = get_scoped(session, DataSource, batch.data_source_id, ctx)
    source.mapping = {**(source.mapping or {}), batch.record_type: batch.profile["mapping"]}
    job = jobs.enqueue(session, kind=IMPORT_JOB, org_id=ctx.org_id, payload={"import_id": str(batch.id)})
    batch.status = "queued"
    batch.job_id = job.id
    audit.record(session, org_id=ctx.org_id, actor_id=ctx.user_id, action="import.commit_requested",
                 entity="import_batch", entity_id=batch.id,
                 payload={"record_type": batch.record_type, "rows": batch.profile.get("row_count")})
    return batch


# ---------------------------------------------------------------- commit (worker)

def _row_hash(values: dict[str, Any]) -> str:
    canonical = json.dumps({k: canonical_text(v) for k, v in values.items()}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _attrs(spec: RecordSpec, values: dict[str, Any], ref_ids: dict[str, uuid.UUID]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    params: dict[str, Any] = {}
    for f in spec.fields[1:]:
        if f.type == "ref":
            attrs[f.model_attr] = ref_ids.get(f.name)
        elif f.model_attr.startswith("params."):
            if values.get(f.name) is not None:
                params[f.model_attr.split(".", 1)[1]] = canonical_text(values[f.name])
        else:
            attrs[f.model_attr] = values.get(f.name)
    if any(f.model_attr.startswith("params.") for f in spec.fields):
        attrs["params"] = params
    for name in _ZERO_DEFAULTS.get(spec.record_type, ()):
        if attrs.get(name) is None:
            attrs[name] = Decimal("0")
    return attrs


def _row_errors(spec: RecordSpec, inverse: dict[str, str], row: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, Any] = {}
    errors: list[str] = []
    for f in spec.fields:
        col = inverse.get(f.name)
        value, err = parse_value(f, row.get(col, "") if col else "")
        if err:
            errors.append(f"{f.name}: {err}")
        elif value is None and f.required:
            errors.append(f"{f.name}: required")
        else:
            values[f.name] = value
    for start, end in _DATE_PAIRS:
        if values.get(start) and values.get(end) and values[end] < values[start]:
            errors.append(f"{end}: is before {start}")
    return values, errors


def process_import(session: Session, job: Job) -> None:
    """Job handler: validate every row and upsert canonical records (FR-07, FR-08)."""
    batch = session.get(ImportBatch, uuid.UUID(job.payload["import_id"]))
    if batch is None or batch.org_id != job.org_id:
        raise jobs.JobError("Import batch not found")
    source = session.get(DataSource, batch.data_source_id)
    spec = RECORDS[batch.record_type]
    model = MODELS[batch.record_type]
    inverse = {field: col for col, field in batch.profile["mapping"].items()}
    try:
        _, rows = _load_file(batch)
    except (CsvError, FileNotFoundError) as exc:
        raise jobs.JobError(f"Could not read the uploaded file: {exc}") from None

    parsed = [(n, row, *_row_errors(spec, inverse, row)) for n, row in enumerate(rows, start=2)]

    ref_maps: dict[str, dict[str, uuid.UUID]] = {}
    for f in spec.fields:
        if f.type == "ref":
            wanted = {v[f.name] for _, _, v, errs in parsed if not errs and v.get(f.name)}
            ref_maps[f.name] = resolve_refs(session, batch.org_id, source.id, f.ref, wanted)  # type: ignore[arg-type]

    existing = _existing(session, batch.org_id, source.id, spec.record_type,
                         {v[spec.id_field.name] for _, _, v, errs in parsed if not errs})
    now = datetime.now(UTC)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0}
    rejected: list[tuple[int, str, str]] = []

    for n, row, values, errors in parsed:
        ref_ids: dict[str, uuid.UUID] = {}
        for f in spec.fields:
            if f.type == "ref" and values.get(f.name):
                found = ref_maps[f.name].get(values[f.name])
                if found is None:
                    errors.append(f"{f.name}: no {f.ref.replace('_', ' ')} with id '{values[f.name]}'")  # type: ignore[union-attr]
                else:
                    ref_ids[f.name] = found
        sid = values.get(spec.id_field.name) or ""
        if errors:
            counts["rejected"] += 1
            rejected.append((n, sid, "; ".join(errors)))
            continue

        attrs = _attrs(spec, values, ref_ids)
        if spec.record_type == "commercial_term":
            # Decision 0001 D-6: a structured admin import is the confirmation.
            attrs.update(status="confirmed", origin="import", confirmed_by=batch.created_by, confirmed_at=now,
                         ambiguous=False)
        digest = _row_hash(values)
        obj = existing.get(sid)
        if obj is None:
            obj = model(org_id=batch.org_id, data_source_id=source.id, source_record_id=sid, **attrs)
            session.add(obj)
            existing[sid] = obj
            counts["inserted"] += 1
        elif obj.source_hash == digest:
            counts["unchanged"] += 1
            continue
        else:
            for k, v in attrs.items():
                setattr(obj, k, v)
            counts["updated"] += 1
        obj.source_payload = row
        obj.source_hash = digest
        obj.import_id = batch.id
        session.flush()

    if rejected:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["row_number", "source_record_id", "errors"])
        for n, sid, msg in rejected:
            w.writerow([n, csv_safe(sid), csv_safe(msg)])
        batch.error_report_ref = get_store().put(batch.org_id, "import-errors", buf.getvalue().encode("utf-8"), ".csv")
    batch.counts = counts
    batch.status = "succeeded"
    batch.error = None
    audit.record(session, org_id=batch.org_id, actor_id=batch.created_by, action="import.completed",
                 entity="import_batch", entity_id=batch.id, payload={"record_type": batch.record_type, **counts})


def _on_failure(session: Session, job: Job) -> None:
    batch = session.get(ImportBatch, uuid.UUID(job.payload["import_id"]))
    if batch is not None:
        batch.status = "failed"
        batch.error = job.last_error


def _on_retry(session: Session, job: Job) -> None:
    batch = session.get(ImportBatch, uuid.UUID(job.payload["import_id"]))
    if batch is not None:
        batch.status = "queued"
        batch.error = None


jobs.register(IMPORT_JOB, on_failure=_on_failure, on_retry=_on_retry)(process_import)

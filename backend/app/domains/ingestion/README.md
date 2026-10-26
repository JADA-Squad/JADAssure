# ingestion

**Built (M1):** BE-005 (field registry, templates), BE-006 (data sources, mapping, profiling) and
BE-007 (idempotent commit with error reports). Status: Built, awaiting owner checkpoint.

- `registry.py`: the single definition of every importable field. Templates, profiling,
  validation and upserts all read it. Add a field here and nowhere else.
- `parsing.py`: CSV reading with limits (10 MB, 50,000 rows, UTF-8), value conversion, header
  suggestions, and `csv_safe()` for formula-injection-safe exports (GR-07).
- `service.py`: `start_import` (store + profile), `set_mapping` (save per source + re-profile),
  `request_commit` (enqueue `import_commit`), `commit_batch` (validate + upsert; also used by
  connector syncs).
- Canonical revenue records (customer, billable event, invoice, line, credit, payment,
  allocation, cost) live in `models.py`. Agreements and terms live in `contracts`, but are upserted
  from here.
- Decisions: 0002 D-1 (identity and change detection), D-2 (reference resolution), D-3 (partial
  acceptance), D-4 (suggestions), D-5 (storage).

## Scope
Field registry, CSV templates, data sources, mappings, profiling, import commit and the canonical revenue records (customers, billable events, invoices, credits, payments, costs).

## Task IDs
BE-005, BE-006, BE-007

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

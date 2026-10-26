# contracts

**Built (M1):** BE-011 (agreements API and term resolution). Status: Built, awaiting owner
checkpoint. BE-027, BE-029 and BE-030 (documents, extraction, confirmation) are Backlog for M4.

- `terms.py`: `confirmed_terms(org_id)` is **the only query the engine may use to read terms**
  (GR-03). `resolve_terms(...)` returns the confirmed terms of the version in effect on a date,
  where the highest version number wins on overlap, filtered to terms effective on that date.
- Terms imported by CSV are stored `confirmed`; extracted terms will be stored `proposed`
  (decision 0001 D-6).
- API: `GET /api/agreements`, `GET /api/agreements/{id}` (versions with every term and its status),
  `GET /api/agreements/{id}/terms?on=YYYY-MM-DD&item_code=…` (what the engine would apply).

## Scope
Agreements, agreement versions, commercial terms, contract documents, extraction orchestration and term confirmation.

## Task IDs
BE-011, BE-027, BE-029, BE-030

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

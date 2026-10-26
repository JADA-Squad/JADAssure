# contracts

**Built:** BE-011 (M1), BE-027, BE-029, BE-030 (M4). Status: Built, awaiting owner checkpoint.

- `terms.py`: `confirmed_terms()` is the only query the engine may use (GR-03); `resolve_terms()`
  and the in-memory `TermBook`.
- `documents.py`: PDF/DOCX/TXT upload with signature checks, 10 MB cap, sha256, DocumentStore, and
  text extraction.
- `extraction.py`: the `extract_terms` job (schema → verbatim passage → version in effect →
  `proposed`), plus `confirm()` (optional edits) and `reject()`, all audited. Decision 0007
  D-1, D-2.
- API: `/api/agreements[/{id}[/terms|/documents]]`, `/api/documents/{id}/original|extract`,
  `/api/terms?status=…`, `/api/terms/{id}/confirm|reject`.

## Scope
Agreements, agreement versions, commercial terms, contract documents, extraction orchestration and term confirmation.

## Task IDs
BE-011, BE-027, BE-029, BE-030

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

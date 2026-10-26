# audit

**Built (M0):** BE-004. `service.record()` appends a hash-chained event inside the caller's
transaction, serialized per org with a Postgres advisory lock. `service.verify()` recomputes the
chain. Endpoints: `GET /api/audit` and `GET /api/audit/verify` (admin, approver).

Call `record()` from every state-changing service (GR-10). Payloads hold ids, roles and decisions,
never record content or credentials.

## Scope
The hash-chained, append-only audit log and its verification.

## Task IDs
BE-004

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

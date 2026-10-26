# recovery

**Built (M3):** BE-023. Status: Built, awaiting owner checkpoint. BE-024 (root-cause
recurrence and prevented-recurrence estimate) is Backlog for M5. Root causes are already captured
at proposal.

- `service.py`: `reconcile()` matches invoices carrying a correction reference (billed) and
  allocations to them (cash, capped at the correction, GR-04). Recovery events are unique per
  source record (GR-11). Imports queue the `recovery_reconcile` job.
- `router.py`: `GET /api/recovery/corrections` (tracker) and the DEMO-only `simulate` endpoint.
- `demo_simulation.py`: writes the corrected invoice and payment through ingestion for `is_demo`
  orgs only (decision 0006 D-6).

## Scope
Matching corrections to billed invoices and payments, root cause and recurrence. Must never import `ai`.

## Task IDs
BE-023, BE-024

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

# reporting

**Built (M3–M5):** BE-025, BE-026. Status: Built, awaiting owner checkpoint.

- `service.outcomes()`: the six figures per currency, each computed from its own source (design
  §2.5). Rejected findings are only a count (GR-05). Cash is walked per correction and capped
  (GR-04). Also status counts, a 12-month trend and the top root-cause categories.
- `service.prevented_recurrence()` (BE-024): confirmed findings' value × later clean months.
- `pricing.opportunities()` (BE-026): confirmed contract net price vs cost record in the same
  currency, below the org's target margin (default 20%). Never part of leakage or recovery.
- API: `GET /api/reports/outcomes` and `GET /api/reports/pricing-opportunities` (all roles via
  `view_reports`). Decision 0008.

## Scope
The six outcome figures, trends, recurring causes and pricing opportunities. Must never import `ai`.

## Task IDs
BE-025, BE-026

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

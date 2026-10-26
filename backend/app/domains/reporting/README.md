# reporting

**Built (M3):** BE-025. Status: Built, awaiting owner checkpoint. BE-026 (pricing
opportunities) is Backlog for M5.

- `service.outcomes()`: the six figures per currency, each computed from its own source (design
  §2.5). Rejected findings are only a count (GR-05). Cash is walked per correction and capped
  (GR-04). Also status counts, a 12-month trend and the top root-cause categories.
- API: `GET /api/reports/outcomes` (all roles via `view_reports`).

## Scope
The six outcome figures, trends, recurring causes and pricing opportunities. Must never import `ai`.

## Task IDs
BE-025, BE-026

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

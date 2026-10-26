# cases

**Built (M2):** BE-020 (findings queue, detail, timeline, comments). Status: Built, awaiting owner
checkpoint. BE-021 (workflow, separation of duties, immutability) and BE-022 (prepared
corrections) are Backlog for M3.

- `service.py`: priority = value × confidence weight (high 1.0, medium 0.7, low 0.4). Filters,
  detail with timeline (detection + investigation events + approvals), and comments (the audit
  records the fact of a comment, not its text).
- The `Finding` model lives in `rules` (generation owns it). `cases` owns the investigation events,
  approvals and corrections around it.

## Scope
Findings queue and detail API, workflow transitions, comments, approvals and prepared corrections. Must never import `ai`.

## Task IDs
BE-020, BE-021, BE-022

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

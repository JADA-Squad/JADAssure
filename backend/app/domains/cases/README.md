# cases

**Built:** BE-020 (M2), BE-021 and BE-022 (M3). Status: Built, awaiting owner checkpoint.

- `service.py`: queue, filters, detail (timeline, correction, `available_actions`), comments.
- `workflow.py`: the design §2.5 transitions with row locks, from-state checks, separation of
  duties (GR-12), timeline + audit events. `system_transition()` is only for recovery-driven
  moves (approved → billed → recovered).
- `corrections.py`: one prepared correction per approval (`JA-<org>-0001`), CSV/JSON export. No
  send path (GR-01).
- Terminal findings are immutable through a database trigger (migration 0004, GR-13).
- The `Finding` model lives in `rules`; `cases` owns investigation events, approvals and corrections.
- Decisions: 0006 D-1..D-4, D-8.

## Scope
Findings queue and detail API, workflow transitions, comments, approvals and prepared corrections. Must never import `ai`.

## Task IDs
BE-020, BE-021, BE-022

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

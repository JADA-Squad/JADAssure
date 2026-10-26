# access

**Built:** BE-002, BE-003 (M0) and BE-032 (M4). Status: Built, awaiting owner checkpoint.

- `permissions.py`: the role → capability matrix and `require` / `require_any`.
- `settings.py`: refresh interval, AI provider (audited opt-in, key required), retention (hourly
  purge of raw uploads), and organization data deletion with a tombstone (decision 0007 D-4, D-5).
- Tenant context and scoping helpers live in `app/core/tenancy.py`.

## Scope
Organizations, users, roles, authentication, the permission matrix, tenant scoping, org settings and retention.

## Task IDs
BE-002, BE-003, BE-032

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

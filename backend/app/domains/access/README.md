# access

**Built (M0):** BE-002 (signup, login, user management) and BE-003 (permission matrix, tenant
scoping). The status on the task board is Built and waits for owner checkpoint. BE-032 (settings,
retention, deletion) is Backlog.

- `permissions.py`: the single role → capability matrix (design §3.7) and the `require(cap)`
  dependency. Every non-public route must depend on it, or on `current_context`. A test enforces
  this.
- Tenant context and the `scoped()` / `get_scoped()` helpers live in `app/core/tenancy.py`, because
  every domain uses them. The org id comes only from the token and is checked against the user row.
- Emails are globally unique and lower-cased (one user, one org: decision 0001 D-5).

## Scope
Organizations, users, roles, authentication, the permission matrix, tenant scoping, org settings and retention.

## Task IDs
BE-002, BE-003, BE-032

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

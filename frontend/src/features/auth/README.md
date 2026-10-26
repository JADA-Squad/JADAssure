# auth

**Built (M0):** FE-001. Login and signup pages, `AuthProvider` (session in `sessionStorage`,
re-validated with `/api/auth/me` on load, automatic sign-out at token expiry or on any 401),
`RequireAuth` and `RequireRole` guards. Navigation is filtered by `NAV_AREAS[].roles` in
`src/app/nav.ts`, which mirrors the backend permission matrix. The API remains the enforcement
point.

## Scope
Login, signup, session handling and role-aware navigation.

## Task IDs
FE-001

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

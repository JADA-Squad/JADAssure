# 0004 — Hosting the pilot on Render

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | Refines 0001 D-1 ("production cloud deployment deferred") for a live pilot URL |

**D-1. Render, single web service, deployed from `main`.** The owner asked for a live URL that
updates when changes land. `render.yaml` defines one Docker web service built from the root
`Dockerfile` (React build, then the Python image) and one Render Postgres. `autoDeploy` redeploys
on every push to `main`. The API serves the built React app on the same origin, so there's no
CORS configuration, no second service, and `/api` paths stay identical to local development.
Owner task: DOC-002.

**D-2. Embedded worker for the pilot.** Render has no free background-worker plan, so
`EMBEDDED_WORKER=true` runs the same `run_loop` (heartbeat, schedule, jobs) in a daemon thread of
the web process. Jobs still use the Postgres queue with `SKIP LOCKED`, so moving the loop to a
separate worker service later is a configuration change.
Owner task: BE-008, BE-010.

**D-3. Safe defaults for a public URL.** `SHOW_DEMO_ACCOUNTS=false` and `ALLOW_SIGNUP=false` on
Render. Demo orgs are seeded on start (idempotent) so the pilot is usable immediately. Access
requires the demo password from the private repo. The container runs as a non-root user.
Owner task: DATA-001, BE-002.

**D-4. Accepted free-plan limitations.** Instances sleep when idle, the free database expires after
30 days, and there's no persistent disk (uploaded files and error reports are lost on redeploy;
records in Postgres are not). All three are documented in `docs/deployment.md` with their fixes.
Upgrade before any real customer data is loaded.
Owner task: DOC-002.

## Open items carried forward

| Item | Blocks | Owner |
|---|---|---|
| Create the Render account, authorize the Render GitHub app for JADA-Squad, apply the Blueprint | Live URL | Shadrack Adeyemi |
| Choose a paid database plan before day 30, or accept data loss | Persisting pilot data | Shadrack Adeyemi |
| S3-compatible DocumentStore adapter | Keeping uploaded files across deploys | Agent, when prioritized |

# Running JADAssure

> Status: written in Phase 0, **before any code exists**. Commands below are the target contract
> for INFRA-001..003. Each section is marked ✅ once verified on a real machine.

## TL;DR

```bash
cp .env.example .env                       # then set JWT_SECRET to a long random value
docker compose up --build                  # db, api, worker, web
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed_demo
```

- UI: http://localhost:5173
- API docs (OpenAPI): http://localhost:8000/api/docs
- Health: http://localhost:8000/api/health

## What runs where

`web` (Vite dev server, port 5173) serves the React app and proxies every `/api/*` request to
`api` (FastAPI on port 8000). `api` validates requests, reads and writes `db` (Postgres 16, port
5432) and enqueues jobs as rows in the `job` table. `worker` (same Python image, different
command) claims jobs: import commits, check runs, term extraction, scheduled refreshes. Uploaded
files live in the `documents` volume mounted into both `api` and `worker`.

## Configuration that MUST be set

| Variable | Why |
|---|---|
| `JWT_SECRET` | Token signing. The API refuses to start if it's unset or still the example value. |
| `DATABASE_URL` | Set by Compose by default. Override only when running outside Docker. |

Optional: `AI_PROVIDER_ALLOWED=anthropic`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`. Even with
these set, each org stays on the offline stub until its admin enables the provider (GR-08).

## The happy path

1. Log in as the DEMO admin of *Cirrus Cloud (demo)* (credentials are shown on the login page,
   demo only).
2. **Data setup** → the demo source → import the baseline files → review the profile → commit.
3. **Run checks now**. The **Findings** queue fills with prioritized findings.
4. Log in as the DEMO analyst → open a wrong-rate finding → read the evidence → propose it with a
   root cause.
5. Log in as the DEMO approver → approve. A prepared correction appears in **Recovery**.
6. As admin, import the follow-up invoice file (carries the correction reference). The finding
   moves to *billed*.
7. Import the follow-up payment file. The finding moves to *recovered*, and **Overview** shows
   cash recovered.
8. Re-import the baseline. Totals don't change.
9. **Agreements**: in *Northwind Advisory (demo)*, upload the demo contract. The ambiguous term
   waits for confirmation.

## Running tests

```bash
docker compose exec api pytest                 # backend: unit, API, acceptance
docker compose exec api pytest -m acceptance    # the eight scenarios only (QA-001)
cd frontend && npm run typecheck && npm run build
```

Backend tests use a separate database (`jadassure_test`) created automatically by the test
harness.

## Known environment gotchas

- **Docker Desktop must be running.** On 2026-10-26 the dev machine had Docker Compose installed
  but the engine stopped (`dockerDesktopLinuxEngine` pipe not found). Start Docker Desktop first.
- Windows: keep the repo on a local NTFS path. Vite file watching inside Docker on Windows may
  need `CHOKIDAR_USEPOLLING=true` (already set in Compose).

## Debugging a job that did nothing

1. `GET /api/jobs?status=failed` (or **Data setup → Jobs**) shows failed jobs with their error.
2. `docker compose logs worker --tail 100`. The worker logs job id, kind and outcome (never
   payload contents).
3. Is a job stuck in `queued`? Check that the worker container is running.
   `GET /api/health` reports `worker: stale` if no heartbeat has arrived in 30 s.
4. Retry from the UI or `POST /api/jobs/{id}/retry`.

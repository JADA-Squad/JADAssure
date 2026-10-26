# Running JADAssure

> Sections marked ✅ are verified on a real machine (Windows 11, Docker Desktop 29.4, 2026-10-26).
> Unmarked sections describe things not built yet.

## TL;DR ✅

```bash
cp .env.example .env    # then set JWT_SECRET (≥32 random chars) and POSTGRES_PASSWORD
docker compose up -d --build
```

- UI: http://localhost:5173 → **Create one** to sign up an organization (you become its admin)
- API docs (OpenAPI): http://localhost:8000/api/docs
- Health: http://localhost:8000/api/health → `{"status":"ok","database":"ok","worker":"ok"}`

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Database migrations run automatically when the `api` container starts (`alembic upgrade head`).

Demo data (DATA-001, milestone M1, not built yet): `docker compose exec api python -m app.seed_demo`.

## What runs where ✅

`web` (Vite dev server, port 5173) serves the React app and proxies every `/api/*` request to
`api` (FastAPI on port 8000, auto-reload on source edits). `api` validates requests, reads and
writes `db` (Postgres 16; host port **5433**, see gotchas) and will enqueue jobs as rows in the
`job` table. `worker` (same image, `python -m app.worker`) writes a heartbeat every 2 s and will
claim jobs from M1 onward. Uploaded files will live in the `documents` volume mounted into both
`api` and `worker`.

## Configuration that MUST be set ✅

| Variable | Why |
|---|---|
| `JWT_SECRET` | Token signing. The API **refuses to start** if it's unset, still `change-me`, or shorter than 32 characters. |
| `POSTGRES_PASSWORD` | Database password used by Compose. |

Optional: `POSTGRES_HOST_PORT` (default 5433), `JWT_EXPIRES_MINUTES` (default 480),
`ALLOW_SIGNUP` (default true), `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL`. Even with an API key set,
each org stays on the offline stub until its admin enables the provider (GR-08, M4).

## The happy path

Today (M0) ✅:
1. Open http://localhost:5173 → **Create one** → fill in the organization and your admin account.
2. You land on **Overview** with the navigation your role allows. Admins see Overview, Data
   setup, Rules & agreements, Pricing opportunities and Access & settings.
3. Create more users with `POST /api/users` (Swagger UI at `/api/docs`, **Authorize** with your
   token). Signing in as each role shows only its areas. The settings screen arrives in M4.

Target (end of M5):
1. Log in as the DEMO admin of *Cirrus Cloud (demo)*.
2. **Data setup** → the demo source → import baseline files → review the profile → commit.
3. **Run checks now**. The **Findings** queue fills.
4. As the DEMO analyst, open a wrong-rate finding → propose with a root cause.
5. As the DEMO approver, approve. A prepared correction appears in **Recovery**.
6. Import the follow-up invoice (carries the correction reference). The finding moves to *billed*.
7. Import the follow-up payment. The finding moves to *recovered*, and **Overview** shows cash recovered.
8. Re-import the baseline. Totals don't change.
9. **Agreements** in *Northwind Advisory (demo)*: upload the demo contract. The ambiguous term waits for confirmation.

## Running tests ✅

```bash
docker compose exec api pytest                  # backend: ~70 tests, ~40 s
cd frontend && npm run typecheck && npm run build
```

The harness drops and recreates a separate database (`<POSTGRES_DB>_test`) each run and clears
all tables between tests. It never touches your dev data. `pytest -m acceptance` (the eight
scenarios, QA-001) arrives in M5.

## Known environment gotchas ✅

- **Docker Desktop must be running.** `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` means the engine is stopped.
- **Port 5432 is often taken** by a locally installed Postgres. Compose publishes the database on
  host port **5433** by default (`POSTGRES_HOST_PORT`). Inside the Docker network it's still
  `db:5432`.
- **Flaky image downloads** (`short read: expected … unexpected EOF`) are network drops while
  pulling. Re-run, or pull first: `docker compose pull db web` and `docker pull python:3.11-slim`.
- The `alembic` CLI needs `prepend_sys_path = .` (already in `alembic.ini`), or migrations fail with
  `No module named 'app'`.
- Test emails must use a real-looking domain such as `example.com`. The email validator rejects
  reserved TLDs like `.test` and `.local`.
- Windows: Vite file watching inside Docker uses polling (`CHOKIDAR_USEPOLLING=true`, set in Compose).
- After changing `backend/pyproject.toml`, rebuild: `docker compose up -d --build api worker`.

## Debugging a job that did nothing

Arrives with BE-008 (M1). Until then the worker only writes heartbeats:
`docker compose logs worker --tail 50`. `GET /api/health` reports `worker: stale` or `missing`
if no heartbeat has arrived in 30 s.

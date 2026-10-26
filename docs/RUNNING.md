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

Load the DEMO organizations **JM** and **Beyon** (synthetic data, idempotent) ✅:

```bash
docker compose exec api python -m app.seed_demo --remove-obsolete
```

`--remove-obsolete` deletes demo-flagged orgs from earlier seeds (e.g. Northwind/Cirrus/Ridgeline).
It never touches orgs that aren't flagged demo.

With `SHOW_DEMO_ACCOUNTS=true` in `.env` (local demos only), the login page lists every demo
account. Click one to fill the form. Logins follow the role, on each org's domain:

| Role | JM | Beyon |
|---|---|---|
| Administrator | `admin@jm.com` | `admin@beyon.com` |
| Finance analyst | `financeanalyst@jm.com` | `financeanalyst@beyon.com` |
| Finance approver | `financeapprover@jm.com` | `financeapprover@beyon.com` |
| Commercial manager | `commercialmanager@jm.com` | `commercialmanager@beyon.com` |
| Executive viewer | `executive@jm.com` | `executive@beyon.com` |

The shared demo password is `DEMO_PASSWORD` in `backend/app/seed_demo.py`. These are demo logins
only; no email is ever sent to these addresses.

## Live deployment

Render, auto-deployed from `main`. Setup, configuration, security and free-plan limits are in
[deployment.md](deployment.md). Reproduce the production image locally with
`docker build -t jadassure-prod .` and run it with `PORT`, `DATABASE_URL`, `JWT_SECRET` and
`EMBEDDED_WORKER=true`.

## What runs where ✅

`web` (Vite dev server, port 5173) serves the React app and proxies every `/api/*` request to
`api` (FastAPI on port 8000, auto-reload on source edits). `api` validates requests, reads and
writes `db` (Postgres 16; host port **5433**, see gotchas) and will enqueue jobs as rows in the
`job` table. `worker` (same image, `python -m app.worker`) writes a heartbeat every 2 s and runs
queued jobs (import commits, connector syncs). `demo-data/` is mounted read-only at `/demo-data`
for the demonstration connector. Uploaded files will live in the `documents` volume mounted into both
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

Today (M3) ✅: workflow through to cash (JM demo org)
1. As `financeanalyst@jm.com`, open the 600.00 **Incorrect contracted rate** finding → **Take ownership**
   → **Propose for approval** (root cause "Price not updated in billing system" + a description).
   The panel says a different approver must approve.
2. Open the 960.00 analyst-hours finding → **Take ownership** → **Reject** with a reason
   (scenario 5). It's final and never counted.
3. As `financeapprover@jm.com`, open the proposed finding → **Approve**. Correction `JA-JM-0001`
   is prepared (export CSV/JSON).
4. **Recovery tracker** → **Simulate billing** (DEMO): billed 600.00, cash 0.00 →
   **Simulate payment** (DEMO): cash recovered 600.00; the finding becomes Recovered (scenario 6).
5. As `executive@jm.com`, **Overview**: cash recovered 600.00; potential 2,970.00; confirmed,
   corrected billing 600.00; rejected 1; trend and root causes.

M2 (still valid) ✅: findings
1. Sign in as `financeanalyst@jm.com` (demo panel) → **Findings** → **Run checks now**.
   After a few seconds: 6 findings, potential 4,530.00 USD. Unbilled hours 2,160.00 and 960.00,
   incorrect rate 600.00 (March), and three missed increases of 270.00 (Jul–Sep).
2. Click a finding: reason, recommended action, side-by-side evidence (agreed / delivered / billed),
   the calculation with its inputs, rule version, timeline. Add a comment.
3. **Run checks now** again: same 4 findings, "0 new". No duplicates.
4. Beyon (`financeanalyst@beyon.com`): 2 expired discounts (375.00, 187.50) and 2 out-of-policy
   credits (750.00, 120.00). The full expected list is in `demo-data/README.md`.
5. Admins run checks from **Data setup**. Analysts run them from **Findings**.

M1 (still valid) ✅:
1. Seed the demo orgs (above), open http://localhost:5173, and click `admin@beyon.com`
   in the demo panel → **Sign in**.
2. **Data setup** → *Demo connector* shows the baseline already loaded. **Sync now** re-syncs it:
   every record type reports 0 inserted, 0 updated.
3. **Data setup** → *Manual uploads* → record type **Billable events** → choose
   `demo-data/ridgeline-supply/manual/shipments-september.csv` → **Upload & check**.
   Six of eight columns map automatically. Map `Shipment Ref` → `event_id` and `Account` →
   `customer_id` → **Save mapping & re-check** → **Commit 3 rows**: 2 inserted, 1 rejected
   (`Qty = n/a`) → **Errors CSV**.
4. Upload the same file again. The mapping is remembered. Commit: 0 inserted, 2 unchanged, 1 rejected.
5. Or create your own org with **Create one** on the login page. You land on **Overview** with the
   navigation your role allows.

Target (end of M5):
1. Log in as the DEMO admin of *JM* (`admin@jm.com`).
2. **Data setup** → the demo source → import baseline files → review the profile → commit.
3. **Run checks now**. The **Findings** queue fills.
4. As the DEMO analyst, open a wrong-rate finding → propose with a root cause.
5. As the DEMO approver, approve. A prepared correction appears in **Recovery**.
6. Import the follow-up invoice (carries the correction reference). The finding moves to *billed*.
7. Import the follow-up payment. The finding moves to *recovered*, and **Overview** shows cash recovered.
8. Re-import the baseline. Totals don't change.
9. **Agreements** in *JM*: upload the demo contract. The ambiguous term waits for confirmation.

## Running tests ✅

```bash
docker compose exec api pytest                  # backend: ~275 tests, ~5 min
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
- **The worker does not auto-reload** (the API does). After editing backend code that jobs run,
  `docker compose restart worker`. Otherwise jobs run the old code.
- After changing `.env`, recreate the containers (`docker compose up -d`); `restart` doesn't re-read it.

## Debugging a job that did nothing

✅ (BE-008)

1. **Data setup → Background jobs** (or `GET /api/jobs?status=failed`) lists failed jobs with a
   user-safe error. Import failures also show on the import-history row.
2. `docker compose logs worker --tail 100`. The worker logs job id, kind and outcome. Unexpected
   errors show the stack trace here; the UI shows only the exception type.
3. Is a job stuck in `queued`? Check that the worker container is running.
   `GET /api/health` reports `worker: stale` or `missing` if no heartbeat has arrived in 30 s.
4. Retry from the UI (**Retry**) or `POST /api/jobs/{id}/retry`. Only failed jobs can be retried.
5. Did the job succeed but do nothing new? Check the import's counts. `unchanged` means identical
   rows were already imported from the same data source (decision 0002 D-1).

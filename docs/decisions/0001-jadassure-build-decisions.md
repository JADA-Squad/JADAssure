# 0001 — JADAssure pilot build decisions

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | — |

**D-1. Fast-track pilot scope.** The pilot targets a working, testable release with a live UI, not
production completeness. Deferred: live ERP/billing connectors, any outbound write, the
natural-language question interface, SSO/MFA, FX conversion, database row-level security,
S3/Azure storage, OCR, production deployment. Each deferral has a pilot substitute in requirements
§3.2. Rationale: the owner asked for speed, and none of these is needed for the eight acceptance
scenarios.
Owner task: all. Revisit at the end of M5.

**D-2. AI provider is swappable and off by default.** An `AIProvider` interface has two
implementations: `stub` (deterministic, offline, the default for every org) and `anthropic`
(Claude, model id from `ANTHROPIC_MODEL`, default `claude-sonnet-5-5`). An org uses `anthropic`
only if an admin enables it (audited) and `ANTHROPIC_API_KEY` is set. AI produces proposals
only, and the engine domains can't import `ai` (enforced by test). Rationale: GR-02, GR-07, GR-08.
The demo must work with no external calls.
Owner task: BE-028, BE-029, BE-031, INFRA-002.

**D-3. Background jobs on Postgres, not Redis/Celery.** A `job` table claimed with
`FOR UPDATE SKIP LOCKED` by one worker process, which also runs the scheduler. Rationale: one
fewer service to run. Failed jobs are visible rows with a retry action (FR-11). Volume is far
below what this pattern handles.
Owner task: BE-008, BE-010.

**D-4. Document store behind an interface, local filesystem for the pilot.** `DocumentStore` with
`put/get/delete`; the pilot implementation writes to a Docker volume (`DOCUMENT_STORE_PATH`).
Rationale: S3/MinIO adds a service with no pilot benefit, and swapping later is configuration
plus one adapter.
Owner task: BE-027.

**D-5. Auth for this phase.** Local email/password accounts, bcrypt, JWT access tokens (lifetime
`JWT_EXPIRES_MINUTES`, default 480). One user belongs to one org. The token carries
`user_id`, `org_id`, `role`. SSO is deferred.
Owner task: BE-002, BE-003.

**D-6. Term provenance.** Terms imported from structured CSV by an administrator are stored
`confirmed` (`origin='import'`, `confirmed_by` = importing admin). The admin's import is the
confirmation (requirements A2). Terms extracted from documents are always stored `proposed`
(`origin='extraction'`). Ambiguous ones also get `ambiguous=true`. Only a human confirmation
changes that status.
Owner task: BE-011, BE-029, BE-030.

**D-7. Tenant isolation at the application layer.** The org id is read only from the token. All
queries go through scoped repository helpers, and every router has a cross-org test. Postgres RLS
is deferred (D-1) and can be added later as defence in depth.
Owner task: BE-003, QA-001.

**D-8. Finding identity and de-duplication.** Fingerprint = `sha256(org, family, anchor_type,
anchor_id)`. Families: `unbilled` (anchor: matcher bucket key), `price` (anchor: invoice line),
`credit` (anchor: credit). Specificity within `price`: expired_discount > missed_increase >
incorrect_rate. Losing checks are listed in `also_detected_by`. Terminal findings are never
reopened or revalued.
Owner task: BE-019.

**D-9. Money arithmetic.** `NUMERIC(19,4)` for amounts and `NUMERIC(19,6)` for quantities and
unit prices, with `Decimal` in Python. Results are quantized to 4 dp using ROUND_HALF_EVEN, and
serialized in the API as strings. The UI formats them without converting to JS numbers for
arithmetic.
Owner task: BE-001, BE-013.

**D-10. Config, sample data and sensitivity.** All config comes from env vars, and
`.env.example` is committed. Demo data in `demo-data/` is synthetic (classification:
public/synthetic) and loaded into orgs flagged `is_demo`. The owner's source documents (product
brief, overview) stay local and uncommitted until the owner decides otherwise. The market
analysis memo is commercially sensitive and is never committed (git-ignored).
Owner task: DATA-001, INFRA-001.

**D-11. Frontend without a component library.** Hand-written CSS with design tokens. Rationale:
fewer dependencies and faster iteration for eight screens. Revisit if the UI grows.
Owner task: INFRA-003.

## Phase 0.1 — status reconciliation

| Area | Task board claims | Actually in repo (2026-10-26) | Action |
|---|---|---|---|
| Docs (Phase 0) | n/a (not tasks) | requirements, design, summary, AGENTS.md, task board, this record, RUNNING.md, build plan | — |
| Infrastructure | INFRA-001..003 Backlog | nothing scaffolded | none: consistent |
| Backend/Frontend/Data | all Backlog | nothing scaffolded | none: consistent |

Re-run this reconciliation when Phase 1 starts.

## Open items carried forward

| Item | Blocks | Owner |
|---|---|---|
| Docker Desktop must be running on the dev machine | INFRA-001 (and all running/testing) | Shadrack Adeyemi |
| Sandbox credentials for a real billing/ERP system (e.g. Xero, QuickBooks, Stripe test mode) | Live connector (deferred, D-1) | Shadrack Adeyemi |
| Whether to commit the product brief/overview into `docs/source/` | Nothing (requirements doc restates it) | Shadrack Adeyemi |
| `ANTHROPIC_API_KEY` if live AI extraction is wanted in demos | Optional path of BE-028/BE-029 only | Shadrack Adeyemi |
| GitHub `workflow` token scope for the ShadrackAdeyemi account | CI workflow files | Shadrack Adeyemi |
| First design-partner industry | Post-pilot planning | Shadrack Adeyemi |

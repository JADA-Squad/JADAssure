# 0002 — Ingestion, connector and demo-data decisions (M1)

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | — |

**D-1. Import identity and change detection.** A canonical record's identity is
`(org, data source, source record id)`. Re-imports upsert on that key. A SHA-256 of the
*converted* values (decimals normalized, currencies upper-cased, dates ISO) decides between
`updated` and `unchanged`, so formatting-only differences such as `45.00` vs `45` or `usd` vs `USD`
are not changes. The original row is kept verbatim in `source_payload` (GR-16). The same ids from
two different sources are separate records by design. Admins must not load one system through two
sources.
Owner task: BE-007.

**D-2. Reference resolution.** A foreign reference in a CSV (e.g. `customer_id` on an invoice) is
the *source* id of the target record. It resolves within the same org only (GR-06), preferring a
record from the same data source and otherwise any source in the org. That lets a manual upload
refer to records loaded by a connector. An unresolved required or provided reference rejects the
row.
Owner task: BE-006, BE-007.

**D-3. Partial acceptance.** A commit accepts valid rows and rejects invalid ones, rather than
failing the whole file. Rejected rows go to a downloadable, formula-safe error report. A file that
can't be read at all fails the job (visible, retryable). The whole commit is one transaction.
Owner task: BE-007, BE-008.

**D-4. Mapping suggestions are deterministic in M1.** Header matching on field names and a small
synonym list. Suggestions are never auto-committed: the admin sees them labelled "suggested" and
commits explicitly. AI suggestions (FR-39, BE-031) will add to this, not replace it.
Owner task: BE-006, BE-031.

**D-5. DocumentStore built in core during M1.** Import files and error reports need storage
before contract documents do (BE-027), so `app/core/storage.py` implements decision 0001 D-4 now.
Keys are `<org>/<namespace>/<random>` with path-traversal checks.
Owner task: BE-006 (shared with BE-027).

**D-6. Connector syncs are one job, one transaction.** A sync fetches each record type in
dependency order and commits each through the normal ingestion path inside a single transaction.
Later record types can then resolve references to earlier ones, and a failed sync leaves nothing
half-loaded. Each record type still gets its own import-history entry.
Owner task: BE-009.

**D-7. Demo logins on the login page are opt-in.** `GET /api/auth/demo-accounts` is public, but
returns users of `is_demo` orgs only and only when `SHOW_DEMO_ACCOUNTS=true`, including the shared
demo password from `app/seed_demo.py`. The default in code is false. `.env.example` sets it true
with a comment for local demos only. Never enable it on a shared or hosted environment.
Owner task: DATA-001.

**D-8. Demo data is generated, not hand-written.** `demo-data/generate.py` is the source of truth
for the CSVs, and `demo-data/README.md` lists every planted discrepancy with its expected value.
M2 tests assert against that table.
Owner task: DATA-001.

## Open items carried forward

| Item | Blocks | Owner |
|---|---|---|
| Follow-up invoice/payment files for scenario 6 must carry the correction reference generated at approval | DATA-001 completion, QA-001 | Agent, in M3 (BE-022) |
| DATA-001 acceptance needs rule configuration per org (BE-012) and the engine (M2) | DATA-001 → Built | Agent, in M2 |

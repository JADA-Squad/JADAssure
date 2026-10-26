# 0005 — Demo organizations JM and Beyon

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | The three demo org names in decision 0002 and demo-data/README.md |

**D-1. Two demo orgs, three business types.** At the owner's request the demo orgs are **JM** and
**Beyon**. JM carries the professional-services (`northwind-advisory`) and subscription-software
(`cirrus-cloud`) datasets, each through its own labelled demo connector source. Beyon carries
distribution (`ridgeline-supply`). All eight acceptance scenarios keep their data, and FR-42's
"three business types" still holds. DATA-001's acceptance wording was updated to match. JM's
`business_type` is `professional_services`, which sets its default grace days; the subscription
data produces no unbilled findings, so the outcome is unchanged.
Owner task: DATA-001.

**D-2. Role-based demo logins.** Emails are `admin@`, `financeanalyst@`, `financeapprover@`,
`commercialmanager@` and `executive@` + `jm.com` or `beyon.com`. The owner's "financial advisor" is
the existing finance analyst role; no new role was added. These domains may exist on the internet,
but JADAssure never sends email, so the addresses are only login identifiers. The orgs stay
flagged `is_demo` and labelled DEMO (GR-14).
Owner task: DATA-001.

**D-3. Removing obsolete demo orgs.** `python -m app.seed_demo --remove-obsolete` deletes demo-flagged
orgs that are no longer in `DEMO_ORGS`, including their (synthetic) audit history, before seeding.
Orgs not flagged `is_demo` are never touched (tested). `start.sh` uses it on Render, so the live
pilot drops the old demo orgs on the next deploy.
Owner task: DATA-001.

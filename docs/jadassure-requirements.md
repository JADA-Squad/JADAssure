# JADAssure — Requirements Specification (Pilot / Release 1)

| | |
|---|---|
| Version | 0.1 (draft for pilot) |
| Date | 2026-10-26 |
| Owner | Shadrack Adeyemi (JADA Squad) |
| Source of truth for scope | The JADAssure end-to-end product brief (`JADAssure-Project-e2e-description.docx`, kept locally and not committed; this document restates it in full) plus decisions recorded in `docs/decisions/` |

## 1. Purpose and how to read this document

This document defines what the first JADAssure release (the **pilot**) must do. Every task on the
task board (`docs/jadassure-task-board.csv`), every decision record and every non-trivial piece of
code traces back to an ID defined here:

- `FR-xx`: functional requirement. One testable claim, plus how it is verified.
- `GR-xx`: guardrail. A rule the system must never break. Guardrails are enforced in code and
  covered by tests; documentation alone isn't enough.
- `NFR-xx`: non-functional requirement.

Verification methods: **Auto** (automated unit or integration test), **E2E** (scripted end-to-end
acceptance test over the demo data), **Review** (a human reviewer checks it in the running app).

The pilot goal is a **working, testable first release with a live frontend, delivered fast**. It
doesn't yet meet every production requirement. Items that matter for production but not for the
pilot are listed as deferred in §3.2 so the cut is explicit, not silent.

## 2. Background

Businesses with complex pricing keep their data in several systems: contracts in one, delivery or
usage in another, billing and cash in a third. Those records drift apart. Work goes unbilled,
expired discounts keep being applied, contractual price increases are missed and credits are
issued without basis. Finance teams rarely have an evidence-backed way to find this leakage,
correct it and prove the money came back.

The buyer is the CFO or finance leader. JADAssure must let them answer four questions:
**Where are we losing revenue? What evidence supports the finding? Who owns the fix? How much
money did we actually recover?**

## 3. Scope

### 3.1 In scope for the pilot

- Multi-organization platform with five roles: finance analyst, finance approver, commercial
  manager, administrator, executive viewer.
- Data intake through secure CSV import (templates, field mapping, profiling, validation, history,
  idempotent reprocessing), plus a connector interface with one clearly labelled demonstration
  connector.
- Contract document upload with **proposed** term extraction (source passage shown) and human
  confirmation.
- A deterministic assurance engine running five checks: delivered-not-billed, incorrect
  contracted rate, expired/unauthorized discount, missed contractual increase, credit outside
  policy.
- Findings queue, finding detail, analyst decision, approval, prepared correction, recovery
  tracking through to cash, root cause and recurrence.
- Separate reporting of potential leakage, confirmed leakage, corrected billing, cash recovered,
  prevented recurrence and closed without recovery.
- Pricing opportunities (separate from billing errors) when cost data exists.
- A React UI covering all eight screen areas in the e2e brief.
- Anonymized demo data for three business types run through one engine by configuration.
- Local runnable environment (Docker Compose), automated tests, API docs, run instructions,
  walkthrough.

### 3.2 Out of scope / deferred (explicit)

| Deferred item | Why | Pilot substitute |
|---|---|---|
| Live ERP/billing integrations (NetSuite, Xero, QuickBooks, Stripe, Salesforce …) | No credentials or test system provided | Connector interface + labelled demonstration connector (FR-09) |
| Any outbound write to external systems (sending invoices, credit notes, emails) | Guardrail GR-01; not needed to prove value | Corrections are *prepared* and exportable only |
| Natural-language question interface over findings | Optional in the brief; not needed for the acceptance demo | Deferred to release 2 (decision 0001) |
| Single sign-on / SAML / OIDC, MFA | Pilot uses local accounts | Local accounts + signed tokens |
| Foreign-exchange conversion across currencies | Needs rate source and policy | Comparisons happen within one currency; mismatches surface as data-quality issues |
| Production cloud deployment, managed secrets manager, KMS | Pilot is local | Env-var config; deployment guide documents TLS/at-rest encryption requirements |
| Database row-level security | App-level tenant scoping is faster to build and fully tested | Single tenant-scoping query layer + cross-org tests (decision 0001) |
| S3/Azure object storage | Faster locally | Document store behind an interface; local filesystem volume |
| OCR of scanned contracts | Complexity | Text-based PDF, DOCX and TXT only |

### 3.3 Current process / baseline

Today, a customer's finance team typically reconciles contracts, delivery records and invoices by
spreadsheet sampling, if at all. Nothing systematic connects a leakage finding to its evidence, an
approval and a verified cash outcome. JADAssure replaces the sampling with full-population checks
and adds a governed workflow from finding to recovery.

## 4. Solution overview (plain language)

An administrator sets up an organization and loads four kinds of records: what was **agreed**
(contracts and commercial terms), **delivered** (billable events), **billed** (invoices, lines,
credits) and **collected** (payments and allocations). JADAssure maps them into one common revenue
model and keeps a link to each original record. Contract documents can be uploaded. The system
proposes the commercial terms it finds, shows the passage each came from, and waits for a human
to confirm them. A deterministic engine then applies versioned rules to confirmed terms and
compares expected against actual billing. Each discrepancy becomes one de-duplicated finding with
a value, confidence, reason and full evidence. Analysts investigate and propose; approvers
approve. On approval JADAssure prepares, but never sends, a correction. It then watches later
imports for the corrected invoice and the matching payment. Money counts as **recovered** only
when that payment exists.

## 5. Input specification

| Record type | Key fields (canonical) | Source |
|---|---|---|
| Customer | external id, name, currency | CSV / connector |
| Agreement | external id, customer, title, start/end, billing frequency, currency | CSV / connector |
| Agreement version (amendment) | agreement, version no., effective from/to, reason | CSV / connector / UI |
| Commercial term | agreement version, item code, term type (rate, discount, escalation, minimum, credit policy), value, unit, effective from/to, approval reference, source passage | CSV (confirmed on import) or contract extraction (proposed) |
| Billable event | external id, customer, agreement (optional), item code, quantity, unit, service date or period, billing date, currency | CSV / connector |
| Invoice | external id, customer, invoice date, currency, status, correction reference (optional) | CSV / connector |
| Invoice line | external id, invoice, item code, quantity, unit price, discount %, net amount, tax amount, service period, agreement ref (optional) | CSV / connector |
| Credit | external id, customer, invoice ref, amount, currency, reason code, approval reference, date | CSV / connector |
| Payment | external id, customer, amount, currency, date | CSV / connector |
| Payment allocation | payment, invoice, amount | CSV / connector |
| Cost record (optional) | item code, unit cost, currency, effective from/to | CSV |
| Contract document | PDF (text), DOCX or TXT | Upload |

All imports are untrusted input (GR-07) and are validated at the boundary.

## 6. Output specification

| Output | Behaviour |
|---|---|
| Import profile | Before commit: row count, mapped vs unmapped columns, missing required fields per column, unmatched references (e.g. invoice line pointing to unknown invoice), sample rows |
| Import result | Rows inserted / updated / unchanged / rejected; downloadable row-level error report; entry in import history |
| Proposed terms | Each term: type, value, effective dates, **verbatim source passage**, confidence, ambiguity flag, status `proposed` |
| Finding | Type, customer, agreement, estimated value + currency, confidence (high/medium/low), reason in plain language, calculation (inputs, formula, result), links to every source record (term/clause, delivery records, invoice lines, credit), rule version, recommended next action, status, owner, timeline |
| Prepared correction | Correction type (supplementary invoice / credit reversal), lines, amounts, reference ID to quote on the corrected invoice; exportable as CSV/JSON; status prepared → billed → paid |
| Outcome report | Six separate figures (FR-32) with trends by month and top recurring root causes |
| Pricing opportunity | Customer/item where contracted price is permitted but margin is below the org's target, with the cost basis shown; never mixed with leakage figures |

## 7. Binding content and behaviour rules

1. Money uses exact decimals end to end (storage, calculation, API, UI formatting). Floats are
   never used for money.
2. Discrepancy values exclude tax: checks compare net amounts. Tax is shown for information.
3. A comparison only happens between amounts in the same currency.
4. A term applies to a delivery or invoice line if the service date falls within the term's
   effective range on the agreement version effective at that date.
5. One underlying discrepancy yields one finding, however many checks detect it. The most
   specific cause wins (expired discount > missed increase > incorrect rate for the same invoice
   line); other detecting checks are recorded on the finding as "also detected by".
6. Statuses map to reporting buckets exactly as defined in FR-32, and no other way.
7. Demo data and the demonstration connector are always labelled as such in UI and API.

## 8. Functional requirements

### Organization and access
| ID | Requirement | Verify |
|---|---|---|
| FR-01 | A new organization can be created together with its first administrator account. | Auto |
| FR-02 | An administrator can create users, assign exactly one of the five roles, correct a user's name and email, and deactivate users. | Auto |
| FR-03 | Every API operation is permitted or denied according to the role permission matrix in the solution design. | Auto |

### Data intake
| ID | Requirement | Verify |
|---|---|---|
| FR-04 | A downloadable CSV template exists for every core record type in §5. | Auto |
| FR-05 | An administrator can register a data source and save a column-to-canonical-field mapping that is reused for later imports from that source. | Auto |
| FR-06 | Before committing an import, the system shows a profile listing missing required fields, unmapped columns and unmatched references. | Auto |
| FR-07 | Committing an import validates every row, stores rejected rows with reasons in a downloadable error report, and records the import in import history. | Auto |
| FR-08 | Re-importing records with the same source identifiers updates or leaves them unchanged and never creates duplicates. | Auto |
| FR-09 | A documented connector interface exists, and a labelled demonstration connector loads data through it without changing assurance logic. | Auto |
| FR-10 | A user with permission can trigger "run checks now", and each organization can configure a scheduled refresh interval. | Auto |
| FR-11 | Failed imports and failed check runs are visible with their error and can be retried. | Auto |

### Agreements and terms
| ID | Requirement | Verify |
|---|---|---|
| FR-12 | Agreements support multiple versions (amendments) and effective-dated commercial terms, and the applicable term for any date is resolved deterministically. | Auto |
| FR-13 | An uploaded contract document is stored with its original, and the system proposes commercial terms each carrying a verbatim source passage. | Auto |
| FR-14 | Proposed terms (including those flagged ambiguous) must be confirmed, edited or rejected by an authorized user; only confirmed terms are used by the engine. | Auto |
| FR-15 | Each organization has versioned rule configurations (tolerances, grace days, materiality thresholds, credit policy, matching configuration for its business type), and each finding records the rule version used. | Auto |

### Assurance engine
| ID | Requirement | Verify |
|---|---|---|
| FR-16 | The matcher compares delivered quantities with billed quantities per agreement, item and billing period, correctly handling split invoices, aggregated invoice lines, partial delivery and different billing frequencies. | Auto |
| FR-17 | Check **delivered-not-billed**: a finding is raised when delivered quantity exceeds billed quantity after the billing date plus grace. | Auto |
| FR-18 | Check **incorrect contracted rate**: a finding is raised when an invoice line's net unit price differs from the applicable contracted rate beyond tolerance. | Auto |
| FR-19 | Check **expired or unauthorized discount**: a finding is raised when a discount is applied after its expiry or exceeds the approved discount. | Auto |
| FR-20 | Check **missed contractual increase**: a finding is raised when an escalation or renewal price was in effect but the pre-increase price was billed. | Auto |
| FR-21 | Check **credit outside policy**: a finding is raised when a credit lacks a reason code, lacks a required approval reference above the policy threshold, or exceeds the policy limit. | Auto |
| FR-22 | Checks handle multiple currencies (no cross-currency comparison) and taxes (net-of-tax comparison). | Auto |
| FR-23 | The same underlying discrepancy produces exactly one finding across checks and across repeated runs. | Auto |
| FR-24 | Each finding stores estimated value, currency, confidence, reason, calculation, source record references, rule version and recommended next action. | Auto |

### Case management and recovery
| ID | Requirement | Verify |
|---|---|---|
| FR-25 | The findings queue is ordered by priority (value × confidence) and filterable by value, customer, type, confidence, age, owner and status. | Auto |
| FR-26 | Finding detail shows evidence side by side, the calculation, a timeline of events and comments. | Review |
| FR-27 | An analyst can assign, comment on, reject (with reason) or propose a finding for approval. | Auto |
| FR-28 | An approver can approve or send back a proposed finding. | Auto |
| FR-29 | Approval creates a prepared correction with a unique correction reference; the correction is exportable and never sent externally. | Auto |
| FR-30 | The system marks a correction billed when an imported invoice carries its reference, and records cash recovered from payment allocations against that invoice. | Auto |
| FR-31 | A root cause is recorded when a finding is closed, and later check runs flag recurrences of the same cause for the same customer and term. | Auto |
| FR-32 | The system reports six separate figures: potential leakage, confirmed leakage, corrected billing, cash recovered, prevented recurrence and closed without recovery. | Auto |
| FR-33 | Pricing opportunities appear in a separate view, and only when cost data exists for the item. | Auto |

### Screens
| ID | Requirement | Verify |
|---|---|---|
| FR-34 | **Overview** screen: the six outcome figures, open findings, monthly trend, top recurring root causes. | Review |
| FR-35 | **Data setup** screen: sources, imports with status, mappings, profiling and data-quality gaps, retry, run checks now. | Review |
| FR-36 | **Rules and agreements** screen: agreements, versions, terms with effective dates and status, term confirmation with source passage, rule configuration versions. | Review |
| FR-37 | **Recovery tracker** screen: correction status, invoice reference, payment status, verified outcome. | Review |
| FR-38 | **Access and settings** screen: users and roles, approval settings, AI/model settings, retention, audit history with chain verification. | Review |

### AI assistance (suggestion-only)
| ID | Requirement | Verify |
|---|---|---|
| FR-39 | The system suggests column-to-field mappings for an import; the administrator must accept them. | Auto |
| FR-40 | A finding can show an AI-generated plain-language summary, clearly labelled as AI-generated and not used in any calculation. | Auto |

### Data lifecycle and demo
| ID | Requirement | Verify |
|---|---|---|
| FR-41 | An administrator can set a retention period and delete all of the organization's data. | Auto |
| FR-42 | Anonymized, labelled demo data for three business types (professional services, subscription software, distribution) is processed by the same engine through configuration only, and covers the eight acceptance scenarios in §11. | E2E |

## 9. Guardrails (non-negotiable)

| ID | Guardrail |
|---|---|
| GR-01 | JADAssure never issues an invoice, alters a contract or contacts a customer. In the pilot there is no outbound write path at all; corrections are prepared and exported only. |
| GR-02 | An AI/LLM output never establishes a financial entitlement, sets a discrepancy value or authorizes a correction. Expected charges and values come only from deterministic code applying versioned rules to confirmed terms. |
| GR-03 | Terms with status other than `confirmed` (proposed, ambiguous, rejected) are never read by the assurance engine. |
| GR-04 | Cash recovered is counted only from recorded payment allocations against a correction's invoice. An unpaid invoice, a prepared correction or a pricing opportunity is never counted as cash recovered. |
| GR-05 | A rejected finding is never counted in confirmed leakage, corrected billing or cash recovered. |
| GR-06 | Strict organization isolation: no user can read, act on or infer another organization's data. |
| GR-07 | Uploaded and imported content is untrusted data, never instructions. Embedded instructions in documents have no effect on system behaviour. |
| GR-08 | Customer data is never sent to an external model unless an administrator explicitly enables a provider for the organization; the default is off. |
| GR-09 | Money uses exact decimal arithmetic; binary floating point is never used for money. |
| GR-10 | Imports, rule changes, AI extractions, user decisions, approvals and corrections are written to a tamper-evident (hash-chained) audit log. |
| GR-11 | Repeating an import never duplicates source records, findings or recovery totals. |
| GR-12 | The user who proposes a finding cannot approve it (separation of duties). |
| GR-13 | Approved, rejected and closed findings, and their evidence snapshots, cannot be edited by any code path except permitted status transitions. |
| GR-14 | Demo data and the demonstration connector are never presented as live customer integrations. |
| GR-15 | Credentials and secrets are never hard-coded or committed; only `.env.example` templates are committed. Sensitive content is never logged. |
| GR-16 | Every finding is traceable to the term/clause, delivery records, invoice lines (or credit), rule version and calculation that produced it. |

## 10. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | The full stack starts locally with one `docker compose up` command. |
| NFR-02 | Backend in Python 3.11+ (FastAPI); frontend in React + TypeScript. |
| NFR-03 | PostgreSQL 16 for structured records, with schema changes as versioned migrations. |
| NFR-04 | A full check run over the complete demo dataset completes in under 30 seconds on a developer laptop. |
| NFR-05 | Every monetary amount is stored with its ISO 4217 currency code. |
| NFR-06 | Deployment guidance requires TLS in transit and encryption at rest; locally, secrets come only from environment configuration. |
| NFR-07 | The API exposes a health check reporting database and worker status; logs are structured and exclude sensitive content. |
| NFR-08 | The API is documented as OpenAPI, served by the application. |
| NFR-09 | Automated tests cover calculations, matching, effective dates, duplicate prevention, access control and the approval workflow. |
| NFR-10 | All configuration is read from environment variables; nothing environment-specific is hard-coded. |
| NFR-11 | The UI works in current Chrome and Edge at desktop widths (≥1280px). |
| NFR-12 | Passwords are stored with a slow adaptive hash; access tokens expire. |

## 11. Evaluation and acceptance

The pilot is accepted when a reviewer can run the stack locally and see each of the following
through the UI, and the automated E2E test (QA-001) proves the same:

1. A delivered item omitted from billing raises a delivered-not-billed finding of the correct value.
2. An invoice using the wrong contracted rate raises an incorrect-rate finding.
3. A discount applied after its expiry raises an expired-discount finding.
4. An ambiguous contract term is held as `proposed` and has no effect until confirmed.
5. A finding rejected by a reviewer does not count toward confirmed or recovered figures.
6. An approved correction moves from confirmed leakage to corrected billing, then to cash
   recovered **only** after a matching payment is imported.
7. Re-importing the same files changes no source-record, finding or recovery totals.
8. A user of organization A cannot view or approve organization B's findings.

Quality measures: every finding value is reproducible from its stored calculation; zero duplicate
findings across re-runs; zero cross-organization access in tests; engine values never sourced from
AI output (enforced structurally and tested).

## 12. Assumptions, dependencies, risks

**Assumptions**
- A1: CSV is a sufficient intake channel for the pilot; customers can export these records.
- A2: Terms loaded via structured CSV by an administrator count as confirmed (an administrator
  entering them is the confirmation); document-extracted terms always start as proposed.
- A3: Each user belongs to exactly one organization in the pilot.
- A4: Contract documents are text-based (not scanned images).
- A5: Prevented recurrence is an estimate: original per-period discrepancy × subsequent clean
  billing periods checked. It is labelled as an estimate.

**Dependencies**
- Docker Desktop running locally (NFR-01).
- An Anthropic API key, only if an administrator chooses to enable the external AI provider (GR-08).

**Risks**
| Risk | Response |
|---|---|
| Incorrect findings erode trust | Deterministic tested calculations, full evidence, approval gate |
| Pilot speed leads to over-claimed ROI | Six separate figures; cash only from payments (GR-04) |
| Cross-tenant leak | Single scoping layer + dedicated tests (GR-06) |
| Prompt injection via contracts | AI output is proposals only, passages verified verbatim, never instructions (GR-02, GR-07) |
| Business-type assumptions hard-coded | Configuration-driven matching; three business types in demo (FR-42) |

## 13. Approval

| Role | Name | Decision | Date |
|---|---|---|---|
| Product owner | Shadrack Adeyemi | Pending review | |
| Delivery (agent-built) | Claude Code | Drafted | 2026-10-26 |

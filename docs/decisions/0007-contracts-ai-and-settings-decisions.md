# 0007 — Contract documents, AI boundary and settings decisions (M4)

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | 0001 D-2's default model (`claude-sonnet-5-5` → `claude-opus-5-5`) |

**D-1. Extracted terms attach to the existing version.** A document is uploaded against an
agreement. Each proposed term attaches to the agreement version in effect on its start date. The
pilot never creates a new version from a document: an empty new version would hide the old
version's confirmed terms from the engine without anyone confirming anything. Amendments that
need a new version are entered as versions by import (or a later task).
Owner task: BE-029.

**D-2. Defence in depth against injected or fabricated terms (GR-02, GR-03, GR-07).**
(1) The provider output must match a strict schema (unknown fields rejected). (2) Each passage
must appear verbatim in the document (whitespace-insensitive), or the term is discarded and
counted. (3) Unknown item codes become `item_code = null` plus ambiguous, never invented. (4)
Survivors are stored `proposed`, which the engine can't read. (5) A person with `manage_contracts`
confirms (optionally editing) or rejects each term, audited. Rates and escalations need an item
before confirmation. A test drives a deliberately malicious provider through this path.
Owner task: BE-028, BE-029, BE-030.

**D-3. Providers: offline stub by default; Claude only by audited opt-in with a key (GR-08).**
The stub is a deterministic pattern reader that flags conditional or open wording ("subject to
agreement", volume thresholds) as ambiguous. The Claude adapter uses the official `anthropic` SDK
(2.x) with model `claude-opus-5-5` (from `ANTHROPIC_MODEL`), JSON-schema structured output,
`effort: medium`, server-side refusal fallbacks (`fallbacks: "default"`), and explicit handling
of `refusal` and `max_tokens`. The document goes in `<document>` tags, and the system prompt
declares it untrusted. Enabling it requires `ANTHROPIC_API_KEY` on the server and writes
`ai.external_provider_enabled` to the audit log. Without a key the org silently stays on the stub.
Owner task: BE-028, BE-032.

**D-4. Retention covers raw uploads, not records.** `retention_days` (30–3650, optional) purges
uploaded import files, error reports, contract originals and their extracted text after the
period (hourly worker task, audited). Canonical records, terms (with their source passages) and
finding evidence stay until the organization's data is deleted. Deleting them earlier would break
evidence trails and recovery history (GR-16).
Owner task: BE-032.

**D-5. Organization data deletion.** Typing the org code confirms it. One transaction deletes the
org's audit events and the org row, which cascades to every tenant table including users and
jobs. Then it re-creates a bare org row (same id, name and code, `data_deleted_at`) and writes a
single tombstone event that starts a fresh, verifiable chain. Stored files are removed through
`DocumentStore.delete_org`. All of the org's users are signed out because they no longer exist.
Owner task: BE-032.

**D-6. Scenario 4 demo data.** Orchard (JM) has synthetic Aug–Sep advisory hours billed at the old
180/hour. Before the amendment's 195/hour term is confirmed they produce no finding (no confirmed
rate). After confirmation, the next run raises two incorrect-rate findings (300.00, 240.00). That
demonstrates "only then does it affect a check run".
Owner task: DATA-001, BE-030.

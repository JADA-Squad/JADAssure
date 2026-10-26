# 0008 — Recurrence, pricing opportunities and AI assistance decisions (M5)

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |

**D-1. Recurrence key and timing.** A new finding is a recurrence when an earlier finding with the
same customer, agreement, check type and item code was confirmed (approved, billed, recovered or
closed without recovery) and its period ended before the new finding's period starts. The link
is set once, when the check run first creates the finding (`recurrence_of_id`), and points to the
most recent such finding. The check type is part of the key, so a missed increase after a fixed
wrong rate isn't called a recurrence of it. Findings raised in the same run as their predecessor
are not recurrences: nothing had been confirmed yet.
Owner task: BE-024.

**D-2. Prevented-recurrence estimate.** For each confirmed finding with a root cause:
value × the number of later months, up to today, in which the same customer, agreement and item
were invoiced and no finding of the same check exists. Months come from invoice lines (service
period, else invoice date). It is an estimate. It's labelled so on the Overview and is never
added to recovered or confirmed figures.
Owner task: BE-024.

**D-3. Pricing opportunities come from contract price vs recorded cost only.** The contracted
net price comes from confirmed terms (the same TermBook the engine uses, GR-03). It's compared
with the cost record in effect today in the same currency. Items below the org's target margin
(`pricing_target_margin_pct`, default 20, range 0–90, set in Access & settings) are listed. The
suggested price is cost ÷ (1 − target). The indicative annual uplift is (suggested − contract
price) × quantity billed in the last 12 months. Without cost data the screen says so and
suggests nothing. Opportunities are reported apart from leakage and never enter recovery figures.
Owner task: BE-026, FE-008.

**D-4. AI assistance lives in the `ai` domain, and nothing it returns is applied automatically.**
The mapping-suggestion and summary endpoints are in `ai/router.py`, so `ingestion`, `cases` and
the engine domains still never import `ai` (GR-02). Mapping suggestions run deterministic value
evidence first: values that all match existing reference IDs suggest that reference field (0.95),
and unique ID-like values suggest the record's ID field (0.7). Only the remaining columns go to
the provider. Every suggestion is filtered to real unmapped columns and free fields, and it's
applied only when an admin clicks Apply and saves. Finding summaries are stored in `ai_summary`
(max 1000 characters), labelled AI-generated in the UI, audited (`ai.summary_generated`), and read
by no calculation. A summary may be regenerated on a final finding, because it isn't evidence.
Owner task: BE-031.

**D-5. Acceptance test runs through the API.** QA-001 seeds the demo orgs and drives all eight
scenarios as the demo users would, in one ordered test (`pytest -m acceptance`). Each check run
asserts NFR-04 (under 30 seconds, measured both from the API call and in the run's stats).
Owner task: QA-001.

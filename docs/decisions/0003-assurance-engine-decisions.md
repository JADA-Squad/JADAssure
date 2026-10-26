# 0003 — Assurance engine decisions (M2)

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | Refines 0001 D-8 (finding identity) |

**D-1. One price finding per invoice line, valued at the total shortfall.** Incorrect rate,
expired/unauthorized discount and missed increase are evaluated together for each invoice line.
The finding's value is `expected net amount − billed net amount`, where expected = contracted list
price (rate + escalation in effect) × (1 − discount actually applied, capped at the approved
maximum) × quantity. The most specific cause names the finding (expired discount > missed
increase > incorrect rate). Other causes go in `also_detected_by`, and the calculation shows each
cause's component. This counts a line with two problems once, at the correct total (FR-23). The
0001 D-8 wording "the most specific check wins" would have under-stated value. Rationale:
correctness of the money figure outranks a one-check-one-value model.
Owner task: BE-015, BE-016, BE-017, BE-019.

**D-2. Findings freeze once a person acts.** A later run refreshes a finding's value, evidence and
calculation only while it's `open` or `in_review`. From `proposed` onward it's frozen (run stats
count it as `frozen`), so an approver never approves a moving number. Terminal states are
additionally protected by a database trigger in M3 (BE-021, GR-13). A discrepancy that disappears
from the data doesn't auto-close its finding; a person decides.
Owner task: BE-019, BE-021.

**D-3. Only shortfalls are leakage.** Billing more than the contract allows (over-billing) is
never a finding. It may be a customer-relations issue, but it isn't revenue the business is owed.
Owner task: BE-014..BE-018.

**D-4. Agreement inference is conservative.** Records without an explicit agreement reference are
matched only when exactly one agreement of the same customer has a confirmed rate for the item on
that date. Such findings are `medium` confidence. An explicit reference to another customer's
agreement is never trusted. Unmatched records are skipped and counted in the run's `skipped` stats
rather than guessed.
Owner task: BE-013.

**D-5. Unbilled delivery is valued at the contracted net price.** If a discount term is in effect,
the authorized discount is assumed to apply (conservative). An unbilled finding is raised only
after `billing date + grace_days` (rule parameter; business-type defaults 10/5/3 days for
services/SaaS/distribution).
Owner task: BE-014, BE-012.

**D-6. Credit policy comes from `credit_policy` terms.** The term's value is the approval threshold
and `params.max_value` is the maximum credit. Rule parameters supply fallbacks when an agreement
has no policy term. Value at risk: the full credit when the reason or required approval is
missing, or the excess over the maximum when the credit is approved but too large.
Owner task: BE-018.

**D-7. In-memory TermBook for runs.** Check runs load confirmed terms once through
`confirmed_terms()` into a `TermBook`, which a test keeps equivalent to `resolve_terms()`. This
keeps a run's database reads constant per org (NFR-04: the demo orgs run in well under a second).
Owner task: BE-013.

**D-8. One check run at a time per org.** `POST /api/check-runs` returns 409 while a run is queued
or running. The worker queues scheduled runs when `organization.settings.refresh_interval_minutes`
has elapsed since the last run. The settings UI for this interval arrives with BE-032 (M4).
Owner task: BE-010.

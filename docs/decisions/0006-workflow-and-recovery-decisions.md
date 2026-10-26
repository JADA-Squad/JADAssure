# 0006 — Workflow, recovery and outcome-reporting decisions (M3)

| | |
|---|---|
| Date | 2026-10-26 |
| Status | Accepted |
| Applies to | JADAssure |
| Supersedes | — |

**D-1. Review before proposal.** Per design §2.5 a finding is proposed only from `in_review`.
Taking ownership, being assigned, or receiving a first comment moves it from `open` to
`in_review`. The UI offers **Take ownership** on open findings. Proposing requires a root-cause
**category** (fixed list: price not updated, discount not ended, delivery not billed, credit
process, contract not loaded, data quality, other) plus a description, so the Overview can group
recurring causes. Reject, send back and write off require a reason.
Owner task: BE-021, FR-27, FR-31.

**D-2. Server decides the available actions.** The finding detail API returns
`available_actions` for the caller (role × status × separation of duties). The UI shows exactly
those, and every endpoint re-checks them. A proposer never gets **approve** (GR-12), even after
being re-roled to approver.
Owner task: BE-021, FE-004.

**D-3. Terminal immutability in the database.** A Postgres trigger rejects any update to the
status, value, currency, evidence or calculation of a `rejected`, `recovered` or
`closed_no_recovery` finding (GR-13). Deletes stay possible for org data deletion (FR-41).
Owner task: BE-021.

**D-4. Corrections.** Approval prepares exactly one correction per finding, with sequential
human-quotable references `JA-<org code>-0001`. Unbilled and price findings become supplementary
invoices; credit findings become credit reversals. Export is CSV/JSON with instructions to quote
the reference. There is no send path (GR-01).
Owner task: BE-022.

**D-5. Recovery matching.** Billed = imported invoice lines (net) on invoices whose
`correction_reference` equals the correction's reference. Cash = payment allocations to exactly
those invoices, capped at the correction amount (tax and overpayment never inflate recovery,
GR-04). Recovery events are unique per source record, so re-imports never double count (GR-11).
Imports of invoices, lines or allocations queue one `recovery_reconcile` job per org. A
written-off finding stays closed even if an invoice later arrives; the correction still records it.
Owner task: BE-023.

**D-6. DEMO billing simulation.** In `is_demo` orgs only, the Recovery tracker's **Simulate billing
/ Simulate payment** write the corrected invoice and its payment as canonical CSVs into a labelled
"Billing simulation (DEMO)" source, through the normal ingestion and recovery path. That makes
scenario 6 demonstrable without an external system. Refused (403) for other orgs (GR-14).
Owner task: BE-023, DATA-001.

**D-7. Outcome figures and trend.** The six figures are computed independently per currency (design
§2.5). "Prevented recurrence" stays zero, labelled as such, until BE-024 (M5). The 12-month trend
shows leakage **identified** by the month it happened (excluding rejected findings) and cash
**recovered** by payment month. It uses the dataviz *emphasis* form: recovered in brand orange,
identified in recessive gray. Orange + black failed the palette validator as a categorical pair
(black reads as gray), and emphasis fits the story. A legend, hover tooltip and table view mean
identity never relies on colour alone.
Owner task: BE-025, FE-006.

**D-8. Timeline ordering.** `investigation_event` and `approval` rows default `created_at` to
`clock_timestamp()` (real insert time), so several events written in one transaction keep their
order in the timeline.
Owner task: BE-021.

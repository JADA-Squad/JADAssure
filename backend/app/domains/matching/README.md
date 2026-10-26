# matching

**Built (M2):** BE-013. Status: Built, awaiting owner checkpoint.

- `periods.py`: billing period for a date by agreement frequency.
- `pricing.py`: `expected_price()` gives the contracted list price (rate + escalation) and the net
  price with the authorized discount capped at its approved maximum. Decimal only.
- `matcher.py`: `OrgData.load()` loads the org's records. `match_agreement()` is explicit, or
  conservatively inferred (decision 0003 D-4). `build_buckets()` sums delivered and billed
  quantities per (customer, agreement, item, period, currency).
- Reads terms only via `contracts.terms.TermBook` (built from `confirmed_terms`). Never imports
  `ai` (enforced by test).

## Scope
Confirmed-term resolution by date, billing periods and the delivered-versus-billed matcher. Must never import `ai`.

## Task IDs
BE-013

Read each task's exact Acceptance Criteria in `docs/jadassure-task-board.csv` before implementing. Don't infer them from this README.

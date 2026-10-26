# JADAssure walkthrough (DOC-001)

The complete user journey on the demo data, one role at a time. It takes about 20 minutes. Setup
is in [RUNNING.md](RUNNING.md). All demo logins and the shared password are in
`backend/app/seed_demo.py`. Every demo org, source and record is labelled **DEMO**.

The same journey runs automatically as the acceptance test (QA-001):

```bash
docker compose exec api pytest -m acceptance
```

Two demo orgs exist, and neither can see the other's data:

| Org | Business types | Data sources |
|---|---|---|
| **JM** | professional services (hours, milestones) + subscription software (seats) | two demo connector sources |
| **Beyon** | distribution (shipped units, USD and CAD) | demo connector + *Manual uploads* |

Logins are `admin@`, `financeanalyst@`, `financeapprover@`, `commercialmanager@` and `executive@`
on `jm.com` or `beyon.com`. The demo panel on the login page fills them in locally (it's hidden on
the public pilot).

## 1. Administrator: data in

Sign in as `admin@beyon.com`.

1. **Data setup** → *Demo connector*. The baseline is already loaded. **Sync now** re-syncs it:
   every record type reports 0 inserted, 0 updated. Re-imports never duplicate (scenario 7).
2. *Manual uploads* → record type **Billable events** → choose
   `demo-data/ridgeline-supply/manual/shipments-september.csv` → **Upload & check**.
   The profile shows rows, new vs existing ids, and which required fields are missing.
3. Two columns aren't mapped. **Suggest mappings** proposes `Account → customer_id` (every value
   matches an existing customer) and `Shipment Ref → event_id` (unique identifiers). It's labelled
   as an AI suggestion, and nothing changes until you click **Apply** and **Save mapping & re-check**.
4. **Commit 3 rows**: 2 inserted, 1 rejected (`Qty = n/a`). **Errors CSV** downloads the rejected row
   with its reason. Upload the same file again: the mapping is remembered and nothing duplicates.
5. **Run checks now** queues a check run. **Background jobs** lists it, with **Retry** for any failure.

## 2. Analyst: findings

Sign in as `financeanalyst@jm.com` → **Findings** → **Run checks now**. After a few seconds there
are six findings worth 4,530.00 USD:

| Finding | Value | Scenario |
|---|---|---|
| Delivered not billed, senior hours, April | 2,160.00 | 1 |
| Delivered not billed, analyst hours, June | 960.00 | 5 (to be rejected) |
| Incorrect contracted rate, Bluefin seats, March | 600.00 | 2 |
| Missed price increase, Bluefin, Jul / Aug / Sep | 270.00 each | |

Beyon's analyst sees its own: an expired discount 375.00 (scenario 3), a second one 187.50, and two
credits outside policy (750.00, 120.00).

Open a finding. It shows the reason and recommended action, the evidence side by side (agreed,
delivered, billed), the calculation with its inputs, the rule version, and a timeline. **Generate
summary** adds a short plain-language summary labelled *AI-generated*. No figure or calculation
ever reads it. Running checks again creates 0 new findings.

## 3. Analyst and approver: workflow

1. As the analyst, open the 960.00 analyst-hours finding → **Take ownership** → **Reject** with a
   reason. It becomes final and is never counted (scenario 5).
2. Open the 600.00 incorrect-rate finding → **Take ownership** → **Propose for approval** with a
   root cause category and description (both required). The analyst can't approve their own proposal.
3. Sign in as `financeapprover@jm.com` → open it → **Approve**. Correction `JA-JM-0001` is prepared.
   Export it as CSV or JSON. JADAssure never sends it anywhere (GR-01).

## 4. Recovery

**Recovery tracker** lists each correction: identified, corrected billing, cash recovered.

1. **Simulate billing** (DEMO) loads a follow-up invoice that carries the correction reference.
   Corrected billing becomes 600.00, cash stays 0.00. An unpaid invoice isn't cash.
2. **Simulate payment** (DEMO) loads the payment. Cash recovered becomes 600.00 and the finding
   becomes *Recovered* (scenario 6).

The simulation only exists for demo orgs. Real orgs import their follow-up invoices and payments,
and the same matching applies.

If a later import repeats an issue whose cause was already confirmed (same customer, agreement,
check and item), the new finding opens with a **Recurring issue** notice that links the earlier
finding and its root cause. The stock demo data has no such later period. The automated test
`tests/test_recurrence.py` shows it.

## 5. Commercial manager: contracts and terms

Sign in as `commercialmanager@jm.com` → **Rules & agreements** → *Data strategy SOW* (Orchard).

1. Upload `demo-data/northwind-advisory/contracts/orchard-sow-amendment-1.txt`. Three terms are
   proposed, each beside the passage it came from:
   - Senior consultant rate 195.00/hour: clear.
   - Analyst rate 130.00: **held** as ambiguous ("subject to a further agreement").
   - 5% volume discount: **held** (threshold not defined).
   The document also contains an instruction to set all rates to zero. It's treated as contract
   text, not an instruction, and produces nothing (GR-07).
2. Before confirming anything, run checks as the analyst: no Orchard findings. Proposed terms are
   never used (scenario 4, GR-03).
3. **Confirm** the 195.00 rate. **Reject** the discount with a reason. Leave the analyst rate held.
4. Run checks again: two new incorrect-rate findings on Orchard, 300.00 (August) and 240.00
   (September).
5. **Rule versions** shows each rule's parameters. Changing one creates a new version, and every
   finding records the version that raised it.

## 6. Commercial manager: pricing opportunities

**Pricing opportunities** compares each confirmed contract price with its recorded cost. Sign in as
`commercialmanager@beyon.com`: two items price below the target margin, each with a suggested
price and an indicative annual uplift based on the last 12 months' billed quantity. JM has no cost
data, so its page says so. These are shown separately from leakage and never added to recovery
figures. The target margin (default 20%) is set by the admin in **Access & settings**.

## 7. Executive: overview

Sign in as `executive@jm.com` → **Overview**:

- Potential leakage, confirmed, corrected billing and cash recovered. After the steps above:
  confirmed 600.00, corrected billing 600.00, cash recovered 600.00. The rejected 960.00 is in none
  of them.
- Counts by status, including rejected and recurring.
- The prevented-recurrence estimate: confirmed findings' value × later months where the issue didn't
  come back. It's labelled as an estimate and kept apart from cash.
- Monthly trend chart (cash recovered vs identified) and the top root causes.

## 8. Administrator: governance

Sign in as `admin@jm.com` → **Access & settings**:

- **Users & roles**: add a user, change a role, deactivate.
- **Contract term reading**: external AI (Claude) is off by default and needs an API key in the
  server config. The built-in offline reader is used otherwise.
- **Scheduled runs**, **retention** and **pricing target margin**.
- **Audit history** → **Verify chain**: every state change is in a hash-chained log. Verification
  reports *intact*.
- **Delete organization** stays disabled until you type the org code.

## 9. Isolation (scenario 8)

Sign in as `financeanalyst@beyon.com` and paste a JM finding's URL: *not found*. The API answers
404, never 403, so it doesn't reveal that the record exists. Approving or simulating on another
org's records fails the same way.

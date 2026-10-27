# JM demo script (presenter)

A 15–20 minute end-to-end demonstration using the **JM** demo org. JM is a services company:
consulting hours and milestones (*advisory services*) plus software seat subscriptions
(*platform subscriptions*). All data is synthetic and labelled **DEMO**.

## Before you present

```bash
docker compose up -d
docker compose exec api python -m app.seed_demo --reset JM
```

Then open http://localhost:5173. The login page lists the demo accounts (local only). The shared
password is `DEMO_PASSWORD` in `backend/app/seed_demo.py`. Sign out between acts: each act is a
different person.

Keep `demo-data/jm-advisory/contracts/orchard-sow-amendment-1.txt` ready for Act 6.

**The one-line pitch:** JADAssure compares what was **agreed**, **delivered**, **billed** and
**collected**, shows where revenue leaked with the evidence, and tracks each fix until the cash is
actually back.

---

## Act 1. The problem (Executive, 1 min)

**Sign in:** `executive@jm.com` → **Overview**.

- Everything is zero. Nobody has looked yet.
- *Say:* "Revenue quietly leaks through billing mistakes nobody notices: hours not invoiced,
  old prices, discounts that never ended. Let's find JM's."

## Act 2. Data in (Administrator, 2 min)

**Sign in:** `admin@jm.com` → **Data setup**.

1. Two sources, both marked **DEMO**: *advisory services* and *platform subscriptions*. Their
   customers, contracts, deliveries, invoices and payments are already loaded.
2. Click a source → **Sync now**. Every record type reports **0 inserted, 0 updated**.
   - *Say:* "Re-importing never duplicates anything. Safe to run every night."
3. Point out *Manual uploads* (CSV with templates, profiling and mapping) for systems without a
   connector.
4. **Rules & agreements**: the five checks with their settings. Changing a setting creates a new
   rule version, and every finding records which version raised it.

## Act 3. Finding the leaks (Finance analyst, 4 min)

**Sign in:** `financeanalyst@jm.com` → **Findings** → **Run checks now**.

After a few seconds: **6 findings, 4,530.00 USD potential leakage.**

| Finding | Value |
|---|---|
| Delivered not billed: 12 senior consultant hours in April | 2,160.00 |
| Delivered not billed: 8 analyst hours in June | 960.00 |
| Incorrect contracted rate: Bluefin seats in March billed at 40, contract says 45 | 600.00 |
| Missed contractual increase: Bluefin Jul, Aug, Sep (5% uplift not applied) | 270.00 each |

1. Open the **2,160.00** finding. Show:
   - the plain-English reason and recommended action;
   - **Evidence** side by side: agreed (contract rate), delivered (52 hours), billed (40 hours);
   - the **calculation** with its inputs, and the rule version.
   - *Say:* "Every number can be traced back to a source record. No black box."
2. **Generate summary**: a short summary labelled *AI-generated, not used in calculations*.
   - *Say:* "AI can help explain, but it never decides what's owed."
3. Click **Run checks now** again: **0 new**. No duplicates.

## Act 4. A false alarm (Finance analyst, 1 min)

Still as the analyst, open the **960.00** analyst-hours finding → **Take ownership** →
**Reject** with the reason "Non-billable workshop prep agreed with the customer".

- *Say:* "People stay in charge. A rejected finding is final and never counted as money."

## Act 5. Fix it and get the cash (Analyst → Approver → Recovery, 4 min)

1. As the analyst, open the **600.00** incorrect-rate finding → **Take ownership** →
   **Propose for approval**. Root cause: *Price not updated in billing system*, plus a short
   description.
   - The panel says a **different** person must approve. *Say:* "Nobody approves their own work."
2. Sign out. **Sign in:** `financeapprover@jm.com` → open the finding → **Approve**.
   - Correction **JA-JM-0001** is prepared. Export it as CSV or JSON.
   - *Say:* "JADAssure prepares the correction. It never sends invoices or contacts customers."
3. **Recovery tracker** → JA-JM-0001:
   - **Simulate billing** (DEMO): corrected billing **600.00**, cash recovered **0.00**.
     *Say:* "Sending an invoice isn't getting paid."
   - **Simulate payment** (DEMO): cash recovered **600.00**, and the finding becomes **Recovered**.
   - *Say:* "In production these come from the next invoice and payment import. Same matching."

## Act 6. Reading a contract safely (Commercial manager, 3 min)

**Sign in:** `commercialmanager@jm.com` → **Rules & agreements** → *Data strategy SOW* (Orchard).

1. Upload `orchard-sow-amendment-1.txt` (**Upload & read terms**). Three terms are proposed, each
   beside the sentence it came from:
   - Senior consultant rate **195.00/hour**: clear.
   - Analyst rate 130.00: **held**, the wording says "subject to a further agreement".
   - 5% volume discount: **held**, the threshold isn't defined.
   - *Say:* "The document also hides an instruction to set all rates to zero. It's treated as
     text, not a command, and produces nothing."
2. *Say:* "Nothing proposed is used until a person confirms it." (If you have time: sign in as the
   analyst, **Run checks now**, and show there are no Orchard findings yet.)
3. **Confirm** the 195.00 rate. **Reject** the discount with a reason. Leave the analyst rate held.
4. Sign in as the analyst → **Run checks now**: **2 new** findings on Orchard, **300.00** (August)
   and **240.00** (September). Both were billed at the old 180 rate.

## Act 7. The scoreboard (Executive, 2 min)

**Sign in:** `executive@jm.com` → **Overview**:

| Figure | Value | What it means |
|---|---|---|
| Cash recovered | 600.00 USD | Only real payments against corrected invoices |
| Potential leakage | 3,510.00 USD | Still open: 2,160 + 3 × 270 + 300 + 240 |
| Confirmed | 600.00 USD | Approved by a finance approver |
| Corrected billing | 600.00 USD | Re-invoiced, not yet the same as cash |
| Rejected | 1 | The 960.00 is in none of the money figures |

Also show the prevented-recurrence estimate (labelled as an estimate), the monthly trend, and the
top root causes.

**Pricing opportunities**: JM has no cost data, so the page says so and suggests nothing.
*Say:* "With cost data it flags prices below your target margin. Beyon's demo shows two."

## Act 8. Trust and control (Administrator, 2 min)

**Sign in:** `admin@jm.com` → **Access & settings**:

- **Users & roles**: five roles, each seeing only what it needs.
- **Contract term reading**: external AI is off by default and needs an explicit, audited opt-in.
- **Audit history** → **Verify chain**: *intact*. Every action above is in a tamper-evident log.

**Isolation:** copy a JM finding URL, sign in as `financeanalyst@beyon.com`, paste it:
**not found**. *Say:* "Each organization's data is completely separate."

## Close

*Say:* "We found 5,070 dollars of leakage across 8 issues, threw out one false alarm, fixed one
end to end and saw the cash arrive, and read a contract without trusting it blindly. Every step
was evidence-backed, approved by people and audited."

To run it again: `docker compose exec api python -m app.seed_demo --reset JM`.

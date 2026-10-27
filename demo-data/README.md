# Demo data (DATA-001)

**Classification: public / synthetic.** Every company, person, number and document here is
fictional. Everything loads into organizations flagged `is_demo` and is labelled **DEMO** in the UI
and API (GR-14). Never present it as a live customer integration.

- `generate.py` writes every `*/baseline/*.csv` and `beyon-distribution/manual/*.csv`. Edit the
  generator, then re-run `python demo-data/generate.py`. Don't hand-edit the CSVs.
- CSV headers are the canonical import-template headers, so the demonstration connector (BE-009)
  loads them with no mapping step.
- `app.seed_demo` creates the orgs JM and Beyon and their users, and loads each `baseline/` folder
  through the demonstration connector.

## The three business types, one engine

| Dataset | Demo org | Business type | Billable unit | Billing frequency |
|---|---|---|---|---|
| `jm-advisory` | **JM** | professional_services | consultant hours; milestones | monthly; milestone |
| `jm-subscriptions` | **JM** | subscription_software | seats | monthly (in advance) |
| `beyon-distribution` | **Beyon** | distribution | shipped units | per_event; USD and CAD |

The engine treats them identically. Only data and configuration differ (FR-42). JM loads two
datasets through two labelled demo connector sources. The dataset folder names are internal;
users see the org names JM and Beyon (decision 0005).

Logins follow the role on each org's domain: `admin@`, `financeanalyst@`, `financeapprover@`,
`commercialmanager@`, `executive@` + `jm.com` or `beyon.com`.

## Planted discrepancies (expected findings once M2 lands)

Values are net of tax, in the invoice currency.

| # | Dataset | What happened | Expected finding | Expected value |
|---|---|---|---|---|
| 1 | jm-advisory | 12 extra senior hours delivered 2026-04-28 (`NW-E-202604-S2`); April invoice bills only 40 h | delivered_not_billed, SENIOR-CONSULT, Apr 2026 | 12 × 180 = **2,160.00 USD** |
| 5 | jm-advisory | 8 analyst hours 2026-06-24 (`NW-E-202606-A2`) were non-billable workshop prep; looks unbilled | delivered_not_billed, ANALYST, Jun 2026 (reviewer **rejects**) | 8 × 120 = **960.00 USD** |
| 2, 6 | jm-subscriptions | Bluefin March seats billed at 40 instead of 45 (`CC-I-B-202603-L1`) | incorrect_rate | 120 × 5 = **600.00 USD** |
| — | jm-subscriptions | Bluefin renewal adds 5% from 2026-07-01 (`CC-T3`); Jul, Aug, Sep billed at 45 | missed_increase ×3 (one per invoice line) | 120 × 2.25 = **270.00 USD** each |
| 3 | beyon-distribution | Q1 promo 10% discount on WIDGET-A expired 2026-03-31 but applied to April shipment `SHP-1010` | expired_discount | 300 × 12.50 × 10% = **375.00 USD** |
| — | beyon-distribution | Same expired discount on May shipment `SHP-1015` | expired_discount | 150 × 12.50 × 10% = **187.50 USD** |
| — | beyon-distribution | Credit `RS-CR-1` 750.00 above the 500 approval threshold with no approval reference | credit_outside_policy | **750.00 USD** |
| — | beyon-distribution | Credit `RS-CR-2` 120.00 with no reason code | credit_outside_policy | **120.00 USD** |

**Only after confirming the extracted amendment term** (scenario 4, M4): upload
`jm-advisory/contracts/orchard-sow-amendment-1.txt` to the Orchard *Data strategy SOW* in JM
and confirm the proposed "Senior consultant rate: USD 195.00 per hour" term. The next check run then
raises two `incorrect_rate` findings on Orchard's August and September advisory invoices:
20 × 15 = **300.00 USD** and 16 × 15 = **240.00 USD**. Before confirmation those lines have no
confirmed rate and are skipped (GR-03).

**Must NOT produce findings** (each guards a matching rule):

- JM subscriptions, Northgate: an authorized 10% discount (`CC-T5`, approval APP-77) applied all year.
- Beyon: shipment `SHP-1001` with the promo discount *inside* its validity window.
- Beyon: shipment `SHP-1020` (100 units) billed as 60 + 40 on two invoices (split invoice).
- Beyon: shipments `SHP-1031` + `SHP-1032` (50 + 50) billed as one line of 100 (aggregated line).
- Beyon: credit `RS-CR-3` 300.00 with a reason code, below the approval threshold.
- Beyon, Maple: CAD invoices billed correctly (second currency; never compared with USD).
- JM advisory, Orchard: milestone fees billed as agreed.
- JM advisory: September hours invoiced 2026-10-03 and not yet paid. An unpaid invoice is not leakage.

## Acceptance scenarios (requirements §11) and where they come from

| # | Scenario | Source |
|---|---|---|
| 1 | Delivered item omitted from billing | jm-advisory row 1 |
| 2 | Invoice at the wrong contracted rate | jm-subscriptions row 2 |
| 3 | Discount applied after expiry | beyon-distribution row 3 |
| 4 | Ambiguous contract term held for confirmation | `jm-advisory/contracts/orchard-sow-amendment-1.txt` §2.2 ("subject to agreement"), uploaded in M4. §4 also contains an embedded instruction that must have no effect (GR-07). |
| 5 | Rejected finding not counted as recovered | jm-advisory row 5 |
| 6 | Approved correction → corrected billing → cash only after payment | jm-subscriptions row 2. Follow-up invoice and payment files are added in M3 (they must carry the correction reference generated at approval). |
| 7 | Repeat import changes nothing | Re-sync any baseline, or re-upload any file into the same data source |
| 8 | No cross-organization access | Any two demo orgs' users |

## Manual-upload exercise

`beyon-distribution/manual/shipments-september.csv` is a "messy" export with non-canonical headers
(`Shipment Ref`, `Account`, `SKU`, `Qty`, `Ship Date`, …) and one bad row (`Qty = n/a`). Upload it
as **Billable events** into the *Manual uploads* source. Map `Shipment Ref` → `event_id`,
`Account` → `customer_id` and `Contract` → `agreement_id`. The remaining columns are recognized
automatically. Commit: 2 inserted, 1 rejected with a downloadable error report. Upload it again:
0 inserted, 2 unchanged, 1 rejected. These shipments are already invoiced in the baseline
(`RS-I-1040`, `RS-I-1041`), so they produce no findings.

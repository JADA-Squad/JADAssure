"""Generate the synthetic JADAssure demo datasets (DATA-001).

    python demo-data/generate.py

Everything here is fictional (classification: public/synthetic). Each dataset writes canonical
CSVs (same headers as the import templates) to <dataset>/baseline/, one file per record type.
The planted discrepancies and their expected values are listed in demo-data/README.md. Keep that
file in sync when you change anything below.
"""

import calendar
import csv
import pathlib
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

ROOT = pathlib.Path(__file__).resolve().parent

HEADERS = {
    "customer": ["customer_id", "name", "currency"],
    "agreement": ["agreement_id", "customer_id", "title", "start_date", "end_date", "billing_frequency", "currency"],
    "agreement_version": ["version_id", "agreement_id", "version_no", "effective_from", "effective_to", "reason"],
    "commercial_term": ["term_id", "version_id", "item_code", "term_type", "value", "unit", "currency",
                        "effective_from", "effective_to", "approval_ref", "max_value"],
    "billable_event": ["event_id", "customer_id", "agreement_id", "item_code", "quantity", "unit", "service_date",
                       "billing_date", "currency"],
    "invoice": ["invoice_id", "customer_id", "number", "invoice_date", "currency", "status", "correction_reference"],
    "invoice_line": ["line_id", "invoice_id", "agreement_id", "item_code", "quantity", "unit_price", "discount_pct",
                     "net_amount", "tax_amount", "service_period_start", "service_period_end"],
    "credit": ["credit_id", "customer_id", "invoice_id", "amount", "currency", "reason_code", "approval_ref",
               "credit_date"],
    "payment": ["payment_id", "customer_id", "amount", "currency", "payment_date"],
    "payment_allocation": ["allocation_id", "payment_id", "invoice_id", "amount"],
    "cost_record": ["cost_id", "item_code", "unit_cost", "currency", "effective_from", "effective_to"],
}

CENT = Decimal("0.01")


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_EVEN)


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


class Dataset:
    def __init__(self, name: str):
        self.name = name
        self.rows: dict[str, list[dict]] = {k: [] for k in HEADERS}
        self.invoice_totals: dict[str, Decimal] = {}

    def add(self, record_type: str, **row) -> None:
        self.rows[record_type].append(row)

    def invoice(self, inv_id: str, customer: str, number: str, on: date, currency: str,
                lines: list[dict], status: str = "posted") -> None:
        self.add("invoice", invoice_id=inv_id, customer_id=customer, number=number, invoice_date=on,
                 currency=currency, status=status)
        total = Decimal("0")
        for n, line in enumerate(lines, start=1):
            qty, price = Decimal(line["quantity"]), Decimal(line["unit_price"])
            disc = Decimal(line.get("discount_pct") or "0")
            net = money(qty * price * (1 - disc / 100))
            tax = money(net * Decimal(line.get("tax_rate", "0")))
            self.add("invoice_line", line_id=f"{inv_id}-L{n}", invoice_id=inv_id, agreement_id=line.get("agreement_id", ""),
                     item_code=line["item_code"], quantity=qty, unit_price=price,
                     discount_pct=disc if disc else "", net_amount=net, tax_amount=tax,
                     service_period_start=line["start"], service_period_end=line["end"])
            total += net + tax
        self.invoice_totals[inv_id] = total

    def pay(self, pay_id: str, customer: str, inv_id: str, on: date, currency: str) -> None:
        amount = self.invoice_totals[inv_id]
        self.add("payment", payment_id=pay_id, customer_id=customer, amount=amount, currency=currency, payment_date=on)
        self.add("payment_allocation", allocation_id=f"{pay_id}-A1", payment_id=pay_id, invoice_id=inv_id, amount=amount)

    def write(self) -> None:
        out = ROOT / self.name / "baseline"
        out.mkdir(parents=True, exist_ok=True)
        for record_type, rows in self.rows.items():
            if not rows:
                continue
            with open(out / f"{record_type}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=HEADERS[record_type], lineterminator="\n")
                w.writeheader()
                for row in rows:
                    w.writerow({k: ("" if row.get(k) is None else row.get(k, "")) for k in HEADERS[record_type]})


# ------------------------------------------------------------------------- Northwind Advisory
# Professional services: consultant hours billed monthly; milestone fees.

def northwind() -> Dataset:
    d = Dataset("northwind-advisory")
    d.add("customer", customer_id="NW-C1", name="Halcyon Retail Group", currency="USD")
    d.add("customer", customer_id="NW-C2", name="Orchard Health Partners", currency="USD")
    d.add("agreement", agreement_id="NW-A1", customer_id="NW-C1", title="Transformation advisory MSA",
          start_date=date(2026, 1, 1), billing_frequency="monthly", currency="USD")
    d.add("agreement", agreement_id="NW-A2", customer_id="NW-C2", title="Data strategy SOW",
          start_date=date(2026, 2, 1), end_date=date(2026, 12, 31), billing_frequency="milestone", currency="USD")
    d.add("agreement_version", version_id="NW-V1", agreement_id="NW-A1", version_no=1,
          effective_from=date(2026, 1, 1), reason="Original MSA")
    d.add("agreement_version", version_id="NW-V2", agreement_id="NW-A2", version_no=1,
          effective_from=date(2026, 2, 1), reason="Original SOW")
    for tid, vid, item, value in (("NW-T1", "NW-V1", "SENIOR-CONSULT", "180"), ("NW-T2", "NW-V1", "ANALYST", "120"),
                                  ("NW-T3", "NW-V2", "DS-MILESTONE", "25000")):
        d.add("commercial_term", term_id=tid, version_id=vid, item_code=item, term_type="rate", value=value,
              unit="milestone" if item == "DS-MILESTONE" else "hour", currency="USD",
              effective_from=date(2026, 2, 1) if vid == "NW-V2" else date(2026, 1, 1))

    senior = {1: 40, 2: 44, 3: 48, 4: 40, 5: 46, 6: 42, 7: 38, 8: 44, 9: 40}
    analyst = {1: 60, 2: 64, 3: 58, 4: 62, 5: 60, 6: 56, 7: 60, 8: 58, 9: 62}
    for m in range(1, 10):
        end = month_end(2026, m)
        d.add("billable_event", event_id=f"NW-E-2026{m:02}-S", customer_id="NW-C1", agreement_id="NW-A1",
              item_code="SENIOR-CONSULT", quantity=senior[m], unit="hour", service_date=date(2026, m, 15),
              billing_date=end, currency="USD")
        d.add("billable_event", event_id=f"NW-E-2026{m:02}-A", customer_id="NW-C1", agreement_id="NW-A1",
              item_code="ANALYST", quantity=analyst[m], unit="hour", service_date=date(2026, m, 15),
              billing_date=end, currency="USD")
    # Scenario 1: 12 extra senior hours in April were delivered but never invoiced.
    d.add("billable_event", event_id="NW-E-202604-S2", customer_id="NW-C1", agreement_id="NW-A1",
          item_code="SENIOR-CONSULT", quantity=12, unit="hour", service_date=date(2026, 4, 28),
          billing_date=month_end(2026, 4), currency="USD")
    # Scenario 5: 8 analyst hours in June look unbilled, but were agreed as non-billable workshop prep;
    # a reviewer rejects this finding.
    d.add("billable_event", event_id="NW-E-202606-A2", customer_id="NW-C1", agreement_id="NW-A1",
          item_code="ANALYST", quantity=8, unit="hour", service_date=date(2026, 6, 24),
          billing_date=month_end(2026, 6), currency="USD")

    for m in range(1, 10):
        start, end = date(2026, m, 1), month_end(2026, m)
        inv = f"NW-I-2026{m:02}"
        on = end + timedelta(days=3)
        d.invoice(inv, "NW-C1", f"NWA-{1000 + m}", on, "USD", [
            {"agreement_id": "NW-A1", "item_code": "SENIOR-CONSULT", "quantity": senior[m], "unit_price": "180",
             "start": start, "end": end},
            {"agreement_id": "NW-A1", "item_code": "ANALYST", "quantity": analyst[m], "unit_price": "120",
             "start": start, "end": end},
        ])
        if m <= 8:
            d.pay(f"NW-P-2026{m:02}", "NW-C1", inv, on + timedelta(days=30), "USD")

    for n, (due, paid) in enumerate(((date(2026, 3, 31), True), (date(2026, 6, 30), True)), start=1):
        d.add("billable_event", event_id=f"NW-E-MS{n}", customer_id="NW-C2", agreement_id="NW-A2",
              item_code="DS-MILESTONE", quantity=1, unit="milestone", service_date=due, billing_date=due,
              currency="USD")
        inv = f"NW-I-MS{n}"
        d.invoice(inv, "NW-C2", f"NWA-M{n}", due + timedelta(days=2), "USD", [
            {"agreement_id": "NW-A2", "item_code": "DS-MILESTONE", "quantity": 1, "unit_price": "25000",
             "start": due, "end": due},
        ])
        if paid:
            d.pay(f"NW-P-MS{n}", "NW-C2", inv, due + timedelta(days=40), "USD")

    # Scenario 4: ad hoc senior advisory hours for Orchard from August, billed at the old 180/hour.
    # The amendment (contracts/orchard-sow-amendment-1.txt) sets 195/hour from 1 August, but until
    # someone confirms that extracted term there is no confirmed Orchard rate, so the engine raises
    # nothing. After confirmation, a re-run finds the shortfall (GR-03).
    for m, hours in ((8, 20), (9, 16)):
        end = month_end(2026, m)
        d.add("billable_event", event_id=f"NW-E-ORCH-2026{m:02}", customer_id="NW-C2", agreement_id="NW-A2",
              item_code="SENIOR-CONSULT", quantity=hours, unit="hour", service_date=end, billing_date=end,
              currency="USD")
        d.invoice(f"NW-I-ORCH-2026{m:02}", "NW-C2", f"NWA-O{m:02}", end + timedelta(days=3), "USD", [
            {"agreement_id": "NW-A2", "item_code": "SENIOR-CONSULT", "quantity": hours, "unit_price": "180",
             "start": end, "end": end},
        ])
    return d


# ------------------------------------------------------------------------- Cirrus Cloud
# Subscription software: seats billed monthly in advance; renewal with a 5% escalation.

def cirrus() -> Dataset:
    d = Dataset("cirrus-cloud")
    d.add("customer", customer_id="CC-C1", name="Bluefin Logistics", currency="USD")
    d.add("customer", customer_id="CC-C2", name="Northgate Media", currency="USD")
    for aid, cid, title in (("CC-A1", "CC-C1", "Platform subscription"), ("CC-A2", "CC-C2", "Platform subscription")):
        d.add("agreement", agreement_id=aid, customer_id=cid, title=title, start_date=date(2026, 1, 1),
              billing_frequency="monthly", currency="USD")
    d.add("agreement_version", version_id="CC-V1", agreement_id="CC-A1", version_no=1,
          effective_from=date(2026, 1, 1), effective_to=date(2026, 6, 30), reason="Initial term")
    d.add("agreement_version", version_id="CC-V2", agreement_id="CC-A1", version_no=2,
          effective_from=date(2026, 7, 1), reason="Renewal: 5% escalation on seats")
    d.add("agreement_version", version_id="CC-V3", agreement_id="CC-A2", version_no=1,
          effective_from=date(2026, 1, 1), reason="Initial term")
    terms = [
        ("CC-T1", "CC-V1", "PLATFORM-SEAT", "rate", "45", "seat", date(2026, 1, 1), None, ""),
        ("CC-T2", "CC-V2", "PLATFORM-SEAT", "rate", "45", "seat", date(2026, 7, 1), None, ""),
        ("CC-T3", "CC-V2", "PLATFORM-SEAT", "escalation", "5", "pct", date(2026, 7, 1), None, "RENEWAL-2026"),
        ("CC-T4", "CC-V3", "PLATFORM-SEAT", "rate", "50", "seat", date(2026, 1, 1), None, ""),
        ("CC-T5", "CC-V3", "PLATFORM-SEAT", "discount", "10", "pct", date(2026, 1, 1), date(2026, 12, 31), "APP-77"),
    ]
    for tid, vid, item, ttype, value, unit, frm, to, ref in terms:
        d.add("commercial_term", term_id=tid, version_id=vid, item_code=item, term_type=ttype, value=value, unit=unit,
              currency="" if unit == "pct" else "USD", effective_from=frm, effective_to=to, approval_ref=ref)

    for m in range(1, 10):
        start, end = date(2026, m, 1), month_end(2026, m)
        for cid, aid, seats in (("CC-C1", "CC-A1", 120), ("CC-C2", "CC-A2", 60)):
            d.add("billable_event", event_id=f"{aid}-SEATS-2026{m:02}", customer_id=cid, agreement_id=aid,
                  item_code="PLATFORM-SEAT", quantity=seats, unit="seat", service_date=start, billing_date=start,
                  currency="USD")
        # Bluefin: scenario 2 (March billed at 40 instead of 45); Jul-Sep billed at 45, missing the 5% escalation.
        price = "40" if m == 3 else "45"
        inv = f"CC-I-B-2026{m:02}"
        d.invoice(inv, "CC-C1", f"CIR-B{m:02}", start, "USD", [
            {"agreement_id": "CC-A1", "item_code": "PLATFORM-SEAT", "quantity": 120, "unit_price": price,
             "tax_rate": "0.08", "start": start, "end": end},
        ])
        d.pay(f"CC-P-B-2026{m:02}", "CC-C1", inv, start + timedelta(days=21), "USD")
        # Northgate: authorised 10% discount (APP-77); correct throughout.
        inv = f"CC-I-N-2026{m:02}"
        d.invoice(inv, "CC-C2", f"CIR-N{m:02}", start, "USD", [
            {"agreement_id": "CC-A2", "item_code": "PLATFORM-SEAT", "quantity": 60, "unit_price": "50",
             "discount_pct": "10", "tax_rate": "0.08", "start": start, "end": end},
        ])
        d.pay(f"CC-P-N-2026{m:02}", "CC-C2", inv, start + timedelta(days=25), "USD")
    return d


# ------------------------------------------------------------------------- Ridgeline Supply
# Distribution: shipments billed per event; promo discount; credit policy; two currencies.

def ridgeline() -> Dataset:
    d = Dataset("ridgeline-supply")
    d.add("customer", customer_id="RS-C1", name="Corbel Hardware", currency="USD")
    d.add("customer", customer_id="RS-C2", name="Maple Fixtures", currency="CAD")
    d.add("agreement", agreement_id="RS-A1", customer_id="RS-C1", title="Supply agreement", start_date=date(2026, 1, 1),
          billing_frequency="per_event", currency="USD")
    d.add("agreement", agreement_id="RS-A2", customer_id="RS-C2", title="Supply agreement (Canada)",
          start_date=date(2026, 1, 1), billing_frequency="per_event", currency="CAD")
    d.add("agreement_version", version_id="RS-V1", agreement_id="RS-A1", version_no=1, effective_from=date(2026, 1, 1),
          reason="Original")
    d.add("agreement_version", version_id="RS-V2", agreement_id="RS-A2", version_no=1, effective_from=date(2026, 1, 1),
          reason="Original")
    terms = [
        ("RS-T1", "RS-V1", "WIDGET-A", "rate", "12.50", "unit", "USD", date(2026, 1, 1), None, "", ""),
        ("RS-T2", "RS-V1", "WIDGET-B", "rate", "30.00", "unit", "USD", date(2026, 1, 1), None, "", ""),
        ("RS-T3", "RS-V1", "WIDGET-A", "discount", "10", "pct", "", date(2026, 1, 1), date(2026, 3, 31), "PROMO-Q1", ""),
        ("RS-T4", "RS-V1", "", "credit_policy", "500", "", "USD", date(2026, 1, 1), None, "CREDIT-POLICY-2026", "2000"),
        ("RS-T5", "RS-V2", "WIDGET-A", "rate", "16.00", "unit", "CAD", date(2026, 1, 1), None, "", ""),
        ("RS-T6", "RS-V2", "WIDGET-B", "rate", "39.00", "unit", "CAD", date(2026, 1, 1), None, "", ""),
    ]
    for tid, vid, item, ttype, value, unit, ccy, frm, to, ref, mx in terms:
        d.add("commercial_term", term_id=tid, version_id=vid, item_code=item, term_type=ttype, value=value, unit=unit,
              currency=ccy, effective_from=frm, effective_to=to, approval_ref=ref, max_value=mx)

    def ship(eid, cid, aid, item, qty, on, ccy):
        d.add("billable_event", event_id=eid, customer_id=cid, agreement_id=aid, item_code=item, quantity=qty,
              unit="unit", service_date=on, billing_date=on, currency=ccy)

    def bill(inv, cid, aid, on, ccy, lines, number):
        d.invoice(inv, cid, number, on + timedelta(days=1), ccy, [
            {"agreement_id": aid, "item_code": item, "quantity": qty, "unit_price": price, "discount_pct": disc,
             "tax_rate": "0.07", "start": on, "end": on}
            for item, qty, price, disc in lines
        ])

    # Corbel (USD)
    ship("SHP-1001", "RS-C1", "RS-A1", "WIDGET-A", 200, date(2026, 2, 12), "USD")      # promo valid
    bill("RS-I-1001", "RS-C1", "RS-A1", date(2026, 2, 12), "USD", [("WIDGET-A", 200, "12.50", "10")], "RDG-1001")
    ship("SHP-1005", "RS-C1", "RS-A1", "WIDGET-B", 80, date(2026, 3, 9), "USD")
    bill("RS-I-1005", "RS-C1", "RS-A1", date(2026, 3, 9), "USD", [("WIDGET-B", 80, "30.00", "")], "RDG-1005")
    # Scenario 3: promo discount kept after it expired on 2026-03-31.
    ship("SHP-1010", "RS-C1", "RS-A1", "WIDGET-A", 300, date(2026, 4, 14), "USD")
    bill("RS-I-1010", "RS-C1", "RS-A1", date(2026, 4, 14), "USD", [("WIDGET-A", 300, "12.50", "10")], "RDG-1010")
    ship("SHP-1015", "RS-C1", "RS-A1", "WIDGET-A", 150, date(2026, 5, 20), "USD")
    bill("RS-I-1015", "RS-C1", "RS-A1", date(2026, 5, 20), "USD", [("WIDGET-A", 150, "12.50", "10")], "RDG-1015")
    # Split invoice: one shipment of 100 billed as 60 + 40 on two invoices (no finding).
    ship("SHP-1020", "RS-C1", "RS-A1", "WIDGET-B", 100, date(2026, 6, 10), "USD")
    bill("RS-I-1020A", "RS-C1", "RS-A1", date(2026, 6, 10), "USD", [("WIDGET-B", 60, "30.00", "")], "RDG-1020A")
    bill("RS-I-1020B", "RS-C1", "RS-A1", date(2026, 6, 10), "USD", [("WIDGET-B", 40, "30.00", "")], "RDG-1020B")
    # Aggregated line: two same-day shipments billed as one line of 100 (no finding).
    ship("SHP-1031", "RS-C1", "RS-A1", "WIDGET-A", 50, date(2026, 7, 8), "USD")
    ship("SHP-1032", "RS-C1", "RS-A1", "WIDGET-A", 50, date(2026, 7, 8), "USD")
    bill("RS-I-1031", "RS-C1", "RS-A1", date(2026, 7, 8), "USD", [("WIDGET-A", 100, "12.50", "")], "RDG-1031")
    # September shipments are invoiced here; the shipment records themselves arrive via the manual
    # upload exercise (manual/shipments-september.csv).
    bill("RS-I-1040", "RS-C1", "RS-A1", date(2026, 9, 3), "USD", [("WIDGET-B", 70, "30.00", "")], "RDG-1040")
    bill("RS-I-1041", "RS-C1", "RS-A1", date(2026, 9, 17), "USD", [("WIDGET-A", 120, "12.50", "")], "RDG-1041")

    for inv in ("RS-I-1001", "RS-I-1005", "RS-I-1010", "RS-I-1015", "RS-I-1020A", "RS-I-1020B", "RS-I-1031"):
        d.pay(inv.replace("-I-", "-P-"), "RS-C1", inv, date(2026, 8, 31), "USD")

    # Credits against the agreement-wide policy: approval needed above 500, maximum 2000.
    d.add("credit", credit_id="RS-CR-1", customer_id="RS-C1", invoice_id="RS-I-1005", amount="750.00", currency="USD",
          reason_code="DAMAGED-GOODS", approval_ref="", credit_date=date(2026, 3, 20))          # no approval
    d.add("credit", credit_id="RS-CR-2", customer_id="RS-C1", invoice_id="RS-I-1020A", amount="120.00", currency="USD",
          reason_code="", approval_ref="", credit_date=date(2026, 6, 25))                        # no reason
    d.add("credit", credit_id="RS-CR-3", customer_id="RS-C1", invoice_id="RS-I-1031", amount="300.00", currency="USD",
          reason_code="LATE-DELIVERY", approval_ref="", credit_date=date(2026, 7, 20))          # within policy

    # Maple (CAD): billed correctly; shows a second currency processed side by side.
    for n, (item, qty, price, on) in enumerate((("WIDGET-A", 400, "16.00", date(2026, 4, 2)),
                                                ("WIDGET-B", 90, "39.00", date(2026, 6, 18))), start=1):
        ship(f"SHP-2{n:03}", "RS-C2", "RS-A2", item, qty, on, "CAD")
        bill(f"RS-I-2{n:03}", "RS-C2", "RS-A2", on, "CAD", [(item, qty, price, "")], f"RDG-C{n:03}")
        d.pay(f"RS-P-2{n:03}", "RS-C2", f"RS-I-2{n:03}", on + timedelta(days=30), "CAD")

    for cid, item, cost, ccy in (("RS-K1", "WIDGET-A", "11.80", "USD"), ("RS-K2", "WIDGET-B", "21.00", "USD"),
                                 ("RS-K3", "WIDGET-A", "13.50", "CAD"), ("RS-K4", "WIDGET-B", "27.00", "CAD")):
        d.add("cost_record", cost_id=cid, item_code=item, unit_cost=cost, currency=ccy, effective_from=date(2026, 1, 1))
    return d


def ridgeline_manual_upload() -> None:
    """A messy export for the manual-upload exercise: non-canonical headers and one bad row."""
    out = ROOT / "ridgeline-supply" / "manual"
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        ["Shipment Ref", "Account", "Contract", "SKU", "Qty", "Ship Date", "Bill By", "Currency"],
        ["SHP-1040", "RS-C1", "RS-A1", "WIDGET-B", "70", "2026-09-03", "2026-09-03", "USD"],
        ["SHP-1041", "RS-C1", "RS-A1", "WIDGET-A", "120", "2026-09-17", "2026-09-17", "USD"],
        ["SHP-1042", "RS-C1", "RS-A1", "WIDGET-A", "n/a", "2026-09-29", "2026-09-29", "USD"],
    ]
    with open(out / "shipments-september.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)


if __name__ == "__main__":
    for dataset in (northwind(), cirrus(), ridgeline()):
        dataset.write()
    ridgeline_manual_upload()
    print("demo data written to", ROOT)

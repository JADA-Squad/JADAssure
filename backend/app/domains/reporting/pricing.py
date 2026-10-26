"""Pricing opportunities (BE-026, FR-33): future pricing decisions, never billing errors.

For every agreement × item with a confirmed rate in effect today, compare what the contract
permits (rate + escalations, less the maximum authorized discount) with the unit cost in effect
today in the same currency. Below the org's target margin it's an opportunity: a commercial decision
for the next negotiation, not leakage. Opportunities come from their own endpoint and never enter
leakage or recovery figures. Without a cost record for an item there is no opportunity; the item
is listed as missing cost data instead.
"""

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.money import to_money
from app.domains.access.models import Organization
from app.domains.contracts.models import Agreement
from app.domains.contracts.terms import TermBook
from app.domains.ingestion.models import CostRecord, Customer, Invoice, InvoiceLine
from app.domains.matching.pricing import expected_price, price

DEFAULT_TARGET_MARGIN_PCT = Decimal("20")
HUNDRED = Decimal("100")


def _pct(x: Decimal) -> Decimal:
    return (x * HUNDRED).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)


def opportunities(session: Session, org_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    org = session.get(Organization, org_id)
    target = Decimal(str((org.settings or {}).get("pricing_target_margin_pct", DEFAULT_TARGET_MARGIN_PCT)))  # type: ignore[union-attr]
    book = TermBook.load(session, org_id)
    agreements = {a.id: a for a in session.scalars(select(Agreement).where(Agreement.org_id == org_id))}
    customers = {c.id: c.name for c in session.scalars(select(Customer).where(Customer.org_id == org_id))}
    costs = session.scalars(select(CostRecord).where(
        CostRecord.org_id == org_id, CostRecord.effective_from <= today,
        or_(CostRecord.effective_to.is_(None), CostRecord.effective_to >= today))).all()
    cost_of = {(c.item_code, c.currency): c for c in sorted(costs, key=lambda c: c.effective_from)}

    # Billed volume in the last 12 months per (agreement, item), to size the indicative uplift.
    since = today - timedelta(days=365)
    volume: dict[tuple, Decimal] = defaultdict(lambda: Decimal("0"))
    for agreement_id, item, qty in session.execute(
        select(InvoiceLine.agreement_id, InvoiceLine.item_code, func.sum(InvoiceLine.quantity))
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(InvoiceLine.org_id == org_id, Invoice.invoice_date >= since, Invoice.correction_reference.is_(None))
        .group_by(InvoiceLine.agreement_id, InvoiceLine.item_code)
    ):
        volume[(agreement_id, item)] += qty

    agreement_of_version = {v.id: v.agreement_id for versions in book.versions.values() for v in versions}
    items = {(agreement_of_version[t.agreement_version_id], t.item_code)
             for terms in book.terms.values() for t in terms if t.term_type == "rate" and t.item_code}
    found, missing = [], set()
    for agreement_id, item in sorted(items, key=lambda k: (str(k[0]), k[1])):
        agreement = agreements.get(agreement_id)
        exp = expected_price(book, agreement_id, item, today) if agreement else None
        if exp is None:
            continue  # no rate in effect today
        currency = exp.currency or agreement.currency  # type: ignore[union-attr]
        cost = cost_of.get((item, currency))
        if cost is None:
            missing.add((item, currency))
            continue
        net = exp.net_unit(exp.approved_discount_pct)
        if net <= 0:
            continue
        margin = (net - cost.unit_cost) / net
        if margin * HUNDRED >= target:
            continue
        suggested = price(cost.unit_cost / (1 - target / HUNDRED))
        qty = volume[(agreement_id, item)]
        found.append({
            "agreement_id": str(agreement_id), "agreement_title": agreement.title,  # type: ignore[union-attr]
            "customer_name": customers.get(agreement.customer_id),  # type: ignore[union-attr]
            "item_code": item, "currency": currency,
            "contracted_net_price": str(net), "authorized_discount_pct": str(exp.approved_discount_pct),
            "unit_cost": str(cost.unit_cost), "cost_source": cost.source_record_id,
            "margin_pct": str(_pct(margin)), "target_margin_pct": str(target),
            "suggested_price": str(suggested), "billed_quantity_12m": str(qty),
            "indicative_annual_uplift": str(to_money((suggested - net) * qty)),
            "below_cost": net < cost.unit_cost,
        })
    found.sort(key=lambda o: Decimal(o["indicative_annual_uplift"]), reverse=True)
    return {
        "as_of": today.isoformat(), "target_margin_pct": str(target), "has_cost_data": bool(costs),
        "opportunities": found,
        "items_without_cost": [{"item_code": i, "currency": c} for i, c in sorted(missing)],
        "note": "Future pricing decisions for negotiation. Not billing errors; never counted as leakage or recovery.",
    }

"""The five first-release checks (BE-014..BE-018). Deterministic; confirmed terms only (GR-02, GR-03).

Each check returns a `Candidate` or None. Values are net of tax, in the record's own currency, and
never compared across currencies (FR-22). Only shortfalls count: billing *more* than the contract
permits is not revenue leakage.
"""

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.core.money import to_money
from app.domains.contracts.terms import TermBook
from app.domains.ingestion.models import Credit, InvoiceLine
from app.domains.matching.matcher import Bucket, OrgData, line_service_date, match_agreement
from app.domains.matching.pricing import HUNDRED, ZERO, expected_price, price
from app.domains.rules import evidence as ev
from app.domains.rules.evidence import s

# Most specific first: when several price checks fire on one line, the first one names the finding.
PRICE_SPECIFICITY = ("expired_discount", "missed_increase", "incorrect_rate")


@dataclass
class Candidate:
    family: str
    anchor_type: str
    anchor_id: str
    check_type: str
    value: Decimal
    currency: str
    confidence: str
    reason: str
    recommended_action: str
    calculation: dict[str, Any]
    evidence: dict[str, Any]
    customer_id: uuid.UUID | None
    agreement_id: uuid.UUID | None
    item_code: str | None
    period_start: date | None
    period_end: date | None
    also_detected_by: list[str] = field(default_factory=list)


@dataclass
class CheckContext:
    data: OrgData
    book: TermBook
    params: dict[str, Any]  # check_type -> typed params
    as_of: date
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def _plural(unit: str, qty: Decimal) -> str:
    """'hour' -> 'hours' unless the quantity is exactly 1 (display text only)."""
    return unit if qty == 1 or unit.endswith("s") else f"{unit}s"


def _fmt(d: Decimal) -> str:
    return s(d)


def _period_label(start: date, end: date) -> str:
    if start == end:
        return start.isoformat()
    if start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1] and start.month == end.month:
        return start.strftime("%B %Y")
    return f"{start.isoformat()} to {end.isoformat()}"


# ------------------------------------------------------------------ BE-014 delivered but not billed

def delivered_not_billed(ctx: CheckContext, b: Bucket) -> Candidate | None:
    p = ctx.params["delivered_not_billed"]
    missing = b.unbilled_quantity
    if missing <= 0:
        return None
    if b.agreement_id is None:
        ctx.skip("unbilled_without_agreement")
        return None
    due = (b.billing_due or b.period_end) + timedelta(days=p.grace_days)
    if ctx.as_of <= due:
        return None  # not yet late (grace period)
    on = max(e.service_date for e in b.events)
    expected = expected_price(ctx.book, b.agreement_id, b.item_code, on)
    if expected is None:
        ctx.skip("unbilled_without_rate")
        return None
    if expected.currency and expected.currency != b.currency:
        ctx.skip("currency_mismatch")
        return None
    unit_net = expected.net_unit(expected.approved_discount_pct)
    value = to_money(missing * unit_net)
    if value < p.min_value:
        return None

    unit = next((e.unit for e in b.events if e.unit), "units")
    period = _period_label(b.period_start, b.period_end)
    data = ctx.data
    return Candidate(
        family="unbilled", anchor_type="bucket", anchor_id=b.anchor(), check_type="delivered_not_billed",
        value=value, currency=b.currency, confidence="medium" if b.inferred else "high",
        reason=(f"{_fmt(missing)} {_plural(unit, missing)} of {b.item_code} delivered in {period} "
                f"{'was' if missing == 1 else 'were'} not invoiced "
                f"({_fmt(b.delivered)} delivered, {_fmt(b.billed)} billed) by {due.isoformat()}."),
        recommended_action=("Confirm the delivery records with the delivery owner, then raise a supplementary invoice "
                            "for the unbilled quantity at the contracted rate."),
        calculation={
            "formula": "(delivered − billed) × contracted net unit price",
            "inputs": {"delivered": _fmt(b.delivered), "billed": _fmt(b.billed), "unbilled": _fmt(missing),
                       "list_price": _fmt(expected.list_price),
                       "approved_discount_pct": _fmt(expected.approved_discount_pct),
                       "net_unit_price": _fmt(unit_net), "billing_due": s(b.billing_due),
                       "grace_days": p.grace_days, "as_of": s(ctx.as_of)},
            "result": _fmt(value),
        },
        evidence={
            "customer": ev.customer(data.customers[b.customer_id]),
            "agreement": ev.agreement(data.agreements.get(b.agreement_id)),
            "terms": [ev.term(t, ctx.book) for t in expected.terms()],
            "delivered": [ev.event(e) for e in sorted(b.events, key=lambda e: e.service_date)],
            "billed": [ev.line(ln, data.invoices[ln.invoice_id]) for ln in b.lines],
        },
        customer_id=b.customer_id, agreement_id=b.agreement_id, item_code=b.item_code,
        period_start=b.period_start, period_end=b.period_end,
    )


# ------------------------------------------------------------------ BE-015/016/017 price checks

def price_line(ctx: CheckContext, ln: InvoiceLine) -> Candidate | None:
    """Incorrect rate, expired/unauthorized discount and missed increase on one invoice line.

    The finding's value is the line's total shortfall against the contracted net price, so a line
    with two causes is counted once (FR-23). The most specific cause names the finding.
    """
    data = ctx.data
    inv = data.invoices[ln.invoice_id]
    on = line_service_date(ln, inv)
    match = match_agreement(data, ctx.book, inv.customer_id, ln.agreement_id, ln.item_code, on)
    if match.agreement_id is None:
        ctx.skip("line_without_agreement")
        return None
    expected = expected_price(ctx.book, match.agreement_id, ln.item_code, on)
    if expected is None:
        ctx.skip("line_without_rate")
        return None
    if expected.currency and expected.currency != inv.currency:
        ctx.skip("currency_mismatch")
        return None
    if ln.quantity <= 0:
        return None

    pr, pd, pm = ctx.params["incorrect_rate"], ctx.params["expired_discount"], ctx.params["missed_increase"]
    line_disc = ln.discount_pct or ZERO
    fired: list[str] = []
    if abs(ln.unit_price - expected.list_price) > pr.unit_price_tolerance:
        fired.append("incorrect_rate")
    if (expected.escalation_term is not None and expected.list_price != expected.base_rate
            and abs(ln.unit_price - expected.base_rate) <= pm.unit_price_tolerance):
        fired.append("missed_increase")
    if line_disc - expected.approved_discount_pct > pd.discount_tolerance_pct:
        fired.append("expired_discount")
    if not fired:
        return None

    expected_unit = expected.net_unit(line_disc)
    expected_total = to_money(expected_unit * ln.quantity)
    shortfall = to_money(expected_total - ln.net_amount)
    check_type = next(c for c in PRICE_SPECIFICITY if c in fired)
    min_value = ctx.params[check_type].min_value
    if shortfall < min_value:
        return None  # overbilled or within tolerance overall

    applied = min(line_disc, expected.approved_discount_pct)
    rate_component = to_money((expected.list_price - ln.unit_price) * ln.quantity * (1 - applied / HUNDRED))
    discount_component = to_money(ln.unit_price * ln.quantity * max(line_disc - expected.approved_discount_pct, ZERO)
                                  / HUNDRED)
    unit = ln.item_code
    if check_type == "expired_discount":
        d = expected.discount_term
        why = (f"the discount term {d.source_record_id or ''} allows {_fmt(d.value)}% on {on.isoformat()}"
               if d is not None else f"no discount is authorized on {on.isoformat()}")
        reason = (f"Invoice {inv.number} applied a {_fmt(line_disc)}% discount to {_fmt(ln.quantity)} × {unit}, "
                  f"but {why}.")
        action = ("Check whether the discount was re-approved. If not, invoice the customer for the over-applied "
                  "discount and correct the discount in the billing system.")
    elif check_type == "missed_increase":
        esc = expected.escalation_term
        assert esc is not None
        reason = (f"Invoice {inv.number} billed {unit} at the pre-increase rate {_fmt(ln.unit_price)}; the "
                  f"{_fmt(esc.value)}{'%' if esc.unit != 'rate' else ''} increase effective "
                  f"{esc.effective_from.isoformat()} makes the contracted rate {_fmt(expected.list_price)}.")
        action = ("Update the price in the billing system from the escalation date and invoice the difference for "
                  "affected periods.")
    else:
        reason = (f"Invoice {inv.number} billed {unit} at {_fmt(ln.unit_price)} per unit; the contracted rate on "
                  f"{on.isoformat()} is {_fmt(expected.list_price)}.")
        action = ("Confirm the contracted rate with the commercial manager and prepare a supplementary invoice for "
                  "the difference.")

    return Candidate(
        family="price", anchor_type="invoice_line", anchor_id=str(ln.id), check_type=check_type,
        also_detected_by=[c for c in PRICE_SPECIFICITY if c in fired and c != check_type],
        value=shortfall, currency=inv.currency, confidence="medium" if match.inferred else "high",
        reason=reason, recommended_action=action,
        calculation={
            "formula": "expected net amount − billed net amount; expected = list price × (1 − authorized discount) × qty",
            "inputs": {"quantity": _fmt(ln.quantity), "billed_unit_price": _fmt(ln.unit_price),
                       "billed_discount_pct": _fmt(line_disc), "billed_net_amount": _fmt(ln.net_amount),
                       "contracted_base_rate": _fmt(expected.base_rate),
                       "contracted_list_price": _fmt(expected.list_price),
                       "approved_discount_pct": _fmt(expected.approved_discount_pct),
                       "expected_net_unit_price": _fmt(price(expected_unit)),
                       "expected_net_amount": _fmt(expected_total), "service_date": s(on)},
            "components": {"rate": _fmt(rate_component), "discount": _fmt(discount_component)},
            "result": _fmt(shortfall),
        },
        evidence={
            "customer": ev.customer(data.customers[inv.customer_id]),
            "agreement": ev.agreement(data.agreements.get(match.agreement_id)),
            "terms": [ev.term(t, ctx.book) for t in expected.terms()],
            "delivered": [],
            "billed": [ev.line(ln, inv)],
        },
        customer_id=inv.customer_id, agreement_id=match.agreement_id, item_code=ln.item_code,
        period_start=ln.service_period_start or inv.invoice_date, period_end=ln.service_period_end or inv.invoice_date,
    )


# ------------------------------------------------------------------ BE-018 credit outside policy

def _credit_agreement(ctx: CheckContext, c: Credit) -> uuid.UUID | None:
    data = ctx.data
    if c.invoice_id is not None:
        explicit = {ln.agreement_id for ln in data.lines_by_invoice.get(c.invoice_id, []) if ln.agreement_id}
        if len(explicit) == 1:
            return explicit.pop()
    own = data.agreements_by_customer.get(c.customer_id, [])
    return own[0].id if len(own) == 1 else None


def credit_outside_policy(ctx: CheckContext, c: Credit) -> Candidate | None:
    p = ctx.params["credit_outside_policy"]
    agreement_id = _credit_agreement(ctx, c)
    policy = ctx.book.first(agreement_id, c.credit_date, "credit_policy") if agreement_id else None
    threshold = policy.value if policy is not None else p.default_approval_threshold
    max_value = (Decimal(policy.params["max_value"]) if policy is not None and policy.params.get("max_value")
                 else (None if policy is not None else p.default_max_credit))
    comparable = policy is None or policy.currency in (None, c.currency)
    if not comparable:
        ctx.skip("currency_mismatch")

    violations: list[tuple[str, Decimal]] = []
    if p.require_reason_code and not (c.reason_code or "").strip():
        violations.append(("has no reason code", c.amount))
    if comparable and threshold is not None and c.amount > threshold and not (c.approval_ref or "").strip():
        violations.append((f"exceeds the {_fmt(threshold)} approval threshold without an approval reference", c.amount))
    if comparable and max_value is not None and c.amount > max_value:
        excess = c.amount - max_value if (c.approval_ref or "").strip() else c.amount
        violations.append((f"exceeds the {_fmt(max_value)} maximum credit", excess))
    if not violations:
        return None
    value = to_money(max(v for _, v in violations))
    data = ctx.data
    inv = data.invoices.get(c.invoice_id) if c.invoice_id else None
    return Candidate(
        family="credit", anchor_type="credit", anchor_id=str(c.id), check_type="credit_outside_policy",
        value=value, currency=c.currency, confidence="high" if policy is not None else "medium",
        reason=f"Credit {c.source_record_id or ''} of {_fmt(c.amount)} {c.currency} " + "; ".join(v for v, _ in violations) + ".",
        recommended_action=("Obtain the missing approval or reason from the credit's owner; if it can't be justified, "
                            "reverse the credit and invoice the amount."),
        calculation={
            "formula": "credit amount at risk under the credit policy",
            "inputs": {"amount": _fmt(c.amount), "reason_code": c.reason_code, "approval_ref": c.approval_ref,
                       "approval_threshold": s(threshold), "max_credit": s(max_value),
                       "policy_source": "credit_policy term" if policy is not None else "rule defaults"},
            "violations": [v for v, _ in violations],
            "result": _fmt(value),
        },
        evidence={
            "customer": ev.customer(data.customers[c.customer_id]),
            "agreement": ev.agreement(data.agreements.get(agreement_id)) if agreement_id else None,
            "terms": [ev.term(policy, ctx.book)] if policy is not None else [],
            "delivered": [],
            "billed": [ev.line(ln, inv) for ln in data.lines_by_invoice.get(inv.id, [])] if inv else [],
            "credit": ev.credit(c, inv),
        },
        customer_id=c.customer_id, agreement_id=agreement_id, item_code=None,
        period_start=c.credit_date, period_end=c.credit_date,
    )

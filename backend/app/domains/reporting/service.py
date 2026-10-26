"""Outcome figures, monthly trend and recurring root causes (BE-025, FR-32, GR-04, GR-05).

The six figures are computed independently from their own source, never derived from one another
(design §2.5), and kept per currency (no FX, FR-22):

    potential leakage        Σ value of findings open / in_review / proposed
    confirmed leakage        Σ value of findings approved / billed / recovered / closed_no_recovery
    corrected billing        Σ billed recovery events (net invoice lines carrying a correction reference)
    cash recovered           Σ per correction of min(payments to its invoices, correction amount)
    prevented recurrence     estimate from BE-024 (zero until recurrence tracking lands in M5)
    closed without recovery  Σ value of findings written off

Rejected findings appear only as a count, never in a money figure (GR-05).
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.domains.cases.models import Correction
from app.domains.recovery.models import RecoveryEvent
from app.domains.rules.models import Finding

ZERO = Decimal("0")
POTENTIAL = ("open", "in_review", "proposed")
CONFIRMED = ("approved", "billed", "recovered", "closed_no_recovery")
FIGURES = ("potential", "confirmed", "corrected_billing", "cash_recovered", "prevented_recurrence",
           "closed_without_recovery")


def _months_back(today: date, n: int) -> list[str]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return list(reversed(out))


def outcomes(session: Session, org_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    figures: dict[str, dict[str, Decimal]] = defaultdict(lambda: {k: ZERO for k in FIGURES})

    for status, currency, total in session.execute(
        select(Finding.status, Finding.currency, func.sum(Finding.value))
        .where(Finding.org_id == org_id).group_by(Finding.status, Finding.currency)
    ):
        if status in POTENTIAL:
            figures[currency]["potential"] += total
        if status in CONFIRMED:
            figures[currency]["confirmed"] += total
        if status == "closed_no_recovery":
            figures[currency]["closed_without_recovery"] += total

    # Corrected billing and cash, walked per correction so cash is capped at the correction amount (GR-04).
    recovered_by_month: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    corrections = {c.id: c for c in session.scalars(select(Correction).where(Correction.org_id == org_id))}
    events = session.scalars(select(RecoveryEvent).where(RecoveryEvent.org_id == org_id)
                             .order_by(RecoveryEvent.occurred_on, RecoveryEvent.created_at)).all()
    remaining = {cid: c.amount for cid, c in corrections.items()}
    for e in events:
        c = corrections[e.correction_id]
        if e.kind == "billed":
            figures[c.currency]["corrected_billing"] += e.amount
        else:
            counted = min(e.amount, remaining[c.id])
            remaining[c.id] -= counted
            figures[c.currency]["cash_recovered"] += counted
            recovered_by_month[(e.occurred_on.strftime("%Y-%m"), c.currency)] += counted

    counts = dict(session.execute(select(Finding.status, func.count()).where(Finding.org_id == org_id)
                                  .group_by(Finding.status)).all())

    # Trend: leakage identified by the month it happened (excluding rejected), and cash recovered by month.
    months = _months_back(today, 12)
    identified: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    # Literal format so SELECT and GROUP BY are the same expression (bound parameters would differ).
    month_expr = func.to_char(Finding.period_start, literal_column("'YYYY-MM'"))
    for month, currency, total in session.execute(
        select(month_expr, Finding.currency, func.sum(Finding.value))
        .where(Finding.org_id == org_id, Finding.status != "rejected", Finding.period_start.is_not(None))
        .group_by(month_expr, Finding.currency)
    ):
        identified[(month, currency)] += total
    currencies = sorted(set(figures) | {c for _, c in identified} | {c for _, c in recovered_by_month})
    trend = [{"month": m, "currency": ccy, "identified": identified[(m, ccy)], "recovered": recovered_by_month[(m, ccy)]}
             for ccy in currencies for m in months]

    causes = session.execute(
        select(Finding.root_cause_category, Finding.currency, func.count(), func.sum(Finding.value))
        .where(Finding.org_id == org_id, Finding.root_cause_category.is_not(None), Finding.status != "rejected")
        .group_by(Finding.root_cause_category, Finding.currency)
        .order_by(func.sum(Finding.value).desc()).limit(5)
    ).all()

    return {
        "currencies": [{"currency": ccy, **figures[ccy]} for ccy in currencies],
        "counts": {
            "open": sum(counts.get(s, 0) for s in POTENTIAL),
            "awaiting_approval": counts.get("proposed", 0),
            "in_recovery": counts.get("approved", 0) + counts.get("billed", 0),
            "recovered": counts.get("recovered", 0),
            "rejected": counts.get("rejected", 0),
            "total": sum(counts.values()),
        },
        "trend": trend,
        "root_causes": [{"category": cat, "currency": ccy, "count": n, "value": v} for cat, ccy, n, v in causes],
        "notes": {"prevented_recurrence": "Estimate from recurrence tracking (BE-024, milestone M5); zero until then."},
    }

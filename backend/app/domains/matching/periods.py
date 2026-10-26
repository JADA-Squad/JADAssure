"""Billing periods by agreement billing frequency (design §3.4)."""

import calendar
from datetime import date


def period_for(frequency: str, on: date) -> tuple[date, date]:
    if frequency == "monthly":
        return on.replace(day=1), on.replace(day=calendar.monthrange(on.year, on.month)[1])
    if frequency == "quarterly":
        first_month = 3 * ((on.month - 1) // 3) + 1
        last_month = first_month + 2
        return date(on.year, first_month, 1), date(on.year, last_month, calendar.monthrange(on.year, last_month)[1])
    if frequency == "annual":
        return date(on.year, 1, 1), date(on.year, 12, 31)
    if frequency in ("per_event", "milestone"):
        return on, on
    raise ValueError(f"unknown billing frequency {frequency!r}")

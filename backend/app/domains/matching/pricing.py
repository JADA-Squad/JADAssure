"""Expected contracted price for an item on a date, from confirmed terms only (GR-03, GR-09)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from app.core.money import PRICE_PLACES
from app.domains.contracts.models import CommercialTerm
from app.domains.contracts.terms import TermBook

HUNDRED = Decimal("100")
ZERO = Decimal("0")


def price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_PLACES, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class ExpectedPrice:
    rate_term: CommercialTerm
    escalation_term: CommercialTerm | None
    discount_term: CommercialTerm | None
    base_rate: Decimal  # contracted rate before escalation
    list_price: Decimal  # rate after any escalation in effect
    approved_discount_pct: Decimal  # maximum authorized discount in effect (0 if none)

    @property
    def currency(self) -> str | None:
        return self.rate_term.currency

    def net_unit(self, applied_discount_pct: Decimal) -> Decimal:
        """Expected net unit price when the customer receives `applied_discount_pct` (capped at the approved max)."""
        allowed = min(applied_discount_pct, self.approved_discount_pct)
        return price(self.list_price * (1 - allowed / HUNDRED))

    def terms(self) -> list[CommercialTerm]:
        return [t for t in (self.rate_term, self.escalation_term, self.discount_term) if t is not None]


def expected_price(book: TermBook, agreement_id: uuid.UUID, item_code: str, on: date) -> ExpectedPrice | None:
    rate = book.first(agreement_id, on, "rate", item_code)
    if rate is None:
        return None
    escalation = book.first(agreement_id, on, "escalation", item_code)
    discount = book.first(agreement_id, on, "discount", item_code)
    list_price = rate.value
    if escalation is not None:
        list_price = escalation.value if escalation.unit == "rate" else rate.value * (1 + escalation.value / HUNDRED)
    return ExpectedPrice(
        rate_term=rate,
        escalation_term=escalation,
        discount_term=discount,
        base_rate=price(rate.value),
        list_price=price(list_price),
        approved_discount_pct=discount.value if discount is not None else ZERO,
    )

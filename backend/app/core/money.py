"""Exact decimal money (GR-09, decision 0001 D-9). A float touching money is a bug."""

from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import Numeric

# Column types
Money = Numeric(19, 4, asdecimal=True)
Quantity = Numeric(19, 6, asdecimal=True)
UnitPrice = Numeric(19, 6, asdecimal=True)

MONEY_PLACES = Decimal("0.0001")
PRICE_PLACES = Decimal("0.000001")


def to_money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"money must be Decimal, got {type(value).__name__}")
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_EVEN)

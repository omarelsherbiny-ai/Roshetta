# server/app/db/money.py
"""Money handling (debt 6, Session 113).

Storage is exact (``NUMERIC``), the Python side and the API stay plain floats, so
the web client and the contract do not change. Rounding is always half-up on the
decimal text of the number, never Python's ``round`` (which rounds 10.005 down).

* ``Money`` is the column type (``Money()`` = 12 digits, 2 places; ``Money(16, 2)``
  for totals; ``Money(14, 6)`` for the weighted unit cost snapshot).
* ``round_money`` / ``money_sum`` are the only rounding helpers code should use.
* ``MoneyIn`` is the request-body type: it rounds to 2 places before the
  ``gt`` / ``ge`` / ``le`` checks run, so 0.004 can never pass ``gt=0`` and then
  be stored as 0.00.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Annotated, Iterable, Optional

from pydantic import BeforeValidator
from sqlalchemy import Numeric
from sqlalchemy.types import TypeDecorator


def _quantum(places: int) -> Decimal:
    return Decimal(1).scaleb(-places)


def to_decimal(value, places: int = 2) -> Decimal:
    """Exact half-up rounding of a float, int, str or Decimal to ``places``."""
    if isinstance(value, Decimal):
        number = value
    else:
        # str(float) is the shortest text that round-trips, so 10.005 stays 10.005.
        number = Decimal(str(value))
    return number.quantize(_quantum(places), rounding=ROUND_HALF_UP)


def round_money(value, places: int = 2):
    """Float rounded half-up to ``places``; ``None`` stays ``None``."""
    if value is None:
        return None
    return float(to_decimal(value, places))


def money_sum(values: Iterable, places: int = 2) -> float:
    """Exact sum of the values (each taken at 2 places first), returned as a float."""
    total = Decimal(0)
    for value in values:
        if value is not None:
            total += to_decimal(value, places)
    return float(total.quantize(_quantum(places), rounding=ROUND_HALF_UP))


class Money(TypeDecorator):
    """NUMERIC column that rounds on the way in and hands back floats on the way out."""

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 12, scale: int = 2):
        self.precision = precision
        self.scale = scale
        super().__init__(precision, scale, asdecimal=False)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return to_decimal(value, self.scale)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return round_money(value, self.scale)


def _round_input(value):
    """BeforeValidator: round numbers to 2 places and leave anything else to pydantic."""
    if value is None or isinstance(value, bool):
        return value
    try:
        number = to_decimal(value, 2)
    except (InvalidOperation, ValueError, TypeError):
        return value  # not a number: pydantic produces the normal error
    if not number.is_finite():
        return value  # NaN / inf: rejected by allow_inf_nan=False
    return float(number)


# Use as ``unit_price: MoneyIn = Field(ge=0, le=100_000_000, allow_inf_nan=False)``
# or ``Optional[MoneyIn] = Field(default=None, ...)``.
MoneyIn = Annotated[float, BeforeValidator(_round_input)]
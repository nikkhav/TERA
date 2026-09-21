"""Standalone conversion with supplied, dated rates; no API or network access."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Union

DecimalInput = Union[Decimal, str, int]


def _decimal(value: DecimalInput) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
        raise TypeError("Use Decimal, a decimal string, or an integer; floats are not supported")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Amounts and rates must be finite")
    return result


def _currency(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Currency code must be a string")
    value = value.strip().upper()
    if len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError("Currency code must contain three ASCII letters")
    return value


@dataclass(frozen=True)
class ExchangeRate:
    """Target currency units per one source unit, as of a specified date.

    Codes are checked for syntax only. A future caller/API adapter is responsible
    for supported currencies, rate availability, and choosing the appropriate date.
    """

    source_currency: str
    target_currency: str
    rate: DecimalInput
    as_of: date
    source: str = "manual"

    def __post_init__(self) -> None:
        source_currency = _currency(self.source_currency)
        target_currency = _currency(self.target_currency)
        rate = _decimal(self.rate)
        if rate <= 0:
            raise ValueError("Exchange rate must be positive")
        if source_currency == target_currency and rate != 1:
            raise ValueError("A same-currency rate must equal 1")
        if type(self.as_of) is not date:
            raise TypeError("as_of must be a calendar date")
        object.__setattr__(self, "source_currency", source_currency)
        object.__setattr__(self, "target_currency", target_currency)
        object.__setattr__(self, "rate", rate)


def convert_amount(
    amount: DecimalInput,
    exchange_rate: ExchangeRate,
    *,
    decimal_places: int = 2,
) -> Decimal:
    """Convert a source-currency amount; round once in the target currency.

    Negative amounts represent refunds. Supply decimal_places explicitly for
    currencies such as JPY (0) or KWD (3); no currency metadata is fetched.
    """
    amount = _decimal(amount)
    if type(decimal_places) is not int or not 0 <= decimal_places <= 6:
        raise ValueError("decimal_places must be an integer between 0 and 6")
    quantum = Decimal(1).scaleb(-decimal_places)
    with localcontext() as context:
        # Preserve multiplication precision before rounding the final amount.
        context.prec = max(
            28,
            len(amount.as_tuple().digits) + len(exchange_rate.rate.as_tuple().digits),
            amount.adjusted() + exchange_rate.rate.adjusted() + decimal_places + 3,
        )
        return (amount * exchange_rate.rate).quantize(quantum, rounding=ROUND_HALF_UP)

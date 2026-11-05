"""Exact nonnegative minor-unit amounts; no implicit rounding or currency conversion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ValidationFailure

MAX_MINOR_UNITS = 2**63 - 1
_CURRENCY = re.compile(r'[A-Z][A-Z0-9]{2,11}\Z')
_DECIMAL = re.compile(r'(0|[1-9][0-9]*)(?:\.([0-9]+))?\Z')


@dataclass(frozen=True, slots=True)
class Money:
    minor_units: int
    currency: str
    exponent: int

    def __post_init__(self) -> None:
        if type(self.minor_units) is not int or not 0 <= self.minor_units <= MAX_MINOR_UNITS:
            raise ValidationFailure('Use exact nonnegative minor units within SQLite integer bounds')
        if not isinstance(self.currency, str) or _CURRENCY.fullmatch(self.currency) is None:
            raise ValidationFailure('Use a bounded uppercase ASCII currency code')
        if type(self.exponent) is not int or not 0 <= self.exponent <= 18:
            raise ValidationFailure('Use a currency exponent between zero and eighteen')
        if self.currency == 'XTR' and self.exponent != 0:
            raise ValidationFailure('Telegram Stars use whole XTR units')

    @classmethod
    def from_decimal(cls, text: str, currency: str, exponent: int) -> Money:
        """Parse a canonical decimal string exactly; excess precision is rejected, never rounded."""
        cls(0, currency, exponent)
        match = _DECIMAL.fullmatch(text) if isinstance(text, str) and len(text) <= 64 else None
        if match is None:
            raise ValidationFailure('Use a bounded canonical nonnegative decimal string')
        whole, fraction = match.group(1), match.group(2) or ''
        if len(fraction) > exponent:
            raise ValidationFailure('Decimal amount exceeds the currency exponent')
        return cls(int(whole) * 10**exponent + int(fraction.ljust(exponent, '0') or '0'), currency, exponent)

    def to_decimal(self) -> str:
        if self.exponent == 0:
            return str(self.minor_units)
        digits = str(self.minor_units).zfill(self.exponent + 1)
        return digits[: -self.exponent] + '.' + digits[-self.exponent :]

    def _compatible(self, other: Money) -> None:
        if not isinstance(other, Money) or (self.currency, self.exponent) != (other.currency, other.exponent):
            raise ValidationFailure('Money arithmetic requires the same currency and exponent')

    def __add__(self, other: Money) -> Money:
        self._compatible(other)
        return Money(self.minor_units + other.minor_units, self.currency, self.exponent)

    def __sub__(self, other: Money) -> Money:
        self._compatible(other)
        return Money(self.minor_units - other.minor_units, self.currency, self.exponent)

"""Exact money boundaries and conversion without floating point or decimal-context rounding."""

import decimal
import unittest

from telegram_patterns.errors import ValidationFailure
from telegram_patterns.money import MAX_MINOR_UNITS, Money


class MoneyTests(unittest.TestCase):
    def test_decimal_parsing_is_exact_even_with_a_tiny_decimal_context(self):
        with decimal.localcontext() as context:
            context.prec = 1
            amount = Money.from_decimal('92233720368.54775807', 'USD', 8)
            self.assertEqual(amount.minor_units, 9223372036854775807)
            self.assertEqual(amount.to_decimal(), '92233720368.54775807')
            self.assertEqual(Money.from_decimal('0.000000000000000001', 'TEST', 18).minor_units, 1)
        self.assertEqual(Money.from_decimal('1.5', 'USD', 2), Money(150, 'USD', 2))
        self.assertEqual(Money(0, 'USD', 2).to_decimal(), '0.00')
        self.assertEqual(Money(100, 'XTR', 0).to_decimal(), '100')

    def test_arithmetic_preserves_currency_exponent_and_integer_bounds(self):
        self.assertEqual(Money(1, 'USD', 2) + Money(2, 'USD', 2), Money(3, 'USD', 2))
        self.assertEqual(Money(3, 'USD', 2) - Money(3, 'USD', 2), Money(0, 'USD', 2))
        for action in [
            lambda: Money(MAX_MINOR_UNITS, 'USD', 2) + Money(1, 'USD', 2),
            lambda: Money(0, 'USD', 2) - Money(1, 'USD', 2),
            lambda: Money(1, 'USD', 2) + Money(1, 'EUR', 2),
            lambda: Money(1, 'USD', 2) + Money(1, 'USD', 3),
            lambda: Money(1, 'USD', 2) + 1,
        ]:
            with self.assertRaises(ValidationFailure):
                action()

    def test_float_bool_negative_overflow_and_unsupported_precision_are_rejected(self):
        for value in [1.0, True, -1, MAX_MINOR_UNITS + 1, decimal.Decimal('1')]:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValidationFailure):
                Money(value, 'USD', 2)
        for currency, exponent in [
            ('usd', 2),
            ('US', 2),
            ('USD ', 2),
            ('USD\n', 2),
            ('РУБ', 2),
            ('USD', True),
            ('USD', -1),
            ('USD', 19),
            ('XTR', 2),
        ]:
            with self.subTest(exponent=exponent), self.assertRaises(ValidationFailure):
                Money(1, currency, exponent)
        for case, value in enumerate(
            ['1e3', '+1', '-1', '01', ' 1', '1.', '.1', '1.001', '1.000', 'NaN', 'Infinity', '1,50', 1.5, '1' * 65]
        ):
            with self.subTest(case=case), self.assertRaises(ValidationFailure):
                Money.from_decimal(value, 'USD', 2)


if __name__ == '__main__':
    unittest.main()

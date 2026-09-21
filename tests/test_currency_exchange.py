import unittest
from datetime import date
from decimal import Decimal

from currency_exchange import ExchangeRate, convert_amount


class CurrencyConversionTests(unittest.TestCase):
    def rate(self, value="0.90", target="EUR"):
        return ExchangeRate("USD", target, value, date(2026, 9, 18))

    def test_rate_direction_and_currency_normalization(self):
        rate = ExchangeRate(" usd ", "eur", "0.90", date(2026, 9, 18))
        self.assertEqual((rate.source_currency, rate.target_currency), ("USD", "EUR"))
        self.assertEqual(convert_amount("100.00", rate), Decimal("90.00"))

    def test_rounding_and_refunds(self):
        self.assertEqual(convert_amount("1.005", self.rate("1")), Decimal("1.01"))
        self.assertEqual(convert_amount("-1.005", self.rate("1")), Decimal("-1.01"))
        self.assertEqual(convert_amount("0", self.rate()), Decimal("0.00"))

    def test_target_currency_precision(self):
        self.assertEqual(convert_amount("1", self.rate("150.5", "JPY"), decimal_places=0), Decimal("151"))
        self.assertEqual(convert_amount("1", self.rate("0.3075", "KWD"), decimal_places=3), Decimal("0.308"))

    def test_invalid_rates_and_amounts(self):
        for rate in ("0", "-1", "NaN", "Infinity"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                self.rate(rate)
        for amount in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                convert_amount(amount, self.rate())
        with self.assertRaises(TypeError):
            convert_amount(0.1, self.rate())
        with self.assertRaises(TypeError):
            self.rate(0.9)

    def test_same_currency(self):
        with self.assertRaises(ValueError):
            self.rate("2", "USD")
        self.assertEqual(convert_amount("15.50", self.rate("1", "USD")), Decimal("15.50"))

    def test_invalid_metadata(self):
        with self.assertRaises(ValueError):
            self.rate(target="EURO")
        with self.assertRaises(TypeError):
            ExchangeRate("USD", "EUR", "1", "2026-09-18")
        for places in (-1, 1.5, True):
            with self.subTest(places=places), self.assertRaises(ValueError):
                convert_amount("1", self.rate(), decimal_places=places)


if __name__ == "__main__":
    unittest.main()

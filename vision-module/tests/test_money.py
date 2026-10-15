import unittest
from decimal import Decimal

from vision_engine.currency import detect_currency
from vision_engine.money import parse_money, reconcile


class MoneyTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_money('EUR 1,234.56'), Decimal('1234.56'))
        self.assertEqual(parse_money('S/ 1.234,56', ','), Decimal('1234.56'))
        self.assertEqual(parse_money('0.00'), Decimal('0.00'))

    def test_ambiguous_and_missing_never_become_zero(self):
        for text in ('', '12.3', '10.00 20.00', '1,23.45', '1.234.56', 'EUR'):
            with self.assertRaises(ValueError):
                parse_money(text)

    def test_invalid_separator(self):
        with self.assertRaises(ValueError):
            parse_money('1.00', ';')

    def test_reconciliation(self):
        self.assertTrue(reconcile(Decimal('10'), Decimal('.20'), Decimal('0'), Decimal('9.80')))
        self.assertFalse(reconcile(Decimal('10'), Decimal('.20'), Decimal('0'), Decimal('10')))

    def test_reconciliation_rejects_float(self):
        with self.assertRaises(TypeError):
            reconcile(10.0, Decimal('1'), Decimal('0'), Decimal('9'))


class CurrencyTests(unittest.TestCase):
    def test_markers(self):
        self.assertEqual(detect_currency('EUR'), 'EUR')
        self.assertEqual(detect_currency('€'), 'EUR')
        self.assertEqual(detect_currency('PEN'), 'PEN')
        self.assertEqual(detect_currency('S/ 10.00'), 'PEN')
        self.assertEqual(detect_currency('USD'), 'USD')

    def test_illegible_or_ambiguous(self):
        for text in ('', 'E0R', 'EUR PEN', '10.00'):
            with self.assertRaises(ValueError):
                detect_currency(text)

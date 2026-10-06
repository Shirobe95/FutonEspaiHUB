"""C3: lectura de importes (regla acordada con Futón Espai)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.core.money import describe_amount_interpretation, is_ambiguous_amount, parse_amount  # noqa: E402


class ParseAmountTests(unittest.TestCase):
    def test_agreed_rule(self) -> None:
        cases = {
            "1.250": 1250.0, "1.25": 1.25, "1,25": 1.25, "12.5": 12.5, "100": 100.0, "0": 0.0,
            "1.234,56": 1234.56, "1,234.56": 1234.56, "1.234.567": 1234567.0, "1,234,567": 1234567.0,
            "0.250": 0.25, "0,350": 0.35, "1250.00": 1250.0, "1250.5": 1250.5, "1250.500": 1250.5,
            "-5.5": -5.5, " 71.00 ": 71.0, "71,00 EUR": 71.0, "€ 1.250,00": 1250.0, "$99.99": 99.99,
        }
        for text, expected in cases.items():
            self.assertEqual(parse_amount(text), expected, text)

    def test_numbers_pass_through(self) -> None:
        self.assertEqual(parse_amount(3), 3.0)
        self.assertEqual(parse_amount(1.25), 1.25)

    def test_not_amounts(self) -> None:
        for bad in (None, "", "  ", "abc", "nan", "inf", "-inf", "Infinity", "1.2.3x", "1..2", True, float("nan")):
            self.assertIsNone(parse_amount(bad), repr(bad))

    def test_only_n_dot_nnn_is_flagged_as_ambiguous(self) -> None:
        self.assertTrue(is_ambiguous_amount("1.250"))
        self.assertTrue(is_ambiguous_amount("12.500"))
        for text in ("1.25", "0.250", "1250.500", "1,250", "1.234,56", "100", "1.234.567", None):
            self.assertFalse(is_ambiguous_amount(text), text)

    def test_note_says_how_it_was_read(self) -> None:
        note = describe_amount_interpretation("1.250")
        self.assertIn("1.250,00", note)
        self.assertIn("miles", note)
        self.assertIsNone(describe_amount_interpretation("1.25"))


if __name__ == "__main__":
    unittest.main()

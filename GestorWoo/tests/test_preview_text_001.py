"""U7: '3 -> 5' no puede mostrarse como '35'; valores None no rompen el preview."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp.preview_text import format_change, format_quantity, format_reception_line  # noqa: E402


class PreviewTextTests(unittest.TestCase):
    def test_change_has_visible_separator(self) -> None:
        self.assertEqual(format_change(3, 5), "3 -> 5")
        self.assertNotEqual(format_change(3.0, 5.0), "35")

    def test_quantities_are_compact_and_tolerate_missing_values(self) -> None:
        self.assertEqual(format_quantity(12.0), "12")
        self.assertEqual(format_quantity("2.5"), "2.5")
        self.assertEqual(format_quantity(None), "-")
        self.assertEqual(format_quantity("x"), "-")

    def test_reception_line_keeps_store_and_warehouse_separate(self) -> None:
        text = format_reception_line({
            "item_code": "A1", "item_name": "Futon", "quantity_received_now": 2,
            "store_stock_before": 3, "store_stock_after": 5,
            "warehouse_stock_before": 10, "warehouse_stock_after": None,
        })
        self.assertIn("Stock tienda 3 -> 5", text)
        self.assertIn("almacen 10 -> -", text)
        self.assertIn("+2", text)


if __name__ == "__main__":
    unittest.main()

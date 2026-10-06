"""D9: ``packages`` es integer en Supabase; la edición no puede enviar 3.0."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.audit import CloudAuditError
from futonhub.cloud.services import inventory as inv


class PackagesIntegerTests(unittest.TestCase):
    def test_packages_is_sent_as_int(self) -> None:
        for raw in ("3", "3.0", "3,0", 3, 3.0):
            value = inv._normalize_inventory_edit_value("packages", raw)
            self.assertEqual(value, 3, raw)
            self.assertIsInstance(value, int, raw)

    def test_fractional_packages_are_rejected_before_reaching_supabase(self) -> None:
        with self.assertRaises(CloudAuditError):
            inv._normalize_inventory_edit_value("packages", "2.5")

    def test_empty_packages_stay_none(self) -> None:
        self.assertIsNone(inv._normalize_inventory_edit_value("packages", ""))

    def test_stock_and_money_fields_keep_decimals(self) -> None:
        self.assertEqual(inv._normalize_inventory_edit_value("store_stock", "2,5"), 2.5)
        self.assertIsInstance(inv._normalize_inventory_edit_value("cubic_meters", "0.35"), float)

    def test_preview_payload_uses_int_for_packages(self) -> None:
        before = {"item_id": 7, "name": "x", "packages": 2}
        original = inv._fetch_inventory_item_by_id
        inv._fetch_inventory_item_by_id = lambda session, item_id: dict(before)
        try:
            preview = inv.preview_inventory_item_field_update(object(), 7, {"packages": "3"})
        finally:
            inv._fetch_inventory_item_by_id = original
        change = [r for r in preview["changes"] if r["field"] == "packages"][0]
        self.assertEqual(change["after"], 3)
        self.assertIsInstance(change["after"], int)


if __name__ == "__main__":
    unittest.main()

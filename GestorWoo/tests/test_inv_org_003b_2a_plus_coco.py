from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    PhysicalCatalogSnapshot,
    normalize_physical_code_comparison_key,
)


PLUS_COCO_CODES = ("0759003", "0759004", "0759005", "0759006", "0759007", "0759008", "0759009", "0759010")
PLUS_COCO_SIZES = {
    "90x200x14", "120x200x14", "140x190x14", "140x200x14",
    "150x200x14", "160x200x14", "180x200x14", "200x200x14",
}


class InvOrg003B2APlusCocoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = PhysicalCatalogSnapshot.load()
        cls.rows_by_code = {
            row.get("heca_reference"): row
            for row in cls.snapshot.rows_by_item_id.values()
            if row.get("heca_reference") in PLUS_COCO_CODES
        }

    def test_six_new_plus_coco_rows_remain_eligible_with_254_total(self) -> None:
        self.assertEqual(self.snapshot.expected_count, 254)
        self.assertEqual(len(self.snapshot.item_ids), 254)
        self.assertEqual(set(self.rows_by_code), set(PLUS_COCO_CODES))
        for code in PLUS_COCO_CODES[2:]:
            self.assertIn(code, self.rows_by_code)

    def test_plus_coco_has_eight_complete_hierarchy_rows_and_no_14_5(self) -> None:
        self.assertEqual({row["size"] for row in self.rows_by_code.values()}, PLUS_COCO_SIZES)
        for row in self.rows_by_code.values():
            self.assertEqual(row["filter_family"], "Futones")
            self.assertEqual(row["filter_group"], "Plus Coco")
            self.assertEqual(row["filter_size"], row["size"])
            self.assertEqual(row["filter_gama"], "NO_GAMA")
            self.assertNotIn("14,5", row["size"])
            self.assertNotIn("14,5", row["filter_size"])

    def test_leading_zero_key_is_stable_and_alphanumeric_codes_are_not_coerced(self) -> None:
        self.assertEqual(normalize_physical_code_comparison_key("302018"), "302018")
        self.assertEqual(normalize_physical_code_comparison_key("0302018"), "302018")
        self.assertEqual(normalize_physical_code_comparison_key("0302018A"), "0302018A")
        self.assertEqual(normalize_physical_code_comparison_key("AB001"), "AB001")

    def test_approved_leading_zero_identity_resolves_without_changing_visible_code(self) -> None:
        row, strategy = self.snapshot.resolve_price_row({"item_id": "unmapped", "heca_reference": "302018"})
        self.assertIsNotNone(row)
        self.assertEqual(row["item_id"], "302018")
        self.assertEqual(row["heca_reference"], "0302018")
        self.assertEqual(strategy, "approved_leading_zero_heca_reference")

    def test_additional_differences_do_not_create_an_automatic_merge(self) -> None:
        row, strategy = self.snapshot.resolve_price_row({"item_id": "unmapped", "heca_reference": "0302018A"})
        self.assertIsNone(row)
        self.assertEqual(strategy, "unmapped")


if __name__ == "__main__":
    unittest.main()

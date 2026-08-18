from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.core.codes import supplier_order_eligibility_reason  # noqa: E402
from futonhub.services.catalog_operational_baseline import CatalogOperationalBaseline  # noqa: E402
from futonhub.services.inventory_visibility import InventoryVisibilityOverrides  # noqa: E402
from futonhub.services.price_catalog_reconciliation import reconcile_canonical_catalogue  # noqa: E402
from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    filter_catalog_rows,
)


PACK_IDS = ("1002010", "1018005", "1020005", "1020006", "1020007", "1020009")
HISTORICAL_DUO_IDS = ("78009", "78012", "78013")
SUPPLIER_COMPONENT_IDS = ("608017", "608018", "608019", "616019")
TOPPER_IDS = ("1110002", "1110003", "1110009", "1110010", "1110011", "1110013", "1110015")


def pack_live_row(item_id: str) -> dict[str, object]:
    return {
        "item_id": item_id,
        "heca_reference": item_id,
        "hub_item_code": item_id,
        "base_item_code": item_id,
        "name": f"Pack aprobado {item_id}",
        "family": "Futones",
        "filter_family": "Futones",
        "filter_group": "Pack",
        "filter_size": "Sin definir",
        "filter_gama": "Sin definir",
        "item_record_type": "simple",
        "is_pack": True,
    }


class AFKWorkday002CatalogFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = PhysicalCatalogSnapshot.load()
        cls.visibility = InventoryVisibilityOverrides.load()
        cls.baseline = CatalogOperationalBaseline()
        cls.live_rows = [dict(row) for row in cls.snapshot.rows_by_item_id.values()]
        cls.live_rows.extend(pack_live_row(item_id) for item_id in PACK_IDS)
        cls.visible_rows = cls.visibility.apply_to_live_rows(cls.snapshot, cls.live_rows)
        cls.visible_by_id = {str(row.get("item_id")): row for row in cls.visible_rows}

    def test_runtime_counts_keep_physical_snapshot_strict_and_inventory_visible_257(self) -> None:
        self.assertEqual(self.snapshot.expected_count, 254)
        self.assertEqual(len(self.snapshot.rows_by_item_id), 254)
        self.assertEqual(self.visibility.expected_visible_count(len(self.snapshot.item_ids)), 257)
        self.assertEqual(len(self.visible_rows), 257)

    def test_runtime_contracts_are_packaged_outside_auditoria(self) -> None:
        runtime_paths = (
            self.snapshot.source_path,
            self.snapshot.manifest_path,
            self.visibility.source_path,
            self.visibility.manifest_path,
            self.baseline.source_path,
            self.baseline.manifest_path,
        )
        for path in runtime_paths:
            with self.subTest(path=path):
                self.assertIsNotNone(path)
                self.assertNotIn("auditoria", str(path).replace("\\", "/").lower())

    def test_confirmed_identities_are_literal_and_do_not_create_wrong_codes(self) -> None:
        premium = self.snapshot.rows_by_item_id["758087"]
        self.assertEqual(premium["heca_reference"], "0758087")
        self.assertEqual(premium["hub_item_code"], "0758087")
        self.assertEqual(premium["name"], "Fut\u00f3n de coco Premium, 120 x 200 x 17 cm")
        self.assertIn("0758087", self.snapshot.rows_by_code)
        self.assertNotIn("0758007", self.snapshot.rows_by_code)

        corrected = self.snapshot.rows_by_item_id["619011"]
        self.assertEqual(corrected["heca_reference"], "0619008")
        self.assertEqual(corrected["hub_item_code"], "0619008")
        self.assertEqual(corrected["name"], "Funda Fut\u00f3n 90x200x14,5 cm, Marr\u00f3n Chocolate")
        self.assertIn("0619008", self.snapshot.rows_by_code)
        self.assertNotIn("0619011", self.snapshot.rows_by_code)

        self.assertIn("1020007", self.visible_by_id)
        self.assertNotIn("1020011", self.visible_by_id)

    def test_toppers_have_their_own_family_and_filter_family(self) -> None:
        for item_id in TOPPER_IDS:
            with self.subTest(item_id=item_id):
                row = self.snapshot.rows_by_item_id[item_id]
                self.assertEqual(row["family"], "Toppers")
                self.assertEqual(row["filter_family"], "Toppers")
                self.assertEqual(row["filter_group"], "Toppers")

    def test_inventory_visibility_includes_only_approved_packs_and_excludes_old_duo_duplicates(self) -> None:
        for item_id in PACK_IDS:
            with self.subTest(pack=item_id):
                row = self.visible_by_id[item_id]
                self.assertEqual(row["filter_family"], "Complementos")
                self.assertEqual(row["filter_group"], "")
                self.assertEqual(row["filter_size"], "")
                self.assertEqual(row["filter_gama"], "")
        for item_id in HISTORICAL_DUO_IDS:
            with self.subTest(excluded=item_id):
                self.assertNotIn(item_id, self.visible_by_id)
                metadata = self.visibility.metadata_for_item_id(item_id)
                self.assertEqual(metadata["inventory_visible"], "NO")
                self.assertEqual(metadata["visibility_reason"], "HISTORICAL_DUPLICATE_REPLACED_BY_CORRECT_CODE")

    def test_exact_inventory_searches_respect_corrected_identities(self) -> None:
        expectations = {
            "0758087": ["758087"],
            "0758007": [],
            "1020007": ["1020007"],
            "1020011": [],
            "0619008": ["619011"],
            "0619011": [],
            "0780009": ["780009"],
            "0078009": [],
            "0780012": ["780012"],
            "0078012": [],
            "0780013": ["780013"],
            "0078013": [],
        }
        for query, expected_ids in expectations.items():
            with self.subTest(query=query):
                rows = filter_catalog_rows(self.visible_rows, CatalogFilterSelection(query=query))
                self.assertEqual([str(row.get("item_id")) for row in rows], expected_ids)

    def test_inventory_visibility_does_not_expand_price_catalogue_or_macao_price_policy(self) -> None:
        reconciliation = reconcile_canonical_catalogue(self.snapshot, self.visible_rows)
        self.assertEqual(reconciliation["counts"]["canonical_expected"], 254)
        self.assertEqual(reconciliation["counts"]["price_catalogue_visible"], 254)
        self.assertTrue(set(PACK_IDS).isdisjoint({str(row["item_id"]) for row in reconciliation["canonical_rows"]}))

        macao_operational = self.baseline.metadata_for_item_id("302009")
        macao_historical = self.baseline.metadata_for_item_id("402014")
        self.assertTrue(macao_operational["can_participate_in_price_propagation"])
        self.assertFalse(macao_historical["can_participate_in_price_propagation"])
        self.assertEqual(macao_historical["operational_status"], "HISTORICAL_OR_DISCONTINUED")
        self.assertEqual(macao_historical["business_review_status"], "REVIEW_RESOLVED")

    def test_supplier_components_remain_order_eligible_but_not_price_operable(self) -> None:
        for item_id in SUPPLIER_COMPONENT_IDS:
            with self.subTest(item_id=item_id):
                row = self.visible_by_id[item_id]
                eligible, reason = supplier_order_eligibility_reason(dict(row))
                baseline = self.baseline.metadata_for_item_id(item_id)
                self.assertTrue(eligible, reason)
                self.assertFalse(row["price_operable"])
                self.assertEqual(row["sale_item"], "NO")
                self.assertFalse(baseline["can_participate_in_price_propagation"])
                self.assertEqual(baseline["quarantine_group"], "SUPPLIER_COMPONENT_NOT_FOR_SALE")


if __name__ == "__main__":
    unittest.main()

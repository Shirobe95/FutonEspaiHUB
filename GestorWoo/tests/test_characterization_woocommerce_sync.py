from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import woocommerce_sync_preview as sync  # noqa: E402


class WooSyncClassificationTests(unittest.TestCase):
    def test_variable_parent_without_sku_is_informational(self) -> None:
        woo = {"item_kind": "product", "type": "variable", "sku": "", "woo_id": 100}

        self.assertTrue(sync.is_variable_parent_without_sku(woo))

    def test_test_products_and_children_are_ignored(self) -> None:
        ignored_parent_ids = {100}

        self.assertTrue(
            sync.is_test_or_demo_woo(
                {"item_kind": "product", "woo_id": 100, "name": "Test Product + Var"},
                ignored_parent_ids,
            )
        )
        self.assertTrue(
            sync.is_test_or_demo_woo(
                {"item_kind": "variation", "woo_id": 101, "parent_woo_id": 100, "name": "Medida 90x200"},
                ignored_parent_ids,
            )
        )

    def test_variable_parent_sku_owned_by_variation_is_informational(self) -> None:
        woo = {"item_kind": "product", "type": "variable", "woo_id": 200, "sku": "ABC-001"}

        self.assertTrue(sync.is_variable_parent_sku_owned_by_variation(woo, {200: {"abc001"}}))


class WooInventoryMatchTests(unittest.TestCase):
    def test_woo_id_match_has_priority_over_sku_alias(self) -> None:
        by_woo = {"900": [{"item_id": 1, "woo_id": 900, "woo_sku": "OTHER"}]}
        by_sku = {"abc001": [{"item_id": 2, "heca_reference": "ABC-001"}]}

        match, method, all_matches = sync.find_inventory_match(
            {"woo_id": 900, "sku": "ABC-001"},
            {"by_woo_id": by_woo, "by_sku": by_sku},
        )

        self.assertEqual(match["item_id"], 1)
        self.assertEqual(method, "woo_id")
        self.assertEqual([row["item_id"] for row in all_matches], [1])

    def test_sku_and_heca_reference_aliases_match_when_woo_id_is_absent(self) -> None:
        inventory = [{"item_id": 201001, "heca_reference": "0201014", "woo_sku": ""}]
        indexes = sync.build_inventory_indexes(inventory)

        match, method, all_matches = sync.find_inventory_match(
            {"woo_id": "", "sku": "020-1014"},
            indexes,
        )

        self.assertEqual(match["item_id"], 201001)
        self.assertEqual(method, "sku")
        self.assertEqual([row["item_id"] for row in all_matches], [201001])


class WooSyncPreviewContractTests(unittest.TestCase):
    def test_preview_excludes_tests_and_keeps_variable_parents_informational(self) -> None:
        woo_items = [
            {
                "item_kind": "product",
                "type": "variable",
                "woo_id": 100,
                "parent_woo_id": None,
                "sku": "",
                "name": "Test Product + Var",
                "price": "0",
                "family": "Otros / Sin clasificar",
                "confidence": "Baja",
            },
            {
                "item_kind": "variation",
                "type": "variation",
                "woo_id": 101,
                "parent_woo_id": 100,
                "sku": "TEST-90",
                "name": "Test Product + Var 90x200",
                "price": "10",
                "family": "Futones",
                "confidence": "Alta",
            },
            {
                "item_kind": "product",
                "type": "variable",
                "woo_id": 200,
                "parent_woo_id": None,
                "sku": "SKU-PACK",
                "name": "Futon variable padre",
                "price": "150",
                "family": "Futones",
                "confidence": "Alta",
            },
            {
                "item_kind": "variation",
                "type": "variation",
                "woo_id": 201,
                "parent_woo_id": 200,
                "sku": "SKU-PACK",
                "name": "Futon variable 140x200",
                "price": "150",
                "family": "Futones",
                "confidence": "Alta",
            },
            {
                "item_kind": "product",
                "type": "variable",
                "woo_id": 300,
                "parent_woo_id": None,
                "sku": "",
                "name": "Tatami variable sin SKU",
                "price": "0",
                "family": "Tatamis",
                "confidence": "Alta",
            },
        ]
        inventory = [{"item_id": 201001, "heca_reference": "SKU-PACK", "woo_id": "", "woo_sku": ""}]

        with patch.object(sync, "load_woocommerce_items", return_value=woo_items), patch.object(
            sync, "load_inventory_items", return_value=inventory
        ):
            preview = sync.build_sync_preview(object())

        rows_by_woo_id = {row["woo"]["woo_id"]: row for row in preview["items"]}

        self.assertEqual(rows_by_woo_id[100]["match_method"], "ignored_test_item")
        self.assertEqual(rows_by_woo_id[101]["match_method"], "ignored_test_item")
        self.assertEqual(rows_by_woo_id[200]["match_method"], "parent_sku_owned_by_variation")
        self.assertEqual(rows_by_woo_id[200]["review"]["severity"], "Info")
        self.assertEqual(rows_by_woo_id[201]["match_method"], "sku")
        self.assertEqual(rows_by_woo_id[201]["supabase_match"]["item_id"], 201001)
        self.assertEqual(rows_by_woo_id[300]["match_method"], "no_match")
        self.assertEqual(
            [issue["code"] for issue in rows_by_woo_id[300]["issues"]],
            ["variable_parent_without_sku"],
        )


class ManualWooLinkPreviewTests(unittest.TestCase):
    def test_manual_link_preview_fills_only_empty_classification_fields(self) -> None:
        before = {
            "item_id": 55,
            "name": "Item sin Woo",
            "family": "Futones",
            "subgroup": "",
            "size": "",
            "materials": "Algodon",
            "commercial_status": "",
            "is_pack": "",
            "woo_id": "",
            "woo_link_status": "",
        }
        row = {
            "woo": {
                "item_kind": "variation",
                "woo_id": 777,
                "parent_woo_id": 700,
                "sku": "0201014",
                "name": "Futon 140x200",
                "type": "variation",
                "price": "138.00",
                "categories": "Futones",
            },
            "classification_after": {
                "family": "Tatamis",
                "subgroup": "Futon",
                "size": "140x200",
                "materials": "Latex",
                "commercial_status": "Normal",
                "is_pack": 0,
            },
            "manual_link_candidate": {"available": True},
        }

        with patch.object(sync, "_rows_with_woo_id", return_value=[]), patch.object(
            sync, "_fetch_inventory_item_by_id", return_value=before
        ):
            preview = sync.preview_manual_woo_link(object(), row, 55)

        payload = preview["update_payload"]
        self.assertEqual(payload["woo_id"], 777)
        self.assertEqual(payload["woo_parent_id"], 700)
        self.assertEqual(payload["woo_link_status"], "Enlazado manual")
        self.assertNotIn("family", payload)
        self.assertNotIn("materials", payload)
        self.assertEqual(payload["subgroup"], "Futon")
        self.assertEqual(payload["size"], "140x200")
        self.assertEqual(payload["commercial_status"], "Normal")
        self.assertEqual(payload["is_pack"], 0)


if __name__ == "__main__":
    unittest.main()

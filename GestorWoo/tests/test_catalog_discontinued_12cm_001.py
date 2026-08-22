import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.inventory_visibility import InventoryVisibilityOverrides  # noqa: E402
from futonhub.services.price_catalog_reconciliation import operational_price_catalogue_rows, reconcile_canonical_catalogue  # noqa: E402
from futonhub.services.price_woo_catalog_index import WooReadOnlyIndex, resolve_physical_woo_identity  # noqa: E402
from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot  # noqa: E402
from futonhub.core.codes import supplier_order_eligibility_reason  # noqa: E402


DISCONTINUED_12CM_IDS = ("725001", "725002", "725003", "725004", "725005", "725006")
DISCONTINUED_12CM_CODES = ("0725001", "0725002", "0725003", "0725004", "0725005", "0725006")


def empty_woo_index() -> WooReadOnlyIndex:
    return WooReadOnlyIndex(
        products_by_id={},
        products_by_exact_sku={},
        variations_by_id={},
        variations_by_exact_sku={},
        variations_by_parent={},
        woo_entities_by_exact_literal_sku={},
        counts={},
    )


class CatalogDiscontinued12cm001Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = PhysicalCatalogSnapshot.load()
        cls.visibility = InventoryVisibilityOverrides.load()
        cls.live_rows = [
            {
                **dict(row),
                "commercial_status": "Normal",
                "woo_link_status": "Sin Woo",
                "woo_id": "",
                "woo_parent_id": "",
                "woo_sku": "",
            }
            for row in cls.snapshot.rows_by_item_id.values()
        ]
        cls.visible_rows = cls.visibility.apply_to_live_rows(cls.snapshot, cls.live_rows)
        cls.visible_by_id = {str(row.get("item_id")): row for row in cls.visible_rows}

    def test_12cm_identities_remain_literal_historical_inventory_rows(self) -> None:
        for item_id, code in zip(DISCONTINUED_12CM_IDS, DISCONTINUED_12CM_CODES, strict=True):
            with self.subTest(code=code):
                snapshot_row = self.snapshot.rows_by_item_id[item_id]
                self.assertEqual(snapshot_row["heca_reference"], code)
                self.assertEqual(snapshot_row["hub_item_code"], code)
                self.assertIn(item_id, self.visible_by_id)
                self.assertEqual(self.visibility.metadata_for_item_id(item_id), {})

    def test_12cm_is_not_encoded_as_manual_visibility_overrides(self) -> None:
        self.assertEqual(self.visibility.expected_visible_count(len(self.snapshot.item_ids)), 257)
        for item_id in DISCONTINUED_12CM_IDS:
            with self.subTest(item_id=item_id):
                self.assertEqual(self.visibility.metadata_for_item_id(item_id), {})

    def test_12cm_current_normal_rows_are_not_hidden_by_manual_price_policy(self) -> None:
        reconciliation = reconcile_canonical_catalogue(
            self.snapshot,
            self.live_rows,
            visibility_overrides=self.visibility,
        )
        rows_by_id = {str(row.get("item_id")): row for row in reconciliation["canonical_rows"]}
        woo_index = empty_woo_index()
        for item_id in DISCONTINUED_12CM_IDS:
            with self.subTest(item_id=item_id):
                row = rows_by_id[item_id]
                self.assertNotIn("price_policy_override", row)
                context = resolve_physical_woo_identity(row, woo_index=woo_index)
                self.assertEqual(context["sync_status"], "WOO_NOT_FOUND")
                self.assertEqual(context["session_usable"], "NO")

    def test_live_descatalogado_status_is_a_commercial_veto_for_future_regeneration(self) -> None:
        live_descatalogado = []
        for item_id in DISCONTINUED_12CM_IDS:
            row = dict(self.snapshot.rows_by_item_id[item_id])
            row["commercial_status"] = "Descatalogado"
            live_descatalogado.append(row)
        reconciliation = reconcile_canonical_catalogue(self.snapshot, live_descatalogado)
        rows_by_id = {str(row.get("item_id")): row for row in reconciliation["canonical_rows"]}
        for item_id in DISCONTINUED_12CM_IDS:
            with self.subTest(item_id=item_id):
                row = rows_by_id[item_id]
                self.assertEqual(row["catalog_commercial_status"], "DESCATALOGADO_NO_WOO_REQUIRED")
                self.assertEqual(row["woo_mapping_required"], "NO")
                self.assertFalse(row["price_operable"])
                self.assertEqual(row["operational_status"], "HISTORICAL_OR_DISCONTINUED")
                eligible, reason = supplier_order_eligibility_reason(row)
                self.assertFalse(eligible)
                self.assertEqual(reason, "rejected:DESCATALOGADO_NO_NEW_OPERATIONAL_SELECTION")

    def test_descatalogado_rows_are_excluded_from_operational_inventory_and_price_catalogue(self) -> None:
        live_rows = [dict(row) for row in self.snapshot.rows_by_item_id.values()]
        for row in live_rows:
            if str(row.get("item_id")) in DISCONTINUED_12CM_IDS:
                row["commercial_status"] = "Descatalogado"
            else:
                row["commercial_status"] = "Normal"
        visible_rows = self.visibility.apply_to_live_rows(self.snapshot, live_rows)
        visible_ids = {str(row.get("item_id")) for row in visible_rows}
        self.assertTrue(set(DISCONTINUED_12CM_IDS).isdisjoint(visible_ids))

        reconciliation = reconcile_canonical_catalogue(self.snapshot, live_rows)
        price_ids = {str(row.get("item_id")) for row in operational_price_catalogue_rows(reconciliation["canonical_rows"])}
        self.assertTrue(set(DISCONTINUED_12CM_IDS).isdisjoint(price_ids))


if __name__ == "__main__":
    unittest.main()

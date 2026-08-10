from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDITORIA = ROOT.parent / "auditoria"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(AUDITORIA))

from pre_fire_001a_apply import (  # noqa: E402
    MACAO_TARGET_FAMILY,
    macao_state,
    mapping_payload,
    verify_mapping_values,
)


class PreFire001AApplyTests(unittest.TestCase):
    def test_macao_only_accepts_the_approved_source_or_target_state(self) -> None:
        approved = {"family": "Camas", "filter_family": "Camas", "filter_group": "Macao"}
        completed = {"family": MACAO_TARGET_FAMILY, "filter_family": MACAO_TARGET_FAMILY, "filter_group": "Macao"}
        unexpected = {"family": "Tatamis", "filter_family": "Camas", "filter_group": "Macao"}
        self.assertEqual(macao_state(approved), "READY_FOR_APPLY")
        self.assertEqual(macao_state(completed), "NO_ACTION_REQUIRED")
        self.assertEqual(macao_state(unexpected), "ABORT_UNEXPECTED_STATE")

    def test_mapping_payload_includes_only_fields_explicitly_flagged_yes(self) -> None:
        row = {
            "write_woo_id": "YES", "target_woo_id": "11838",
            "write_woo_parent_id": "NO", "target_woo_parent_id": "3646",
            "write_woo_kind": "YES", "target_woo_kind": "variation",
            "write_woo_sku": "NO", "target_woo_sku": "",
            "write_woo_name": "YES", "target_woo_name": "Natural",
            "write_link_status": "YES", "target_link_status": "Enlazado",
        }
        self.assertEqual(
            mapping_payload(row),
            {"woo_id": "11838", "woo_item_kind": "variation", "woo_name": "Natural", "woo_link_status": "Enlazado"},
        )

    def test_verify_mapping_rejects_changes_outside_the_field_minimal_payload(self) -> None:
        snapshot = {
            "payload_json": '{"woo_id":"11838"}',
            "woo_item_kind": "", "woo_id": "", "woo_parent_id": "", "woo_sku": "",
            "woo_name": "", "woo_link_status": "Sin Woo",
        }
        valid = {"woo_item_kind": "", "woo_id": "11838", "woo_parent_id": "", "woo_sku": "", "woo_name": "", "woo_link_status": "Sin Woo"}
        invalid = {**valid, "woo_name": "Unexpected"}
        self.assertEqual(verify_mapping_values(valid, snapshot), (True, ""))
        self.assertFalse(verify_mapping_values(invalid, snapshot)[0])

    def test_single_row_revalidation_uses_the_exact_check_without_rebuilding_a_178_row_plan(self) -> None:
        import pre_fire_001a_apply

        source = inspect.getsource(pre_fire_001a_apply.revalidate_ready_row)
        self.assertIn("revalidate_live_rows([master_row]", source)
        self.assertNotIn("build_preflight_rows([master_row]", source)

    def test_apply_script_has_no_woo_mutation_or_price_stock_payload(self) -> None:
        import pre_fire_001a_apply

        source = inspect.getsource(pre_fire_001a_apply)
        for forbidden in (".post(", ".put(", ".delete(", "regular_price", "sale_price", "stock_quantity"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

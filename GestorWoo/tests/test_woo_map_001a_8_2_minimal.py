from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.woo_map_001a_8_2_minimal import minimal_apply_rows, minimal_apply_summary


def preflight(**changes: str) -> dict[str, str]:
    row = {
        "physical_item_id": "1",
        "physical_sku": "0201001",
        "woo_id": "11",
        "woo_parent_id": "101",
        "woo_kind": "variation",
        "woo_sku": "0201001",
        "woo_name": "Nombre Woo corto",
        "current_supabase_woo_id": "11",
        "current_supabase_parent_id": "101",
        "current_supabase_woo_kind": "variation",
        "current_supabase_woo_sku": "0201001",
        "current_supabase_woo_name": "Nombre descriptivo conservado",
        "current_supabase_woo_link_status": "Enlazado",
        "precondition_ok": "YES",
        "safe_to_apply": "YES_PREVIEW_ONLY",
        "blocking_reason": "",
    }
    row.update(changes)
    return row


class WooMap001A82MinimalTests(unittest.TestCase):
    def test_name_only_difference_never_triggers_a_write(self) -> None:
        row = minimal_apply_rows([preflight()])[0]
        self.assertEqual(row["difference_class"], "NAME_ONLY_DIFFERENCE")
        self.assertEqual(row["field_write_count"], "0")
        self.assertEqual(row["write_name"], "NO")
        self.assertEqual(row["name_policy"], "PRESERVE_DESCRIPTIVE_CURRENT_VALUE")

    def test_partial_relation_writes_only_missing_sku(self) -> None:
        row = minimal_apply_rows([preflight(current_supabase_woo_sku="")])[0]
        self.assertEqual(row["write_sku"], "YES")
        self.assertEqual(row["write_woo_id"], "NO")
        self.assertEqual(row["write_parent"], "NO")
        self.assertEqual(row["write_kind"], "NO")
        self.assertEqual(row["write_name"], "NO")

    def test_empty_display_cache_can_be_filled_with_relation_fields(self) -> None:
        row = minimal_apply_rows([preflight(
            current_supabase_woo_id="",
            current_supabase_parent_id="",
            current_supabase_woo_kind="",
            current_supabase_woo_sku="",
            current_supabase_woo_name="",
        )])[0]
        self.assertEqual(row["difference_class"], "FULL_MAPPING_AND_NAME_DIFFERENCE")
        self.assertEqual(row["field_write_count"], "5")
        self.assertEqual(row["write_name"], "YES")
        self.assertEqual(row["name_policy"], "FILL_EMPTY_DISPLAY_CACHE")

    def test_link_status_is_never_invented(self) -> None:
        row = minimal_apply_rows([preflight(current_supabase_woo_link_status="")])[0]
        self.assertEqual(row["write_link_status"], "NO")
        self.assertEqual(row["link_status_policy"], "PRESERVE_CURRENT_PENDING_USER_RULE")

    def test_summary_reports_minimal_field_count(self) -> None:
        rows = minimal_apply_rows([preflight(), preflight(current_supabase_woo_sku="")])
        summary = minimal_apply_summary(rows)
        self.assertEqual(summary["rows_no_write_needed"], 1)
        self.assertEqual(summary["total_fields_future_write"], 1)


if __name__ == "__main__":
    unittest.main()

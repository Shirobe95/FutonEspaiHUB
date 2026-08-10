from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "auditoria" / "woo_map_001a_0_audit.py"
spec = importlib.util.spec_from_file_location("woo_map_001a_0_audit", AUDIT_PATH)
audit = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class WooMap001A0AuditTests(unittest.TestCase):
    def test_exact_sku_match(self) -> None:
        method, rows = audit.sku_match("0201001", [{"sku": "0201001", "woo_id": "1"}])
        self.assertEqual(method, "EXACT_SKU")
        self.assertEqual(rows[0]["woo_id"], "1")

    def test_missing_sku_is_blocked(self) -> None:
        method, rows = audit.sku_match("0201001", [{"sku": "0201002"}])
        self.assertEqual(method, "MISSING_WOO_SKU")
        self.assertEqual(rows, [])

    def test_duplicate_sku_is_blocked(self) -> None:
        method, rows = audit.sku_match("0201001", [{"sku": "0201001"}, {"sku": "0201001"}])
        self.assertEqual(method, "DUPLICATE_EXACT_SKU")
        self.assertEqual(len(rows), 2)

    def test_only_approved_exceptional_equivalence_is_used(self) -> None:
        method, rows = audit.sku_match("0302018", [{"sku": "302018", "woo_id": "7"}])
        self.assertEqual(method, "EXCEPTION_302018_0302018")
        self.assertEqual(rows[0]["woo_id"], "7")
        self.assertEqual(audit.sku_match("0302019", [{"sku": "302019"}])[0], "MISSING_WOO_SKU")

    def test_variation_uses_own_sku(self) -> None:
        row = audit.flatten_woo({"id": 12, "parent_id": 3, "sku": "VAR-12", "_audit_parent_name": "Parent"}, "variation")
        self.assertEqual(row["sku"], "VAR-12")
        self.assertEqual(row["parent_woo_id"], "3")

    def test_csv_literal_null_is_treated_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.csv"
            path.write_text("item_id,heca_reference\n1,null\n", encoding="utf-8")
            self.assertEqual(audit.read_csv(path)[0]["heca_reference"], "")

    def test_grouped_component_has_missing_quantity_and_is_not_exact(self) -> None:
        rows = audit.extract_woo_composition({"id": 1, "sku": "PACK", "type": "grouped", "grouped_products": [2]})
        self.assertEqual(rows[0]["quantity_status"], "MISSING")

    def test_bundle_component_quantity_is_exact_when_positive(self) -> None:
        rows = audit.extract_woo_composition({"id": 1, "sku": "PACK", "bundled_items": [{"product_id": 2, "quantity_default": 3}]})
        self.assertEqual(rows[0]["component_woo_id"], "2")
        self.assertEqual(rows[0]["quantity"], "3")
        self.assertEqual(rows[0]["quantity_status"], "EXACT")

    def test_pipe_sku_is_exact_component_list_with_repeated_quantity(self) -> None:
        rows = audit.extract_woo_composition({"id": 10, "parent_id": 2, "sku": "0302009|0201002|0201002"})
        by_sku = {row["component_sku"]: row for row in rows}
        self.assertEqual(by_sku["0302009"]["quantity"], 1)
        self.assertEqual(by_sku["0201002"]["quantity"], 2)
        self.assertEqual(by_sku["0201002"]["quantity_status"], "EXACT")

    def test_delta_sum_uses_quantity(self) -> None:
        result = audit.simulate_delta(100, [
            {"current_sale_price": 10, "new_sale_price": 12, "quantity": 2},
            {"current_sale_price": 20, "new_sale_price": 19, "quantity": 3},
        ])
        self.assertEqual(result["delta_combination"], 1)
        self.assertEqual(result["new_combination_sale_price"], 101)

    def test_repeated_component_rows_are_accumulated(self) -> None:
        result = audit.simulate_delta(50, [
            {"current_sale_price": 10, "new_sale_price": 11, "quantity": 1},
            {"current_sale_price": 10, "new_sale_price": 11, "quantity": 2},
        ])
        self.assertEqual(result["new_combination_sale_price"], 53)

    def test_negative_delta_is_supported(self) -> None:
        result = audit.simulate_delta(50, [{"current_sale_price": 10, "new_sale_price": 8, "quantity": 2}])
        self.assertEqual(result["delta_combination"], -4)
        self.assertEqual(result["new_combination_sale_price"], 46)

    def test_percentage_change_is_converted_to_absolute_prices(self) -> None:
        result = audit.simulate_delta(100, [{"current_sale_price": 50, "new_sale_price": 55, "quantity": 1}])
        self.assertEqual(result["delta_combination"], 5)

    def test_empty_sale_price_blocks_simulation(self) -> None:
        result = audit.simulate_delta("", [{"current_sale_price": 10, "new_sale_price": 11, "quantity": 1}])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "EMPTY_COMBINATION_SALE_PRICE")

    def test_missing_quantity_blocks_simulation(self) -> None:
        result = audit.simulate_delta(100, [{"current_sale_price": 10, "new_sale_price": 11, "quantity": ""}])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "MISSING_OR_INVALID_QUANTITY")

    def test_sale_schedule_is_reported_without_mutation(self) -> None:
        rows = audit.build_price_audit([{
            "woo_id": "1", "regular_price": "100", "sale_price": "90", "price": "90",
            "date_on_sale_from": "2026-01-01", "date_on_sale_to": "2026-01-31",
        }])
        self.assertIn("SCHEDULED_SALE_DATES_PRESENT", rows[0]["risk_flags"])

    def test_discount_case_does_not_plan_regular_price_write(self) -> None:
        case = next(row for row in audit.simulation_cases() if row["case_id"] == "discount_preserved")
        self.assertEqual(case["regular_price_write"], "NO")
        self.assertEqual(case["new_combination_sale_price"], 95)

    def test_required_plus_eight_simulations_are_literal(self) -> None:
        cases = {row["case_id"]: row for row in audit.simulation_cases()}
        self.assertEqual(cases["single_up_8_x_1"]["delta_combination"], 8)
        self.assertEqual(cases["single_up_8_x_2"]["delta_combination"], 16)

    def test_required_cross_pack_and_ambiguous_simulations_exist(self) -> None:
        cases = {row["case_id"]: row for row in audit.simulation_cases()}
        self.assertEqual(cases["ambiguous_sku"]["status"], "BLOCKED")
        self.assertEqual(cases["two_selected_same_pack"]["new_combination_sale_price"], 216)
        self.assertEqual(cases["one_component_multiple_packs"]["new_combination_sale_price"], "108 | 166")

    def test_canonical_edge_fields_are_explicit(self) -> None:
        rows = audit.enrich_canonical_edges([{
            "source": "WOO_SKU_COMPONENT_LIST", "edge_role": "PRIMARY_WOO", "edge_status": "EXACT",
            "parent_woo_id": "10", "woo_product_parent_id": "5", "parent_sku": "PACK",
            "component_sku": "ITEM", "physical_item_id": "1", "quantity": 2,
            "quantity_status": "EXACT", "physical_match_method": "EXACT_SKU",
        }], [{"woo_id": "10", "parent_woo_id": "5", "sku": "PACK", "name": "Pack"}])
        self.assertEqual(rows[0]["combination_name"], "Pack")
        self.assertEqual(rows[0]["component_item_id"], "1")
        self.assertEqual(rows[0]["resolution_status"], "COMPOSITION_EXACT_WOO")
        self.assertEqual(rows[0]["source_woo"], "YES")

    def test_audit_source_has_no_woo_mutation_call(self) -> None:
        source = AUDIT_PATH.read_text(encoding="utf-8")
        for token in ("client.put(", "client.post(", "client.delete(", ".update_product_pricing(", ".update_variation_pricing("):
            self.assertNotIn(token, source)

    def test_audit_source_has_no_supabase_mutation(self) -> None:
        source = AUDIT_PATH.read_text(encoding="utf-8")
        for token in ("create_supabase_client", ".table(", ".upsert(", ".delete().eq("):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()

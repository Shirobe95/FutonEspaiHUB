from __future__ import annotations

import inspect
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "GestorWoo" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.services.combination_price_impact import (  # noqa: E402
    CombinationPriceImpactError,
    CombinationPriceImpactService,
    SPECIAL_LITERAL_SUFFIX_SKUS,
    effective_edge_status,
    effective_resolution_status,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


class CombinationPriceImpactServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = CombinationPriceImpactService(ROOT / "auditoria" / "out")

    def test_adapter_load_is_deterministic_and_has_expected_counts(self) -> None:
        first = self.service.describe()
        second = CombinationPriceImpactService().describe()

        self.assertEqual(first["source_handoff_sha256"], second["source_handoff_sha256"])
        self.assertEqual(first["source_kind"], "legacy_artifact_root")
        self.assertEqual(second["source_kind"], "runtime_config")
        self.assertEqual(first["clean_graph_edges"], 926)
        self.assertEqual(first["operational_combinations"], 241)
        self.assertEqual(first["impact_matrix_rows"], 640)
        self.assertEqual(first["excluded_combinations"], 142)
        self.assertEqual(second["clean_graph_edges"], 926)
        self.assertEqual(second["operational_combinations"], 241)
        self.assertEqual(second["impact_matrix_rows"], 640)
        self.assertEqual(second["excluded_combinations"], 142)

    def test_manifest_hash_mismatch_is_rejected_before_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            shutil.copytree(ROOT / "auditoria" / "out" / "woo_map_001a_3", out / "woo_map_001a_3")
            shutil.copytree(ROOT / "auditoria" / "out" / "woo_map_001a_4", out / "woo_map_001a_4")
            target = out / "woo_map_001a_4" / "WOO_MAP_001A_4_WOO_IMPACT_MATRIX.csv"
            target.write_bytes(target.read_bytes() + b"\n")

            with self.assertRaisesRegex(CombinationPriceImpactError, "SHA-256 mismatch"):
                CombinationPriceImpactService(out)

    def test_effective_status_prefers_new_value_and_falls_back_to_history(self) -> None:
        self.assertEqual(effective_edge_status({"edge_status": "BLOCKED", "new_edge_status": "EXACT"}), "EXACT")
        self.assertEqual(effective_edge_status({"edge_status": "EXACT", "new_edge_status": ""}), "EXACT")
        self.assertEqual(
            effective_resolution_status({
                "resolution_status": "COMPONENT_SKU_NOT_FOUND",
                "new_resolution_status": "COMPOSITION_EXACT_WOO_FULL_SKU",
            }),
            "COMPOSITION_EXACT_WOO_FULL_SKU",
        )

    def test_no_operational_relation_is_blocked_by_historical_status(self) -> None:
        primary = [
            row for row in self.service.clean_graph_rows if row.get("edge_role") == "PRIMARY_WOO"
        ]
        self.assertTrue(primary)
        self.assertEqual({effective_edge_status(row) for row in primary}, {"EXACT"})

    def test_literal_suffix_skus_are_complete_and_not_rebased(self) -> None:
        self.assertEqual(
            set(self.service.describe()["special_literal_suffix_skus"]),
            set(SPECIAL_LITERAL_SUFFIX_SKUS),
        )
        for sku in SPECIAL_LITERAL_SUFFIX_SKUS:
            with self.subTest(sku=sku):
                result = self.service.impact_for_changes([
                    {"sku": sku, "old_price": "10", "new_price": "11", "proposal_key": sku}
                ])
                components = [
                    component
                    for combination in result["included_combinations"]
                    for component in combination["modified_components"]
                ]
                self.assertTrue(any(component["component_sku"] == sku for component in components))
                self.assertFalse(any(component["component_sku"] == sku[:-1] for component in components))

    def test_suffix_relation_uses_effective_resolution_not_historical_blocker(self) -> None:
        result = self.service.impact_for_changes([
            {"sku": "0726007A", "component_woo_id": "10406", "old_price": 10, "new_price": 11}
        ])
        relation = result["included_combinations"][0]["modified_components"][0]["relation"]

        self.assertEqual(relation["historical_edge_status"], "BLOCKED")
        self.assertEqual(relation["effective_edge_status"], "EXACT")
        self.assertEqual(relation["effective_resolution_status"], "COMPOSITION_EXACT_WOO_FULL_SKU")

    def test_indices_are_available_by_target_sku_component_and_combination(self) -> None:
        self.assertIn("201002", self.service.matrix_by_target_key)
        self.assertIn("0201002", self.service.matrix_by_sku)
        self.assertIn("10406", self.service.matrix_by_component_woo_id)
        self.assertIn("3662", self.service.matrix_by_combination)

    def test_one_component_can_affect_many_combinations(self) -> None:
        result = self.service.impact_for_changes([
            {"component_target_key": "201002", "old_price": 10, "new_price": 12}
        ])

        self.assertEqual(result["counts"]["included_combinations"], 19)
        self.assertEqual(len({row["combination_woo_id"] for row in result["included_combinations"]}), 19)

    def test_multiple_changes_converge_and_quantity_is_applied(self) -> None:
        result = self.service.impact_for_changes([
            {"component_target_key": "201002", "old_price": 10, "new_price": 12, "proposal_key": "A"},
            {"component_target_key": "302009", "old_price": 20, "new_price": 19, "proposal_key": "B"},
        ])
        combination = next(
            row for row in result["included_combinations"] if row["combination_woo_id"] == "3662"
        )

        self.assertEqual(combination["component_delta"], "3.00")
        self.assertEqual(combination["simulated_effective_price"], "584.70")
        self.assertEqual(combination["modified_component_count"], 2)
        repeated = next(
            row for row in combination["modified_components"] if row["component_sku"] == "0201002"
        )
        self.assertEqual(repeated["quantity"], "2")
        self.assertEqual(repeated["weighted_delta"], "4.00")

    def test_negative_and_zero_deltas_are_supported(self) -> None:
        negative = self.service.impact_for_changes([
            {"component_target_key": "302009", "old_price": 20, "new_price": 19}
        ])["included_combinations"][0]
        zero = self.service.impact_for_changes([
            {"component_woo_id": "10406", "sku": "0726007A", "old_price": 50, "new_price": 50}
        ])["included_combinations"][0]

        self.assertEqual(negative["component_delta"], "-1.00")
        self.assertEqual(negative["simulated_effective_price"], "580.70")
        self.assertEqual(zero["component_delta"], "0.00")
        self.assertEqual(zero["simulated_effective_price"], "226.00")
        self.assertEqual(zero["visual_state"], "NO_CHANGE")

    def test_result_has_no_duplicate_combination_ids(self) -> None:
        result = self.service.impact_for_changes([
            {
                "component_target_key": "201002",
                "sku": "0201002",
                "old_price": 10,
                "new_price": 12,
            }
        ])
        ids = [row["combination_woo_id"] for row in result["included_combinations"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_conflicting_changes_for_same_exact_edge_are_rejected(self) -> None:
        with self.assertRaisesRegex(CombinationPriceImpactError, "Conflicting proposed changes"):
            self.service.impact_for_changes([
                {"component_target_key": "302009", "old_price": 20, "new_price": 21},
                {"sku": "0302009", "old_price": 20, "new_price": 22},
            ])

    def test_excluded_combination_never_enters_operational_result(self) -> None:
        result = self.service.impact_for_changes([
            {"sku": "0606002-1", "old_price": 30, "new_price": 31}
        ])

        self.assertEqual(result["included_combinations"], [])
        self.assertEqual(result["counts"]["excluded_combinations"], 7)
        self.assertTrue(all(row["excluded"] == "YES" for row in result["excluded_combinations"]))
        self.assertTrue(all(row["price_simulation_status"] == "BLOCKED" for row in result["excluded_combinations"]))
        self.assertTrue(all(row["publication_allowed"] == "NO" for row in result["excluded_combinations"]))

    def test_business_quarantine_is_also_outside_propagation(self) -> None:
        result = self.service.impact_for_changes([
            {"sku": "0615011", "old_price": 30, "new_price": 31}
        ])

        self.assertEqual(result["included_combinations"], [])
        self.assertGreater(result["counts"]["excluded_combinations"], 0)
        self.assertTrue(
            all("UD-001" in row["quarantine_group_ids"] for row in result["excluded_combinations"])
        )

    def test_price_field_policy_requires_live_context_for_sale_regular_and_schedule(self) -> None:
        contexts = [
            ({"regular_price": "100", "sale_price": "90"}, "SALE_PRICE_PRESENT_ACTIVE_STATE_UNVERIFIED"),
            ({"regular_price": "100", "sale_price": ""}, "REGULAR_PRICE_ONLY"),
            ({
                "regular_price": "100",
                "sale_price": "90",
                "date_on_sale_from": "2026-01-01",
                "date_on_sale_to": "2026-01-31",
            }, "SCHEDULED_DISCOUNT_PRESENT"),
        ]
        for row, context in contexts:
            with self.subTest(context=context):
                policy = self.service._price_policy(row)
                self.assertEqual(policy["price_context"], context)
                self.assertEqual(policy["price_simulation_status"], "BLOCKED_MISSING_PRICE_CONTEXT")
                self.assertEqual(policy["publication_allowed"], "NO")

    def test_service_source_has_no_remote_or_persistence_clients(self) -> None:
        source = inspect.getsource(sys.modules[CombinationPriceImpactService.__module__])
        for token in (
            "WooCommerceClient",
            "create_supabase_client",
            "requests.",
            ".table(",
            ".insert(",
            ".upsert(",
            "subprocess",
            "git commit",
            "git push",
        ):
            self.assertNotIn(token, source)

    def test_ui_preview_contains_expandable_combination_section_without_publish_action(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._open_price_bulk_add_preview)
        build_source = inspect.getsource(FutonHubErpPrototype._price_build_bulk_preview)

        self.assertIn("Impacto en combinaciones Woo", source)
        self.assertIn('show="tree headings"', source)
        self.assertIn("modified_components", source)
        self.assertIn("combination_impact", build_source)
        self.assertNotIn("publish_price", source)
        self.assertNotIn("Guardar", source)


if __name__ == "__main__":
    unittest.main()

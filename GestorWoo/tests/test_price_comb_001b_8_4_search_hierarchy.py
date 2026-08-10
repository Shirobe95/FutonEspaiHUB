from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_proposal_live_context import project_grouped_combination_rows  # noqa: E402
from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    ranked_catalog_search_rows,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem, ProposalLine  # noqa: E402


def inventory_item(raw: dict[str, object]) -> InventoryItem:
    return InventoryItem(
        code=str(raw.get("item_id") or raw.get("hub_item_code") or "-"),
        name=str(raw.get("name") or "-"),
        price="100.00 EUR",
        stock="0",
        status="OK",
        family=str(raw.get("family") or "-"),
        provider="-",
        m3="-",
        sku_woo=str(raw.get("woo_sku") or "-"),
        measures=str(raw.get("size") or "-"),
        material="-",
        sync_woo="-",
        notes="-",
        woo_id=str(raw.get("woo_id") or "-"),
        woo_item_kind="product",
        raw=raw,
    )


def component(trace_key: str, sku: str, quantity: str) -> dict[str, str]:
    return {
        "proposal_trace_key": trace_key,
        "component_item_id": trace_key,
        "component_sku": sku,
        "component_name": f"Componente {sku}",
        "quantity": quantity,
        "is_modified": "YES",
    }


def combination(woo_id: str, components: list[dict[str, str]], *, delta: str) -> dict[str, object]:
    return {
        "combination_woo_id": woo_id,
        "combination_name": f"Combinacion {woo_id}",
        "combination_sku": f"VAR-{woo_id}",
        "modified_components": components,
        "proposal_trace_keys": [row["proposal_trace_key"] for row in components],
        "component_delta": delta,
        "effective_current_price": "100.00",
        "simulated_effective_price": str(100 + float(delta)),
        "validation_status": "VALID",
        "impact_display_status": "READY",
    }


class LiteralCatalogSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "physical_sku": "0402014",
                "hub_item_code": "0402014",
                "heca_reference": "0402014",
                "item_id": "402014",
                "name": "Cama Macao",
            },
            {
                "physical_sku": "0302009",
                "hub_item_code": "0302009",
                "heca_reference": "0302009",
                "item_id": "302009",
                "name": "Base Tatami Macao",
            },
            {
                "physical_sku": "0201001",
                "hub_item_code": "0201001",
                "heca_reference": "0201001",
                "item_id": "201001",
                "name": "Tatami 80x200",
            },
            {"physical_sku": "0609007B", "item_id": "609007", "name": "Funda B"},
            {"physical_sku": "0726007A", "item_id": "726007", "name": "Funda A"},
            {"physical_sku": "1242002A", "item_id": "1242002", "name": "Complemento A"},
        ]

    def test_required_literal_codes_keep_zeroes_and_suffixes(self) -> None:
        for code in ("0402014", "0302009", "0201001", "0609007B", "0726007A", "1242002A"):
            matches, audit = ranked_catalog_search_rows(self.rows, code)
            self.assertEqual(matches[0]["physical_sku"], code)
            self.assertEqual(audit["query_type"], "CODE_LITERAL")
            self.assertEqual(audit["matched_field"], "physical_sku")

    def test_suffix_comparison_is_case_insensitive_without_rewriting_storage(self) -> None:
        matches, audit = ranked_catalog_search_rows(self.rows, "0609007b")
        self.assertEqual(matches[0]["physical_sku"], "0609007B")
        self.assertEqual(audit["matched_value"], "0609007B")

    def test_exact_physical_sku_wins_over_other_identity_fields(self) -> None:
        rows = [
            {"physical_sku": "0402014X", "item_id": "0402014", "name": "Item ID only"},
            {"physical_sku": "0402014", "item_id": "99", "name": "Physical exact"},
        ]
        matches, audit = ranked_catalog_search_rows(rows, "0402014")
        self.assertEqual(matches[0]["name"], "Physical exact")
        self.assertEqual(audit["matched_field"], "physical_sku")

    def test_code_search_does_not_coerce_or_fuzzy_match_numeric_fragments(self) -> None:
        matches, audit = ranked_catalog_search_rows(self.rows, "2014")
        self.assertEqual(matches, [])
        self.assertEqual(audit["result_count"], 0)


class PriceCatalogueSearchAndFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = PhysicalCatalogSnapshot.load()
        self.app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        self.app._inventory_catalog_snapshot_cache = self.snapshot
        self.app._price_catalog_filter_selection_state = CatalogFilterSelection()
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection()
        self.app._price_search_query = ""
        self.app._price_filter_metadata_generation = 0
        self.app._current_key = "other"
        self.app._price_edit_selected_code = ""
        self.app._price_proposal_model = {}

    def _result(self, item_id: str) -> dict[str, object]:
        raw = dict(self.snapshot.rows_by_item_id[item_id])
        item = inventory_item(raw)
        physical_sku = raw.get("hub_item_code") or raw.get("heca_reference")
        return {
            "code": item.code,
            "name": item.name,
            "item": item,
            "source": {"physical_sku": physical_sku, "hub_item_code": raw.get("hub_item_code"), "woo_sku": physical_sku, "woo_id": item_id},
        }

    def test_exact_macao_search_uses_physical_sku_first(self) -> None:
        results = [self._result("302009"), self._result("402014")]
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection(query="0402014")
        filtered = self.app._price_filtered_catalog_results(results)
        self.assertEqual(filtered[0]["name"], "Cama Macao, 180 x 200 cm, Natural")
        self.assertEqual(self.app._price_search_diagnostics["matched_field"], "physical_sku")
        self.assertEqual(self.app._price_search_diagnostics["top_result_physical_sku"], "0402014")
        self.assertEqual(self.app._price_search_diagnostics_history[-1]["result_count"], 1)

    def test_search_still_applies_inside_active_hierarchy_filter(self) -> None:
        results = [self._result("302009"), self._result("402014")]
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection(filter_family="Camas", query="0402014")
        filtered = self.app._price_filtered_catalog_results(results)
        self.assertEqual([row["name"] for row in filtered], ["Cama Macao, 180 x 200 cm, Natural"])

    def test_clear_keeps_literal_code_query(self) -> None:
        self.app._price_search_query = "0402014"
        self.app._price_catalog_filter_selection_state = CatalogFilterSelection(filter_family="Camas", query="0402014")
        self.app._price_catalog_applied_filter_state = self.app._price_catalog_filter_selection_state
        self.app._clear_price_catalog_filters(object())
        self.assertEqual(self.app._price_catalog_applied_filter_state, CatalogFilterSelection(query="0402014"))

    def test_price_filter_view_normalizes_only_legacy_camas_japonesas(self) -> None:
        cam = inventory_item(dict(self.snapshot.rows_by_item_id["402014"]))
        legacy = inventory_item(dict(self.snapshot.rows_by_item_id["406003"]))
        self.app._price_prepare_catalog_filter_cache([cam, legacy], 1)
        options = self.app._price_catalog_filter_options_for_selection(CatalogFilterSelection())
        counts = self.app._price_filter_option_counts["filter_family"]
        self.assertGreater(counts["Camas"], 0)
        self.assertEqual(counts.get("Camas Japonesas", 0), 0)
        self.assertIn("Camas", options["filter_family"])
        self.assertNotIn("Camas Japonesas", options["filter_family"])

    def test_new_catalog_generation_drops_old_filter_options(self) -> None:
        legacy = inventory_item(dict(self.snapshot.rows_by_item_id["406003"]))
        self.app._price_prepare_catalog_filter_cache([legacy], 1)
        self.app._price_catalog_filter_options_for_selection(CatalogFilterSelection())
        self.assertTrue(self.app._price_filter_options_cache)
        cam = inventory_item(dict(self.snapshot.rows_by_item_id["402014"]))
        self.app._price_prepare_catalog_filter_cache([cam], 2)
        options = self.app._price_catalog_filter_options_for_selection(CatalogFilterSelection())
        self.assertEqual(options["filter_family"], ["Camas"])


class ConfirmedPopupHierarchyTests(unittest.TestCase):
    def _entries(self, *, first_new_price: str = "102.00") -> list[dict[str, object]]:
        return [
            {
                "key": "product:1",
                "line": ProposalLine("A", "Articulo 1", "100.00", first_new_price, "+2", "up"),
                "source": {
                    "physical_sku": "A",
                    "popup_combination_addition_plan": {
                        "all_lines": [
                            combination("9001", [component("product:1", "A", "1")], delta="2.00"),
                            combination("9000", [component("product:1", "A", "2")], delta="2.00"),
                        ],
                    },
                },
            },
            {
                "key": "product:2",
                "line": ProposalLine("B", "Articulo 2", "100.00", "103.00", "+3", "up"),
                "source": {
                    "physical_sku": "B",
                    "popup_combination_addition_plan": {
                        "all_lines": [combination("9000", [component("product:2", "B", "1")], delta="3.00")],
                    },
                },
            },
        ]

    def _projection(self) -> dict[str, object]:
        return {
            "all_lines": [
                combination("9000", [component("product:1", "A", "2"), component("product:2", "B", "1")], delta="7.00"),
                combination("9001", [component("product:1", "A", "1")], delta="2.00"),
            ],
        }

    def test_confirmed_popup_order_is_retained_per_direct_parent(self) -> None:
        groups = project_grouped_combination_rows(self._entries(), self._projection())
        self.assertEqual([group["entry"]["line"].code for group in groups], ["A", "B"])
        self.assertEqual([child["combination_woo_id"] for child in groups[0]["children"]], ["9001", "9000"])
        self.assertEqual([child["combination_woo_id"] for child in groups[1]["children"]], ["9000"])

    def test_shared_destination_is_visual_twice_but_operational_once(self) -> None:
        projection = self._projection()
        groups = project_grouped_combination_rows(self._entries(), projection)
        shared = [group["children"][-1] for group in groups]
        self.assertEqual(len(projection["all_lines"]), 2)
        self.assertEqual([child["combination_woo_id"] for child in shared], ["9000", "9000"])
        self.assertEqual([child["accumulated_combination_delta"] for child in shared], ["7.00", "7.00"])
        self.assertEqual(shared[0]["source_component_entry_ids"], ["product:1", "product:2"])

    def test_parent_edit_updates_only_its_visual_contribution(self) -> None:
        groups = project_grouped_combination_rows(self._entries(first_new_price="103.00"), self._projection())
        self.assertEqual(groups[0]["children"][1]["contribution_from_parent_item"], "6.00")
        self.assertEqual(groups[1]["children"][0]["contribution_from_parent_item"], "3.00")

    def test_removing_parent_removes_its_group_and_keeps_shared_destination(self) -> None:
        entries = self._entries()[1:]
        projection = {"all_lines": [combination("9000", [component("product:2", "B", "1")], delta="3.00")]}
        groups = project_grouped_combination_rows(entries, projection)
        self.assertEqual([group["entry"]["line"].code for group in groups], ["B"])
        self.assertEqual([child["combination_woo_id"] for child in groups[0]["children"]], ["9000"])

    def test_editor_and_publish_preview_do_not_render_global_direct_and_derived_tables(self) -> None:
        editor_source = inspect.getsource(FutonHubErpPrototype._price_render_derived_variations)
        preview_source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertIn("popup_combination_addition_plan", inspect.getsource(project_grouped_combination_rows))
        self.assertIn("direct_entry_by_tree_id", editor_source)
        self.assertNotIn('text="Articulos seleccionados"', preview_source)
        self.assertNotIn('text="Combinaciones Woo afectadas"', preview_source)
        self.assertIn("source_component_entry_ids", preview_source)

    def test_hierarchy_paths_contain_no_remote_writes(self) -> None:
        source = "\n".join((
            inspect.getsource(project_grouped_combination_rows),
            inspect.getsource(FutonHubErpPrototype._price_filtered_catalog_results),
        ))
        for forbidden in (
            ".post(", ".put(", ".delete(", "update_inventory_item_fields",
            "create_real_price_proposal", "publish_price_proposal_group",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

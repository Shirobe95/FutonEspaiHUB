from __future__ import annotations

import csv
import inspect
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_catalog_audit import (  # noqa: E402
    CATALOG_AUDIT_COLUMNS,
    write_catalog_count_audit,
)
from futonhub.services.price_initial_live_sync import TERMINAL_SYNC_STATUSES, sync_initial_live_prices, terminal_sync_error  # noqa: E402
from futonhub.services.price_proposal_live_context import _graph_coverage_for_changes  # noqa: E402
from futonhub.ui.erp.catalog_filters import CatalogFilterSelection  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


class Woo:
    def __init__(self, entities: dict[str, dict] | None = None) -> None:
        self.entities = dict(entities or {})
        self.reads: list[str] = []

    def get(self, endpoint: str):
        self.reads.append(endpoint)
        return dict(self.entities[endpoint])


def product(woo_id: int, sku: str) -> dict:
    return {
        "id": woo_id,
        "sku": sku,
        "regular_price": "100.00",
        "sale_price": "",
        "price": "100.00",
        "status": "publish",
    }


def row(
    item_id: str,
    sku: str,
    *,
    woo_id: int | str = 1,
    record_type: str = "simple",
    is_pack: bool = False,
    operational_status: str = "",
    physical: bool = True,
) -> dict:
    source = {
        "physical_item_id": item_id if physical else "",
        "physical_sku": sku,
        "woo_id": woo_id,
        "woo_item_kind": "product",
        "woo_sku": sku,
        "operational_status": operational_status,
        "item_snapshot": {
            "item_id": item_id if physical else "",
            "item_record_type": record_type,
            "is_pack": is_pack,
        },
    }
    return {"code": sku, "name": f"Item {sku}", "cached_price": "90.00", "source": source}


class InitialSyncTerminalStateTests(unittest.TestCase):
    def test_every_visible_row_ends_with_a_terminal_state(self):
        rows = [
            row("1", "A", woo_id=1),
            row("2", "B", woo_id=""),
            row("3", "C", is_pack=True),
            row("4", "D", record_type="alias"),
            row("5", "E", operational_status="QUARANTINED_BUSINESS"),
            row("6", "F", physical=False),
        ]
        result = sync_initial_live_prices(rows, woo_client=Woo({"products/1": product(1, "A")}), session=None)

        self.assertEqual(result["counts"]["visible"], 6)
        self.assertEqual(len(result["row_outcomes"]), 6)
        self.assertEqual(result["counts"]["pending_after_completion"], 0)
        self.assertTrue(all(row["sync_status"] in TERMINAL_SYNC_STATUSES for row in result["row_outcomes"]))
        self.assertEqual(
            {row["terminal_status"] for row in result["row_outcomes"]},
            {"READY", "NO_WOO_LINK", "INELIGIBLE_RECORD_TYPE", "QUARANTINED", "MISSING_PHYSICAL_IDENTITY"},
        )

    def test_shared_destination_performs_one_get_and_fans_out_ready_context(self):
        rows = [row("1", "A", woo_id=7), row("2", "A", woo_id=7), row("3", "A", woo_id=7)]
        woo = Woo({"products/7": product(7, "A")})
        result = sync_initial_live_prices(rows, woo_client=woo, session=None)

        self.assertEqual(woo.reads, ["products/7"])
        self.assertEqual(result["counts"]["total"], 1)
        self.assertEqual(result["counts"]["ready"], 3)
        self.assertEqual(result["counts"]["deduplicated"], 2)
        for item_id in ("1", "2", "3"):
            context = result["live_price_context_by_physical_item"][item_id]
            self.assertEqual(context["sync_status"], "READY")
            self.assertEqual(context["terminal_status"], "SHARED_WOO_TARGET")
            self.assertEqual(context["shared_physical_item_ids"], ["1", "2", "3"])

    def test_global_worker_failure_still_terminalizes_the_entire_visible_catalogue(self):
        result = terminal_sync_error([row("1", "A", woo_id=1), row("2", "B", is_pack=True)], "Woo unavailable")
        self.assertEqual(result["counts"]["pending_after_completion"], 0)
        self.assertEqual(result["live_price_context_by_physical_item"]["1"]["sync_status"], "ERROR_SYNC")
        self.assertEqual(result["live_price_context_by_physical_item"]["2"]["sync_status"], "INELIGIBLE_RECORD_TYPE")

    def test_catalog_audit_serializes_each_terminal_row_without_network_access(self):
        result = sync_initial_live_prices([row("1", "A", woo_id="")], woo_client=Woo(), session=None)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_catalog_count_audit(result, stage_counts={"raw_inventory_rows": 1, "enriched_rows": 1, "unified_rows": 1}, output_dir=tmp)
            with paths["csv"].open(encoding="utf-8", newline="") as handle:
                written = list(csv.DictReader(handle))
            self.assertEqual(tuple(written[0]), CATALOG_AUDIT_COLUMNS)
            self.assertEqual(written[0]["sync_status"], "NO_WOO_LINK")
            self.assertIn("Destinos Woo únicos", paths["summary"].read_text(encoding="utf-8"))


class FilterCacheTests(unittest.TestCase):
    def _app(self) -> FutonHubErpPrototype:
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._price_filter_metadata_by_physical_item = {
            "1": {
                "item_id": "1", "code": "A", "name": "Articulo A", "filter_family": "Futones",
                "filter_group": "Algodon", "filter_size": "90x200", "filter_gama": "Natural",
            }
        }
        app._price_filter_options_cache = {}
        app._price_filter_metadata_generation = 1
        app._price_filter_performance = {}
        app._price_catalog_filter_selection_state = CatalogFilterSelection()
        app._price_catalog_applied_filter_state = CatalogFilterSelection()
        app._price_candidate_page = 0
        app._current_key = "precios"
        app._price_persist_filter_performance = lambda: None
        app._show_view = lambda *_args: self.fail("a combobox selection must not rebuild the view")
        return app

    def test_combobox_selection_updates_state_without_rebuilding_the_view(self):
        app = self._app()
        app._price_catalog_filter_selection_changed(CatalogFilterSelection(filter_family="Futones"))
        self.assertEqual(app._price_catalog_filter_selection_state.filter_family, "Futones")
        self.assertIn(("Futones", "", "", "", ""), app._price_filter_options_cache)

    def test_cached_metadata_is_used_without_snapshot_resolution(self):
        app = self._app()
        item = InventoryItem("A", "Articulo A", "1", "0", "Activo", "-", "-", "-", "A", "-", "-", "-", "-", raw={"item_id": "1"})
        metadata, strategy = app._price_catalog_metadata_for_result({"item": item})
        self.assertEqual(strategy, "session_cache")
        self.assertEqual(metadata["filter_group"], "Algodon")

    def test_filter_selection_path_has_no_remote_or_view_refresh_calls(self):
        source = inspect.getsource(FutonHubErpPrototype._price_catalog_filter_selection_changed)
        self.assertNotIn("_show_view", source)
        self.assertNotIn("search_cloud_inventory_items", source)
        self.assertNotIn("list_all_cloud_inventory_items", source)

    def test_metadata_is_resolved_once_per_catalog_generation(self):
        class Snapshot:
            def __init__(self):
                self.calls = 0

            def resolve_price_row(self, _raw):
                self.calls += 1
                return ({
                    "filter_family": "Futones", "filter_group": "Algodon", "filter_size": "90x200",
                    "filter_gama": "Natural", "heca_reference": "A", "hub_item_code": "A",
                }, "explicit_item_id")

        app = self._app()
        app._price_filter_metadata_generation = 0
        app._price_catalog_snapshot = lambda: Snapshot()
        snapshot = app._price_catalog_snapshot()
        app._price_catalog_snapshot = lambda: snapshot
        app._price_inventory_item_is_pack = lambda _item: False
        app._price_display_name_for_inventory_item = lambda item: item.name
        item = InventoryItem("A", "Articulo A", "1", "0", "Activo", "-", "-", "-", "A", "-", "-", "-", "-", raw={"item_id": "1"})

        app._price_prepare_catalog_filter_cache([item], 9)
        app._price_prepare_catalog_filter_cache([item], 9)

        self.assertEqual(snapshot.calls, 1)
        self.assertEqual(app._price_filter_metadata_generation, 9)

    def test_clear_rebuilds_the_table_once_without_losing_the_proposal(self):
        app = self._app()
        app._price_search_query = ""
        app._price_edit_selected_code = "A"
        app._price_proposal_model = {"product:1": {"keep": True}}
        calls: list[str] = []
        app._show_view = lambda key: calls.append(key)

        app._clear_price_catalog_filters(object())

        self.assertEqual(calls, ["precios"])
        self.assertEqual(app._price_edit_selected_code, "A")
        self.assertEqual(app._price_proposal_model, {"product:1": {"keep": True}})

    def test_manual_refresh_invalidates_the_filter_cache_generation(self):
        app = self._app()
        app._cloud_session = object()
        app._price_catalog_loading = False
        app._price_live_sync_in_progress = False
        app._price_loaded_once = True
        app._price_next_refresh_source = ""
        app._price_catalog_error = ""
        app._price_catalog_loaded_once = True
        app._price_catalog_items = ["test-double"]
        app._price_catalog_generation = 4
        app._price_filter_metadata_generation = 4
        app._price_filter_options_cache = {("old", "", "", "", ""): {}}
        starts: list[tuple[list[object], dict]] = []
        app._price_start_initial_live_sync = lambda items, **kwargs: starts.append((items, kwargs))

        app._refresh_price_module(object())

        self.assertEqual(app._price_catalog_generation, 5)
        self.assertEqual(app._price_filter_metadata_generation, 0)
        self.assertEqual(app._price_filter_options_cache, {})
        self.assertEqual(starts, [(["test-double"], {"force_full": True})])


class UniversalCombinationIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = CombinationPriceImpactService(ROOT.parent / "auditoria" / "out")

    def test_inverse_index_covers_every_approved_physical_identity(self):
        self.assertGreater(len(self.service.inverse_by_canonical_identity), 0)
        self.assertEqual(self.service.describe()["canonical_identity_index_size"], len(self.service.inverse_by_canonical_identity))

    def test_every_exact_component_returns_its_expected_destinations(self):
        for item_id, sku in self.service.inverse_by_canonical_identity:
            with self.subTest(item_id=item_id, sku=sku):
                expected = self.service.affected_destinations_for_identity({"physical_item_id": item_id, "physical_sku": sku})
                impact = self.service.impact_for_changes([{
                    "physical_item_id": item_id,
                    "physical_sku": sku,
                    "old_price": "10.00",
                    "new_price": "11.00",
                }])
                expected_ids = {row["combination_woo_id"] for row in expected["destinations"]}
                returned_ids = {row["combination_woo_id"] for row in impact["included_combinations"]}
                self.assertEqual(returned_ids, expected_ids)
                self.assertEqual(len(returned_ids), len(impact["included_combinations"]))

    def test_exact_literal_suffix_identity_is_preserved(self):
        resolved = self.service.resolve_canonical_identity({"physical_sku": "0726007A"})
        self.assertEqual(resolved["resolution_status"], "RESOLVED_EXACT")
        self.assertEqual(resolved["canonical_physical_sku"], "0726007A")

    def test_unresolved_identity_is_blocked_instead_of_approximated(self):
        result = self.service.affected_destinations_for_identity({"physical_item_id": "unknown", "physical_sku": "A"})
        self.assertEqual(result["status"], "IDENTITY_MISMATCH")
        self.assertEqual(result["resolution_status"], "IDENTITY_NOT_FOUND")

    def test_zero_destinations_by_design_is_allowed_but_a_missing_expected_set_is_blocked(self):
        no_combo_identity = next(identity for identity, rows in self.service.inverse_by_canonical_identity.items() if not rows)
        no_combo = _graph_coverage_for_changes(
            self.service,
            [{"physical_item_id": no_combo_identity[0], "physical_sku": no_combo_identity[1]}],
            {"included_combinations": []},
        )
        expected_identity = next(identity for identity, rows in self.service.inverse_by_canonical_identity.items() if rows)
        missing = _graph_coverage_for_changes(
            self.service,
            [{"physical_item_id": expected_identity[0], "physical_sku": expected_identity[1]}],
            {"included_combinations": []},
        )
        self.assertEqual(no_combo[0]["status"], "NO_COMBINATIONS_BY_DESIGN")
        self.assertEqual(missing[0]["status"], "BLOCKED_GRAPH_COVERAGE")

    def test_index_and_audit_path_have_no_family_specific_logic_or_clients(self):
        source = inspect.getsource(sys.modules[CombinationPriceImpactService.__module__])
        self.assertNotIn("Tatamis", source)
        self.assertNotIn("WooCommerceClient", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn(".table(", source)


if __name__ == "__main__":
    unittest.main()

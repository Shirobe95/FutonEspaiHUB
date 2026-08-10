from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_initial_live_sync import sync_initial_live_prices  # noqa: E402
from futonhub.services.price_proposal_live_context import project_grouped_combination_rows  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem, ProposalLine  # noqa: E402


def product(woo_id: int, sku: str, price: str = "134.90") -> dict:
    return {
        "id": woo_id,
        "sku": sku,
        "name": f"Articulo {sku}",
        "status": "publish",
        "regular_price": "165.00",
        "sale_price": price,
        "price": price,
        "on_sale": True,
        "date_on_sale_from": "2026-08-01T00:00:00",
        "date_on_sale_to": "2026-08-31T23:59:59",
        "date_modified_gmt": "2026-08-06T08:00:00",
    }


class Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if row.get(key) == value]
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=[dict(row) for row in self.rows])


class ReadOnlySupabase:
    def __init__(self):
        self.client = self
        self.calls = []

    def table(self, name):
        self.calls.append(name)
        return Query([])

    def insert(self, *_args, **_kwargs):  # pragma: no cover - safety tripwire
        raise AssertionError("unexpected write")

    update = insert
    upsert = insert
    delete = insert


class Woo:
    def __init__(self, entities=None, *, fail_ids=()):
        self.entities = dict(entities or {})
        self.fail_ids = {str(value) for value in fail_ids}
        self.reads = []

    def get(self, endpoint, params=None):
        self.reads.append((endpoint, dict(params or {})))
        if endpoint == "products":
            sku = (params or {}).get("sku")
            return [dict(row) for row in self.entities.values() if row.get("sku") == sku]
        if endpoint.rsplit("/", 1)[-1] in self.fail_ids:
            raise RuntimeError("Woo unavailable")
        return dict(self.entities[endpoint])


def row(item_id="201001", sku="0201001", woo_id=4548, cached_price="99.00") -> dict:
    return {
        "code": sku,
        "name": f"Articulo {sku}",
        "cached_price": cached_price,
        "source": {
            "physical_item_id": item_id,
            "physical_sku": sku,
            "woo_id": woo_id,
            "woo_item_kind": "product",
            "woo_sku": sku,
            "item_snapshot": {"item_id": item_id, "item_record_type": "simple", "is_pack": False},
        },
    }


class PriceComb001B8InitialLiveSyncTests(unittest.TestCase):
    def _sync(self, rows, woo=None, events=None):
        woo = woo or Woo({"products/4548": product(4548, "0201001")})
        result = sync_initial_live_prices(
            rows,
            woo_client=woo,
            session=ReadOnlySupabase(),
            progress_callback=(events.append if events is not None else None),
        )
        return result, woo

    # 1. The initial service is an explicit read-only entrypoint.
    def test_initial_sync_has_read_only_mode(self):
        result, _woo = self._sync([row()])
        self.assertEqual(result["mode"], "READ_ONLY_GET_AND_SELECT")
        self.assertEqual(result["writes"], {"woo": 0, "supabase": 0, "sql": 0})

    # 2. Each exact Woo destination is read only once.
    def test_deduplicates_exact_woo_destination(self):
        duplicate = row("201002")
        result, woo = self._sync([row(), duplicate])
        self.assertEqual(result["counts"]["total"], 1)
        self.assertEqual(result["counts"]["deduplicated"], 1)
        self.assertEqual([endpoint for endpoint, _params in woo.reads].count("products/4548"), 1)

    # 3. The live context retains the required operational fields.
    def test_context_contains_woo_price_fields(self):
        result, _woo = self._sync([row()])
        context = result["live_price_context_by_physical_item"]["201001"]
        self.assertEqual(context["effective_price"], "134.90")
        self.assertEqual(context["regular_price"], "165.00")
        self.assertEqual(context["sale_price"], "134.90")
        self.assertEqual(context["price_source"], "WOO_LIVE")
        self.assertEqual(context["sync_status"], "READY")

    # 4. Progress exposes processed and total counters.
    def test_progress_exposes_processed_and_total(self):
        events = []
        self._sync([row()], events=events)
        self.assertTrue(events)
        self.assertEqual(events[-1]["counts"]["processed"], 1)
        self.assertEqual(events[-1]["counts"]["total"], 1)

    # 5. An absent literal Woo link is visible but not price-eligible.
    def test_missing_link_is_not_calculated_from_cache(self):
        unlinked = row()
        unlinked["source"].pop("woo_id")
        result, woo = self._sync([unlinked])
        context = result["live_price_context_by_physical_item"]["201001"]
        self.assertEqual(context["sync_status"], "NO_WOO_LINK")
        self.assertEqual(context["effective_price"], "")
        self.assertEqual(woo.reads, [])

    # 6. A GET failure remains an ERROR_SYNC row with no fallback price.
    def test_get_error_is_visible_without_cached_price_fallback(self):
        result, _woo = self._sync([row()], Woo({"products/4548": product(4548, "0201001")}, fail_ids={4548}))
        context = result["live_price_context_by_physical_item"]["201001"]
        self.assertEqual(context["sync_status"], "ERROR_SYNC")
        self.assertEqual(context["effective_price"], "")
        self.assertEqual(context["stored_price"], "99.00")

    # 6b. Private Woo keeps its exact identity but cannot become a price target.
    def test_private_woo_entity_is_terminal_and_not_price_eligible(self):
        private = product(4548, "0201001")
        private["status"] = "private"
        result, _woo = self._sync([row()], Woo({"products/4548": private}))
        context = result["live_price_context_by_physical_item"]["201001"]
        self.assertEqual(context["sync_status"], "PRIVATE_WOO_ENTITY")
        self.assertEqual(context["price_change_eligible"], "NO")
        self.assertEqual(context["effective_price"], "")
        self.assertEqual(result["counts"]["private"], 1)

    # 7. Error keys are retained for the targeted retry action.
    def test_error_physical_ids_are_reported(self):
        result, _woo = self._sync([row()], Woo({"products/4548": product(4548, "0201001")}, fail_ids={4548}))
        self.assertEqual(result["error_physical_item_ids"], ["201001"])

    # 8. Initial sync never prefetches combination endpoints.
    def test_initial_sync_does_not_prefetch_combinations(self):
        _result, woo = self._sync([row()])
        self.assertFalse(any("/variations/" in endpoint for endpoint, _params in woo.reads))

    # 9. The visible table selects effective Woo price after the context exists.
    def test_results_use_effective_price_from_live_context(self):
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._price_live_price_context_by_physical_item = {
            "201001": {"sync_status": "READY", "effective_price": "134.90", "price_source": "WOO_LIVE", "woo_id": 4548, "woo_item_kind": "product", "woo_sku": "0201001"},
        }
        app._price_live_price_traces = []
        app._price_live_sync_required = True
        item = InventoryItem("0201001", "Tatami", "99.00", "0", "Activo", "Tatamis", "-", "-", "0201001", "-", "-", "-", "-", "-", raw={"item_id": "201001", "hub_item_code": "0201001", "woo_id": 4548, "woo_item_kind": "product", "woo_sku": "0201001", "item_record_type": "simple"})
        result = app._price_results_from_items([item])[0]
        self.assertEqual(result["price"], "134.90")
        self.assertEqual(result["cached_price"], "99.00")

    # 10. Filtering preserves the same result object and Woo price.
    def test_filter_keeps_woo_price(self):
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._price_catalog_applied_filter_state = SimpleNamespace(has_hierarchy=False)
        app._price_live_price_traces = []
        result = {"code": "0201001", "price": "134.90", "source": {"live_price_context": {"effective_price": "134.90", "sync_status": "READY", "price_source": "WOO_LIVE"}}}
        self.assertEqual(app._price_filtered_catalog_results([result])[0]["price"], "134.90")

    # 11. An ERROR_SYNC result is rejected before proposal calculation.
    def test_error_sync_is_not_eligible_for_proposal(self):
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._price_live_sync_required = True
        status, reason, price = app._price_classify_result({"type": "Simple", "price": "ERROR_SYNC", "source": {"price_sync_status": "ERROR_SYNC", "live_price_context": {"error": "timeout"}}})
        self.assertEqual(status, "ERROR")
        self.assertIn("ERROR_SYNC", reason)
        self.assertIsNone(price)

    # 12. The workspace starts its direct Woo sync as part of initial loading.
    def test_editor_finishes_items_by_starting_initial_sync(self):
        source = inspect.getsource(FutonHubErpPrototype._finish_price_edit_items)
        self.assertIn("_price_start_initial_live_sync", source)
        self.assertIn("missing_context_items", source)

    # 13. The UI keeps progress and retry without rendering technical counters.
    def test_sync_ui_has_progress_and_retry_without_technical_counters(self):
        source = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)
        self.assertIn("Reintentar errores", source)
        self.assertIn("Cargando precios...", source)
        self.assertNotIn("sin enlace", source)
        self.assertNotIn("destinos Woo", source)

    # 14. The worker uses after rather than touching Tk widgets itself.
    def test_initial_sync_worker_returns_to_main_loop(self):
        source = inspect.getsource(FutonHubErpPrototype._price_start_initial_live_sync)
        scheduler = inspect.getsource(FutonHubErpPrototype._price_schedule_live_sync_callback)
        self.assertIn("threading.Thread", source)
        self.assertIn("_price_schedule_live_sync_callback", source)
        self.assertIn("self.after(0", scheduler)
        self.assertIn("tk.TclError", scheduler)
        self.assertIn("progress_callback=progress", source)

    # 15. Add starts an overlay before launching the slow read worker.
    def test_add_uses_overlay_before_worker(self):
        source = inspect.getsource(FutonHubErpPrototype._price_add_rows_to_proposal)
        self.assertLess(source.index("_price_start_working_overlay"), source.index("threading.Thread"))
        self.assertIn("Resolviendo identidad, relaciones y combinaciones Woo", source)

    # 16. The add worker does not mutate the proposal before its popup review.
    def test_add_opens_popup_only_after_worker_finish(self):
        source = inspect.getsource(FutonHubErpPrototype._price_add_rows_to_proposal)
        self.assertLess(source.index("def finish"), source.index("def worker"))
        self.assertIn("self._open_price_item_impact_popup(prepared)", source)
        self.assertIn("progress_callback=progress", source)

    # 17. A direct parent is followed by its combination children.
    def test_grouped_projection_attaches_children_to_direct_parent(self):
        entries = [{"key": "product:1", "line": ProposalLine("A", "A", "10", "11", "+1", "up"), "source": {"physical_sku": "A"}}]
        projection = {"all_lines": [{"combination_woo_id": "10", "component_delta": "1.00", "proposal_trace_keys": ["product:1"], "modified_components": [{"proposal_trace_key": "product:1", "quantity": "1"}]}]}
        groups = project_grouped_combination_rows(entries, projection)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["children"][0]["combination_woo_id"], "10")

    # 18. A shared destination is projected beneath every responsible parent.
    def test_shared_combination_is_projected_below_each_parent(self):
        entries = [
            {"key": "product:1", "line": ProposalLine("A", "A", "10", "11", "+1", "up"), "source": {"physical_sku": "A"}},
            {"key": "product:2", "line": ProposalLine("B", "B", "20", "22", "+2", "up"), "source": {"physical_sku": "B"}},
        ]
        projection = {"all_lines": [{"combination_woo_id": "10", "component_delta": "3.00", "proposal_trace_keys": ["product:1", "product:2"], "modified_components": [{"proposal_trace_key": "product:1", "quantity": "1"}, {"proposal_trace_key": "product:2", "quantity": "1"}]}]}
        groups = project_grouped_combination_rows(entries, projection)
        self.assertEqual([len(group["children"]) for group in groups], [1, 1])
        self.assertEqual(groups[0]["children"][0]["shared_with_physical_skus"], "A | B")

    # 19. Shared visual rows retain their per-parent contribution and total delta.
    def test_shared_projection_exposes_contribution_and_accumulated_delta(self):
        entries = [{"key": "product:1", "line": ProposalLine("A", "A", "10", "11", "+1", "up"), "source": {"physical_sku": "A"}}]
        projection = {"all_lines": [{"combination_woo_id": "10", "component_delta": "2.00", "proposal_trace_keys": ["product:1"], "modified_components": [{"proposal_trace_key": "product:1", "quantity": "2"}]}]}
        child = project_grouped_combination_rows(entries, projection)[0]["children"][0]
        self.assertEqual(child["contribution_from_parent_item"], "2.00")
        self.assertEqual(child["accumulated_combination_delta"], "2.00")

    # 20. The grouped editor keeps the bounded scroll required by the proposal panel.
    def test_grouped_editor_has_parent_nodes_and_scroll(self):
        source = inspect.getsource(FutonHubErpPrototype._price_render_derived_variations)
        self.assertIn("DIRECTO:", source)
        self.assertIn("tree.insert(parent_item", source)
        self.assertIn("orient=tk.VERTICAL", source)
        self.assertIn('tree.bind("<MouseWheel>"', source)

    # 21. Deleting or editing rebuilds from the canonical model, not a second persistence projection.
    def test_editor_rebuilds_grouping_from_canonical_model(self):
        source = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)
        self.assertIn("model_entries = self._price_model_entries()", source)
        self.assertIn("derived_projection = self._price_derived_projection(model_entries)", source)
        self.assertIn("_price_render_derived_variations(list_host, derived_projection, model_entries)", source)

    # 22. Historical details keep header/footer fixed around a scrollable centre.
    def test_saved_detail_has_fixed_actions_and_scrollable_center(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn("scroll_canvas", source)
        self.assertIn("orient=tk.VERTICAL", source)
        self.assertIn('scroll_canvas.bind("<MouseWheel>"', source)
        self.assertIn("footer.grid(row=2", source)


if __name__ == "__main__":
    unittest.main()

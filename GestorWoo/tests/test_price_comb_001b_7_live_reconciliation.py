from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_combination_live_reconciliation import (  # noqa: E402
    ReadOnlyAccessError,
    live_price_trace,
    make_read_only_session,
    reconcile_live_combination_plan,
    resolve_live_direct_identity,
)
from futonhub.services.price_proposal_live_context import (  # noqa: E402
    prepare_price_addition,
    project_persisted_derived_rows,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import ProposalLine  # noqa: E402


def product(woo_id: int, sku: str, price: str = "134.90") -> dict:
    return {
        "id": woo_id,
        "sku": sku,
        "name": f"Producto {sku}",
        "status": "publish",
        "regular_price": "" if price == "" else "165.00",
        "sale_price": price,
        "price": price,
        "on_sale": True,
        "date_on_sale_from": None,
        "date_on_sale_to": None,
        "date_modified_gmt": "2026-08-06T08:00:00",
        "attributes": [],
    }


def variation(woo_id: int, parent_id: int, sku: str, price: str = "730.70") -> dict:
    return {
        **product(woo_id, sku, price),
        "parent_id": parent_id,
    }


class Query:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.filters = []

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self.filters.append(("in", key, set(values)))
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        rows = self.rows
        for kind, key, value in self.filters:
            if kind == "eq":
                rows = [row for row in rows if row.get(key) == value]
            else:
                rows = [row for row in rows if row.get(key) in value]
        return SimpleNamespace(data=[dict(row) for row in rows])


class Supabase:
    def __init__(self, tables=None):
        self.tables = tables or {}

    def table(self, name):
        return Query(self.tables.get(name, []))


class Woo:
    def __init__(self, products=None, variations=None):
        self.products = products or {}
        self.variations = variations or {}
        self.reads = []

    def get(self, endpoint, params=None):
        self.reads.append((endpoint, dict(params or {})))
        if endpoint == "products":
            sku = (params or {}).get("sku")
            return [dict(row) for row in self.products.values() if row.get("sku") == sku]
        if endpoint.startswith("products/") and "/variations/" in endpoint:
            return dict(self.variations[endpoint])
        if endpoint.startswith("products/"):
            return dict(self.products[endpoint])
        raise AssertionError(endpoint)


class GraphWoo(Woo):
    def __init__(self, service: CombinationPriceImpactService, *, missing_id: str = ""):
        super().__init__()
        self.service = service
        self.missing_id = missing_id

    def get(self, endpoint, params=None):
        self.reads.append((endpoint, dict(params or {})))
        if endpoint.startswith("products/") and "/variations/" in endpoint:
            woo_id = endpoint.rsplit("/", 1)[-1]
            if woo_id == self.missing_id:
                return variation(int(woo_id), int(endpoint.split("/")[1]), "", "")
            source = self.service.combination_by_id[woo_id]
            return variation(int(woo_id), int(source["combination_parent_woo_id"]), source["combination_sku"])
        return super().get(endpoint, params)


class PriceComb001B7LiveReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.service = CombinationPriceImpactService(ROOT.parent / "auditoria" / "out")
        self.session = make_read_only_session(Supabase({
            "products": [],
            "product_variations": [],
            "inventory_items": [
                {"item_id": 201001, "name": "Tatami, 80 x 200 x 5,5 cm."},
                {"item_id": 201002, "name": "Tatami, 90 x 200 x 5,5 cm"},
            ],
        }))

    def _direct_woo(self, sku="0201001", woo_id=4548, price="134.90"):
        return Woo({f"products/{woo_id}": product(woo_id, sku, price), f"lookup:{sku}": product(woo_id, sku, price)})

    def _with_product_lookup(self, sku="0201001", woo_id=4548, price="134.90"):
        woo = self._direct_woo(sku, woo_id, price)
        original = woo.get

        def get(endpoint, params=None):
            if endpoint == "products":
                woo.reads.append((endpoint, dict(params or {})))
                return [product(woo_id, sku, price)]
            return original(endpoint, params)

        woo.get = get
        return woo

    def _change(self, sku="0201001", item_id="201001"):
        return [{
            "physical_item_id": item_id,
            "physical_sku": sku,
            "old_price": "134.90",
            "new_price": "135.90",
            "proposal_key": f"product:{sku}",
        }]

    # 1. A direct local test id is never an operational identity.
    def test_real_identity_is_not_taken_from_fake_local_id(self):
        resolved = resolve_live_direct_identity("201001", "0201001", session=self.session, woo_client=self._with_product_lookup())
        self.assertEqual(resolved["woo_id"], 4548)
        self.assertEqual(resolved["resolution_source"], "WOO_EXACT_SKU")

    # 2. Exact products and exact replica variations both resolve.
    def test_product_and_variation_exact_resolution(self):
        product_result = resolve_live_direct_identity("201001", "0201001", session=self.session, woo_client=self._with_product_lookup())
        variation_session = make_read_only_session(Supabase({
            "products": [],
            "product_variations": [{"woo_id": 3667, "parent_woo_id": 3612, "sku": "0302018|0201001|0201001"}],
        }))
        woo = Woo(variations={"products/3612/variations/3667": variation(3667, 3612, "0302018|0201001|0201001")})
        variation_result = resolve_live_direct_identity("302018", "0302018|0201001|0201001", session=variation_session, woo_client=woo)
        self.assertEqual(product_result["woo_item_kind"], "product")
        self.assertEqual(variation_result["woo_item_kind"], "variation")

    def test_woo_exact_sku_variation_is_classified_with_parent_endpoint(self):
        sku = "0201010"
        woo = Woo(
            products={"lookup": variation(12345, 900, sku, "137.90")},
            variations={"products/900/variations/12345": variation(12345, 900, sku, "137.90")},
        )

        result = resolve_live_direct_identity("201010", sku, session=None, woo_client=woo)

        self.assertEqual(result["resolution_status"], "RESOLVED")
        self.assertEqual(result["resolution_source"], "WOO_EXACT_SKU")
        self.assertEqual(result["woo_item_kind"], "variation")
        self.assertEqual(result["woo_parent_id"], "900")
        self.assertEqual(result["woo_endpoint"], "products/900/variations/12345")
        self.assertNotIn(("products/12345", {}), woo.reads)

    # 3. The exact Woo endpoint is retained in the trace.
    def test_endpoint_is_logged(self):
        trace = live_price_trace("201001", "0201001", session=self.session, woo_client=self._with_product_lookup())
        self.assertEqual(trace["woo_endpoint"], "products/4548")

    # 4. Effective current price is the price returned by Woo.
    def test_price_matches_woo_response(self):
        trace = live_price_trace("201001", "0201001", session=self.session, woo_client=self._with_product_lookup(price="134.90"))
        self.assertEqual(trace["final_old_price"], 134.9)
        self.assertEqual(trace["woo_effective_price"], "134.90")

    # 5. A cached value is diagnostic only, never calculation input.
    def test_cache_is_not_used_for_calculation(self):
        trace = live_price_trace("201001", "0201001", displayed_price="1.00", supabase_cached_price="1.00", session=self.session, woo_client=self._with_product_lookup())
        self.assertEqual(trace["supabase_cached_price"], "1.00")
        self.assertEqual(trace["final_old_price"], 134.9)

    # 6. An empty effective Woo price blocks the direct row.
    def test_missing_woo_price_blocks_direct_row(self):
        trace = live_price_trace("201001", "0201001", session=self.session, woo_client=self._with_product_lookup(price=""))
        self.assertEqual(trace["status"], "BLOCKED_LIVE_PRICE_UNAVAILABLE")
        self.assertIsNone(trace["final_old_price"])

    # 7. The approved graph has 18 operational candidates for 0201001.
    def test_reconciles_18_candidates_for_0201001_individually(self):
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service), session=self.session)
        self.assertEqual(result["counts"]["candidates"], 18)
        self.assertEqual(result["counts"]["valid"], 18)
        self.assertEqual(result["counts"]["quarantined"], 78)

    # 8. The approved graph has 19 operational candidates for 0201002.
    def test_reconciles_19_candidates_for_0201002_individually(self):
        result = reconcile_live_combination_plan(self._change("0201002", "201002"), impact_service=self.service, woo_client=GraphWoo(self.service), session=self.session)
        self.assertEqual(result["counts"]["candidates"], 19)
        self.assertEqual(result["counts"]["valid"], 19)

    # 9. Only VALID variation rows form the applicable proposal projection.
    def test_only_valid_rows_enter_proposal(self):
        first = self.service.impact_for_changes(self._change())["included_combinations"][0]["combination_woo_id"]
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service, missing_id=str(first)), session=self.session)
        self.assertTrue(all(row["validation_status"] == "VALID" for row in result["derived_lines"]))
        self.assertEqual(len(result["derived_lines"]), 17)

    # 10. Missing prices/errors stay visible in a distinct blocked collection.
    def test_blocked_rows_are_separate_from_valid_rows(self):
        first = self.service.impact_for_changes(self._change())["included_combinations"][0]["combination_woo_id"]
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service, missing_id=str(first)), session=self.session)
        self.assertEqual(len(result["blocked_lines"]), 1)
        self.assertEqual(result["blocked_lines"][0]["included_in_proposal"], "NO")

    # 11. Component labels come from an exact inventory item_id lookup.
    def test_component_names_are_resolved(self):
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service), session=self.session)
        component = result["derived_lines"][0]["modified_components"][0]
        self.assertEqual(component["component_name_status"], "RESOLVED")
        self.assertIn("Tatami", component["component_name"])

    # 12. Component quantities survive reconciliation unchanged.
    def test_component_quantity_is_preserved(self):
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service), session=self.session)
        self.assertEqual(result["derived_lines"][0]["modified_components"][0]["quantity"], "2")

    # 13. Modified components are marked for visible UI emphasis.
    def test_modified_component_is_highlightable(self):
        result = reconcile_live_combination_plan(self._change(), impact_service=self.service, woo_client=GraphWoo(self.service), session=self.session)
        self.assertEqual(result["derived_lines"][0]["modified_components"][0]["is_modified"], "YES")

    # 14. The review popup owns vertical scroll plus mouse/keyboard navigation.
    def test_popup_has_vertical_scroll_navigation(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_item_impact_popup)
        self.assertIn("orient=tk.VERTICAL", source)
        self.assertIn('impact_tree.bind("<MouseWheel>"', source)
        self.assertIn('impact_tree.bind("<Prior>"', source)

    # 15. The main derived block has its own bounded vertical scroller.
    def test_main_derived_list_has_vertical_scroll_navigation(self):
        source = inspect.getsource(FutonHubErpPrototype._price_render_derived_variations)
        self.assertIn("tree_host.pack_propagate(False)", source)
        self.assertIn('tree.bind("<MouseWheel>"', source)
        self.assertIn("yscroll", source)

    # 16. The popup footer remains outside the scroll host.
    def test_popup_buttons_remain_accessible(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_item_impact_popup)
        self.assertIn("footer.grid(row=2", source)
        self.assertIn("impact_host.grid(row=1", source)

    # 17. A reopened draft renders its saved validation snapshot before refresh.
    def test_reopen_preserves_validation_snapshot(self):
        entry = {
            "key": "product:4548",
            "line": ProposalLine("0201001", "Tatami", "134.90", "135.90", "+1", "up"),
            "source": {"physical_item_id": "201001", "physical_sku": "0201001", "combination_addition_plan": {
                "all_lines": [{"combination_woo_id": "3667", "validation_status": "VALID"}, {"combination_woo_id": "3668", "validation_status": "PRICE_MISSING"}],
            }},
        }
        projection = project_persisted_derived_rows([entry], impact_service=self.service)
        self.assertEqual(projection["read_validation_snapshot"], "PERSISTED")
        self.assertEqual(len(projection["derived_lines"]), 1)
        self.assertEqual(len(projection["blocked_lines"]), 1)

    # 17b. Reopen schedules a fresh Woo-only reconciliation after the snapshot.
    def test_reopen_schedules_fresh_read_only_reconciliation(self):
        source = inspect.getsource(FutonHubErpPrototype._price_schedule_reopened_live_reconciliation)
        self.assertIn("live_price_trace(", source)
        self.assertIn("reconcile_live_combination_plan(", source)
        self.assertIn("make_read_only_session(session)", source)
        self.assertIn("threading.Thread", source)

    # 18. Combined graph impact deduplicates a Woo variation destination.
    def test_combined_graph_has_no_duplicate_woo_ids(self):
        result = reconcile_live_combination_plan(
            [*self._change(), *self._change("0201002", "201002")],
            impact_service=self.service,
            woo_client=GraphWoo(self.service),
            session=self.session,
        )
        ids = [row["combination_woo_id"] for row in result["derived_lines"]]
        self.assertEqual(len(ids), len(set(ids)))

    # 19. The read-only client guard rejects every mutation method.
    def test_read_only_guard_rejects_real_writes(self):
        with self.assertRaises(ReadOnlyAccessError):
            self.session.client.table("inventory_items").update({"name": "blocked"})

    # 20. UI-prepared counters derive from the same validated popup data.
    def test_ui_counts_agree_with_validated_popup_data(self):
        woo = self._with_product_lookup()
        prepared = prepare_price_addition(
            [{"code": "0201001", "cached_price": "1.00", "source": {"physical_item_id": "201001", "physical_sku": "0201001"}}],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=self.service,
            woo_client=woo,
            session=None,
        )
        # Without a replica row the direct Woo product still resolves through
        # exact Woo, while combination reads receive a deliberate fake error.
        self.assertEqual(prepared["counts"]["derived"], (prepared["popup_combination_plan"].get("counts") or {}).get("candidates"))


if __name__ == "__main__":
    unittest.main()

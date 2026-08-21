from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_proposal_live_context import (  # noqa: E402
    prepare_price_addition,
    project_persisted_derived_rows,
    resolve_direct_woo_target,
    validate_incremental_destination,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import ProposalLine  # noqa: E402


class Query:
    def __init__(self, rows):
        self.rows = list(rows)
        self.equals = []

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.equals.append((key, value))
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        rows = self.rows
        for key, value in self.equals:
            rows = [row for row in rows if row.get(key) == value]
        return SimpleNamespace(data=[dict(row) for row in rows])


class Session:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.client = self

    def table(self, name):
        return Query(self.tables.get(name, []))


class Woo:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.reads = []

    def get(self, endpoint, params=None):
        key = (endpoint, tuple(sorted((params or {}).items()))) if params else endpoint
        self.reads.append(key)
        response = self.responses.get(key, self.responses.get(endpoint))
        if isinstance(response, Exception):
            raise response
        return response


def product(woo_id, sku, price="150.00"):
    return {
        "id": woo_id,
        "sku": sku,
        "regular_price": price,
        "sale_price": "",
        "price": price,
        "on_sale": False,
        "date_on_sale_from": None,
        "date_on_sale_to": None,
        "status": "publish",
        "stock_status": "instock",
        "manage_stock": False,
        "stock_quantity": None,
        "attributes": [],
        "date_modified_gmt": "2026-08-05T10:00:00",
    }


def variation(woo_id, parent_id, sku, price="150.00"):
    row = product(woo_id, sku, price)
    row["type"] = "variation"
    row["parent_id"] = parent_id
    return row


def variation_context():
    return {
        "id": 13092,
        "parent_id": 3658,
        "sku": "0201001|0201001|1249001|1249001|0619007|0619007",
        "regular_price": "950.00",
        "sale_price": "749.90",
        "price": "749.90",
        "on_sale": True,
        "date_on_sale_from": None,
        "date_on_sale_to": None,
        "date_modified_gmt": "2026-08-05T10:00:00",
    }


class FixedImpact:
    def impact_for_changes(self, changes):
        components = []
        total = 0.0
        for change in changes:
            total += float(change["new_price"]) - float(change["old_price"])
            components.append({
                "component_item_id": str(change["physical_item_id"]),
                "component_sku": str(change["physical_sku"]),
                "proposal_trace_key": str(change["proposal_key"]),
                "quantity": "1",
            })
        return {
            "included_combinations": [{
                "combination_woo_id": "13092",
                "combination_parent_woo_id": "3658",
                "combination_sku": variation_context()["sku"],
                "combination_name": "Combinacion exacta",
                "component_delta": f"{total:.2f}",
                "modified_components": components,
                "proposal_trace_keys": [row["proposal_trace_key"] for row in components],
                "excluded": "NO",
            }],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "counts": {},
        }


class PriceComb001B6DirectResolutionTests(unittest.TestCase):
    def source(self, *, woo_id=9001, sku="0201001"):
        return {
            "physical_item_id": "201001",
            "physical_sku": sku,
            "woo_id": woo_id,
            "woo_item_kind": "product",
            "woo_sku": sku,
        }

    def test_local_graph_exact_resolution_wins(self):
        result = resolve_direct_woo_target("201001", "0201001", source=self.source())
        self.assertEqual(result["resolution_status"], "RESOLVED")
        self.assertEqual(result["resolution_source"], "LOCAL_GRAPH_EXACT")
        self.assertEqual(result["woo_id"], 9001)

    def test_local_graph_requires_literal_woo_sku(self):
        source = self.source(sku="0201001")
        source["woo_sku"] = "0201001-X"
        result = resolve_direct_woo_target("201001", "0201001", source=source)
        self.assertEqual(result["resolution_status"], "NOT_FOUND")

    def test_replica_exact_resolution_is_used_without_local_link(self):
        session = Session({"products": [{"woo_id": 9001, "sku": "0201001"}]})
        result = resolve_direct_woo_target("201001", "0201001", session=session)
        self.assertEqual(result["resolution_source"], "SUPABASE_EXACT_REPLICA")
        self.assertEqual(result["woo_id"], 9001)

    def test_replica_ambiguous_target_is_blocked(self):
        session = Session({
            "products": [{"woo_id": 9001, "sku": "0201001"}],
            "product_variations": [{"woo_id": 9002, "parent_woo_id": 10, "sku": "0201001"}],
        })
        result = resolve_direct_woo_target("201001", "0201001", session=session)
        self.assertEqual(result["resolution_status"], "AMBIGUOUS")

    def test_woo_exact_sku_resolution_is_used_last(self):
        lookup = ("products", (("per_page", 100), ("sku", "0201001")))
        woo = Woo({lookup: [product(9001, "0201001")]})
        result = resolve_direct_woo_target("201001", "0201001", woo_client=woo)
        self.assertEqual(result["resolution_source"], "WOO_EXACT_SKU")
        self.assertEqual(result["woo_id"], 9001)

    def test_woo_exact_sku_variation_keeps_parent_identity(self):
        lookup = ("products", (("per_page", 100), ("sku", "0201010")))
        woo = Woo({lookup: [variation(12345, 900, "0201010")]})

        result = resolve_direct_woo_target("201010", "0201010", woo_client=woo)

        self.assertEqual(result["resolution_status"], "RESOLVED")
        self.assertEqual(result["resolution_source"], "WOO_EXACT_SKU")
        self.assertEqual(result["woo_item_kind"], "variation")
        self.assertEqual(result["woo_id"], 12345)
        self.assertEqual(result["woo_parent_id"], "900")

    def test_woo_exact_sku_multiple_matches_are_blocked(self):
        lookup = ("products", (("per_page", 100), ("sku", "0201001")))
        woo = Woo({lookup: [product(9001, "0201001"), product(9002, "0201001")]})
        result = resolve_direct_woo_target("201001", "0201001", woo_client=woo)
        self.assertEqual(result["resolution_status"], "AMBIGUOUS")

    def test_missing_direct_target_is_not_calculated_from_inventory_cache(self):
        prepared = prepare_price_addition(
            [{"code": "0201001", "cached_price": "128.00", "source": {"physical_item_id": "201001", "physical_sku": "0201001"}}],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=FixedImpact(),
            woo_client=Woo({}),
            session=None,
        )
        row = prepared["direct_rows"][0]
        self.assertIsNone(row["old_price_value"])
        self.assertIsNone(row["new_price_value"])
        self.assertEqual(row["woo_price_context"]["stored_price"], "128.00")
        self.assertEqual(row["apply_allowed"], "NO")

    def test_live_direct_price_is_calculated_from_resolved_woo_target(self):
        lookup = ("products", (("per_page", 100), ("sku", "0201001"), ("status", "any")))
        prepared = prepare_price_addition(
            [{"code": "0201001", "cached_price": "128.00", "source": self.source()}],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=FixedImpact(),
            # The stale local 9001 reference is deliberately ignored. A Woo
            # exact-SKU GET must resolve and price the actual target instead.
            woo_client=Woo({
                lookup: [product(4548, "0201001", "155.00")],
                "products/4548": product(4548, "0201001", "155.00"),
            }),
            session=None,
        )
        row = prepared["direct_rows"][0]
        self.assertEqual(row["old_price_value"], 155.0)
        self.assertEqual(row["new_price_value"], 156.0)
        self.assertEqual(row["woo_price_context"]["direct_resolution_source"], "WOO_EXACT_SKU")

    def test_private_direct_target_is_blocked_without_losing_traceability(self):
        lookup = ("products", (("per_page", 100), ("sku", "0201001"), ("status", "any")))
        private = product(4548, "0201001", "155.00")
        private["status"] = "private"
        prepared = prepare_price_addition(
            [{"code": "0201001", "cached_price": "128.00", "source": self.source()}],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=FixedImpact(),
            woo_client=Woo({lookup: [private], "products/4548": private}),
            session=None,
        )
        row = prepared["direct_rows"][0]
        self.assertEqual(row["status"], "PRIVATE_WOO_ENTITY")
        self.assertEqual(row["apply_allowed"], "NO")
        self.assertEqual(row["identities"]["woo_id"], 4548)

    def test_incremental_destination_requires_literal_item_and_sku(self):
        destination = {"modified_components": [{"component_item_id": "201001", "component_sku": "0201001"}]}
        self.assertTrue(validate_incremental_destination(destination, "201001", "0201001"))
        self.assertFalse(validate_incremental_destination(destination, "201001", "0201002"))
        self.assertFalse(validate_incremental_destination(destination, "201002", "0201001"))

    def test_popup_for_0201002_does_not_include_13092_without_exact_edge(self):
        service = CombinationPriceImpactService(ROOT.parent / "auditoria" / "out")
        prepared = prepare_price_addition(
            [{"code": "0201002", "source": {
                "physical_item_id": "201002", "physical_sku": "0201002", "woo_id": 9002,
                "woo_item_kind": "product", "woo_sku": "0201002",
            }}],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=service,
            woo_client=Woo({"products/9002": product(9002, "0201002")}),
            session=None,
            existing_changes=[{
                "physical_item_id": "201001", "physical_sku": "0201001",
                "old_price": "150.00", "new_price": "151.00", "proposal_key": "product:9001",
            }],
        )
        popup_ids = {row["combination_woo_id"] for row in prepared["popup_combination_plan"]["derived_lines"]}
        self.assertNotIn("13092", popup_ids)
        self.assertTrue(all(row["included_in_popup"] == "YES" for row in prepared["incremental_filter_report"]))

    def test_popup_uses_incremental_plan_not_combined_plan(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_item_impact_popup)
        self.assertIn('prepared.get("popup_combination_plan")', source)
        self.assertNotIn('prepared.get("combination_plan") or {}).get("derived_lines")', source)

    def test_confirm_keeps_full_projection_and_popup_projection(self):
        source = inspect.getsource(FutonHubErpPrototype._confirm_price_item_impact_add)
        self.assertIn("popup_combination_addition_plan", source)
        self.assertIn("combination_addition_plan", source)

    def test_direct_source_is_rehydrated_with_physical_identity(self):
        source = inspect.getsource(FutonHubErpPrototype._prepare_price_edit_state)
        self.assertIn('"physical_item_id": source_row.get("physical_item_id")', source)
        self.assertIn('"combination_addition_plan": dict(source_row.get("combination_addition_plan")', source)

    def test_main_editor_renders_a_distinct_derived_block(self):
        source = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)
        self.assertIn("_price_rendered_derived_keys", source)
        self.assertIn("_price_render_derived_variations", source)

    def test_projection_rebuilds_derived_row_from_confirmed_direct_source(self):
        plan = {"derived_lines": [{
            "combination_woo_id": "13092",
            "woo_price_context": variation_context(),
        }]}
        entries = [{
            "key": "product:9001",
            "line": ProposalLine("0201001", "Tatami", "150.00", "151.00", "+1", "up"),
            "source": {**self.source(), "combination_addition_plan": plan},
        }]
        projection = project_persisted_derived_rows(entries, impact_service=FixedImpact())
        self.assertEqual(len(projection["derived_lines"]), 1)
        self.assertEqual(projection["derived_lines"][0]["combination_woo_id"], "13092")

    def test_projection_is_deduplicated_for_multiple_direct_lines(self):
        plan = {"derived_lines": [{"combination_woo_id": "13092", "woo_price_context": variation_context()}]}
        entries = [
            {"key": "product:9001", "line": ProposalLine("0201001", "A", "150", "151", "+1", "up"), "source": {**self.source(), "combination_addition_plan": plan}},
            {"key": "product:9002", "line": ProposalLine("0201002", "B", "120", "121", "+1", "up"), "source": {
                "physical_item_id": "201002", "physical_sku": "0201002", "woo_id": 9002,
                "woo_item_kind": "product", "woo_sku": "0201002", "combination_addition_plan": plan,
            }},
        ]
        projection = project_persisted_derived_rows(entries, impact_service=FixedImpact())
        self.assertEqual([row["combination_woo_id"] for row in projection["derived_lines"]], ["13092"])

    def test_projection_does_not_fallback_to_inventory_price(self):
        source = inspect.getsource(project_persisted_derived_rows)
        self.assertNotIn('getattr(line, "price"', source)
        self.assertIn("combination_addition_plan", source)

    def test_save_persists_full_derived_projection_context(self):
        source = inspect.getsource(FutonHubErpPrototype._price_validate_and_persist_entries)
        self.assertIn('"combination_addition_plan": dict(combination_plan)', source)

    def test_reopen_refreshes_visible_projection_on_every_workspace_build(self):
        source = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)
        self.assertIn("derived_projection = self._price_derived_projection(model_entries)", source)
        self.assertIn("_price_rendered_derived_keys", source)

    def test_no_direct_woo_resolution_uses_fuzzy_matching(self):
        source = inspect.getsource(resolve_direct_woo_target)
        self.assertIn('params={"sku": sku, "per_page": 100}', source)
        self.assertIn('_text(row.get("sku")) == sku', source)
        self.assertNotIn("startswith", source)

    def test_new_physical_row_can_reach_direct_resolver_without_preloaded_woo_id(self):
        source = inspect.getsource(FutonHubErpPrototype._price_source_from_inventory_item)
        self.assertIn("Physical rows can enter the direct resolver", source)
        self.assertIn('"physical_item_id": physical_item_id', source)

    def test_direct_candidate_validation_defers_price_to_live_woo_resolution(self):
        source = inspect.getsource(FutonHubErpPrototype._price_classify_result)
        self.assertIn("La identidad Woo directa se resolvera", source)


if __name__ == "__main__":
    unittest.main()

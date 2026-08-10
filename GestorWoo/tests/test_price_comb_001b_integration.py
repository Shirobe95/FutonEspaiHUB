from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "GestorWoo" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.services.catalog_operational_baseline import (  # noqa: E402
    CatalogOperationalBaseline,
    HISTORICAL,
    OPERATIONAL,
    OUTSIDE_BASELINE,
    QUARANTINED_BUSINESS,
)
from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.combination_proposal_integration import (  # noqa: E402
    BLOCKED_MISSING_PRICE_CONTEXT,
    EXCLUDED_QUARANTINE,
    READY,
    build_combination_proposal_plan,
    derived_source_row,
)


class FixedImpact:
    def impact_for_changes(self, changes):
        return {
            "status": "READ_ONLY_PREVIEW",
            "included_combinations": [{
                "combination_woo_id": "200",
                "combination_parent_woo_id": "100",
                "combination_sku": "COMBO-200",
                "combination_name": "Combo exacto",
                "effective_current_price": "90.00",
                "component_delta": "2.00",
                "simulated_effective_price": "92.00",
                "modified_components": [{
                    "component_item_id": "10",
                    "component_sku": "SKU-10",
                    "proposal_trace_key": "product:10",
                    "quantity": "1",
                    "weighted_delta": "2.00",
                }],
                "proposal_trace_keys": ["product:10"],
                "inclusion_reason": "EXACT_COMPONENT_MATCH_IN_OPERATIONAL_GRAPH",
                "excluded": "NO",
            }],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "counts": {},
        }


class EmptyImpact:
    def impact_for_changes(self, changes):
        return {
            "included_combinations": [],
            "excluded_combinations": [],
            "unmatched_changes": [{"trace_key": "product:10", "reason": "NO_EXACT_COMPONENT_MATCH"}],
            "counts": {},
        }


class QuarantineImpact:
    def impact_for_changes(self, changes):
        return {
            "included_combinations": [],
            "excluded_combinations": [{
                "combination_woo_id": "300",
                "combination_sku": "QUAR-300",
                "combination_name": "Aislada",
                "exclusion_reason": "Business quarantine",
                "publication_allowed": "NO",
            }],
            "unmatched_changes": [],
            "counts": {},
        }


class Woo:
    def __init__(self, context):
        self.context = dict(context)
        self.reads = []

    def get(self, endpoint):
        self.reads.append(endpoint)
        return SimpleNamespace(json=lambda: dict(self.context))


def context(**updates):
    value = {
        "id": 200,
        "regular_price": "100.00",
        "sale_price": "90.00",
        "price": "90.00",
        "on_sale": True,
        "date_on_sale_from": None,
        "date_on_sale_to": None,
        "date_modified_gmt": "2026-08-05T08:00:00",
    }
    value.update(updates)
    return value


class PriceCombinationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = CatalogOperationalBaseline(ROOT / "auditoria" / "out")

    def test_baseline_keeps_188_operational_and_66_quarantined(self):
        self.assertEqual(self.baseline.describe()["operational_physical_items"], 188)
        self.assertEqual(self.baseline.describe()["quarantined_physical_items"], 66)
        self.assertEqual(self.baseline.describe()["total_physical_items"], 254)
        self.assertFalse(set(self.baseline.operational_by_item_id) & set(self.baseline.quarantine_by_item_id))

    def test_baseline_enriches_without_dropping_rows(self):
        rows = self.baseline.enrich_rows([
            {"item_id": 302009},
            {"item_id": 78009},
            {"item_id": 999999999},
        ])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["operational_status"], OPERATIONAL)
        self.assertEqual(rows[1]["operational_status"], HISTORICAL)
        self.assertEqual(rows[2]["operational_status"], OUTSIDE_BASELINE)
        self.assertTrue(rows[0]["can_participate_in_price_propagation"])
        self.assertFalse(rows[1]["can_participate_in_price_propagation"])

    def test_direct_proposal_without_combinations_is_not_blocked(self):
        plan = build_combination_proposal_plan(
            [{"woo_id": "10", "old_price": 10, "new_price": 11, "proposal_key": "product:10"}],
            impact_service=EmptyImpact(),
            woo_client=None,
        )
        self.assertEqual(plan["derived_lines"], [])
        self.assertEqual(plan["status"], READY)
        self.assertEqual(plan["counts"]["blocked"], 0)

    def test_active_sale_reuses_direct_pricing_policy(self):
        woo = Woo(context())
        plan = build_combination_proposal_plan(
            [{"woo_id": "10", "old_price": 10, "new_price": 12}],
            impact_service=FixedImpact(),
            woo_client=woo,
        )
        line = plan["derived_lines"][0]
        self.assertEqual(line["status"], READY)
        self.assertEqual(line["future_pricing_payload"], {"sale_price": "92.00"})
        self.assertEqual(line["pricing_strategy"], "sale_price")
        self.assertEqual(woo.reads, ["products/100/variations/200"])

    def test_inactive_sale_updates_regular_and_clears_sale(self):
        woo = Woo(context(regular_price="90.00", sale_price="", price="90.00", on_sale=False))
        line = build_combination_proposal_plan(
            [{"woo_id": "10", "old_price": 10, "new_price": 12}],
            impact_service=FixedImpact(),
            woo_client=woo,
        )["derived_lines"][0]
        self.assertEqual(line["future_pricing_payload"], {"regular_price": "92.00", "sale_price": ""})

    def test_missing_price_context_blocks_without_inference(self):
        woo = Woo({"id": 200, "regular_price": "100", "price": "100"})
        line = build_combination_proposal_plan(
            [{"woo_id": "10", "old_price": 10, "new_price": 12}],
            impact_service=FixedImpact(),
            woo_client=woo,
        )["derived_lines"][0]
        self.assertEqual(line["status"], BLOCKED_MISSING_PRICE_CONTEXT)
        self.assertEqual(line["publication_allowed"], "NO")
        self.assertEqual(line["future_pricing_payload"], {})

    def test_quarantine_is_reported_but_never_derived(self):
        plan = build_combination_proposal_plan(
            [{"sku": "Q", "old_price": 10, "new_price": 12}],
            impact_service=QuarantineImpact(),
            woo_client=None,
        )
        self.assertEqual(plan["derived_lines"], [])
        self.assertEqual(plan["excluded_lines"][0]["status"], EXCLUDED_QUARANTINE)

    def test_derived_source_row_contains_complete_traceability(self):
        line = build_combination_proposal_plan(
            [{"woo_id": "10", "old_price": 10, "new_price": 12}],
            impact_service=FixedImpact(),
            woo_client=Woo(context()),
        )["derived_lines"][0]
        source = derived_source_row(
            line,
            proposal_name="Prueba",
            save_token="token",
            source_proposal_ids=["proposal-direct-1"],
        )
        self.assertEqual(source["entry_origin"], "DERIVED_COMBINATION")
        self.assertEqual(source["source_component_entry_ids"], ["proposal-direct-1"])
        self.assertEqual(source["physical_item_ids"], ["10"])
        self.assertEqual(source["physical_skus"], ["SKU-10"])
        self.assertEqual(source["woo_combination_id"], 200)
        self.assertEqual(source["woo_parent_id"], 100)
        self.assertEqual(source["publication_allowed"], "YES")

    def test_real_adapter_deduplicates_multiple_component_changes(self):
        service = CombinationPriceImpactService(ROOT / "auditoria" / "out")
        raw = service.impact_for_changes([
            {"component_target_key": "201002", "old_price": 10, "new_price": 12, "proposal_key": "A"},
            {"component_target_key": "302009", "old_price": 20, "new_price": 19, "proposal_key": "B"},
        ])
        ids = [row["combination_woo_id"] for row in raw["included_combinations"]]
        self.assertEqual(len(ids), len(set(ids)))
        combo = next(row for row in raw["included_combinations"] if row["combination_woo_id"] == "3662")
        self.assertEqual(combo["component_delta"], "3.00")

    def test_new_services_have_no_persistence_or_real_network_clients(self):
        baseline_source = inspect.getsource(sys.modules[CatalogOperationalBaseline.__module__])
        integration_source = inspect.getsource(sys.modules[build_combination_proposal_plan.__module__])
        for token in (".table(", ".insert(", "requests.", "WooCommerceClient("):
            self.assertNotIn(token, baseline_source)
            self.assertNotIn(token, integration_source)


if __name__ == "__main__":
    unittest.main()

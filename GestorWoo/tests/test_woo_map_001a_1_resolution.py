from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "auditoria" / "woo_map_001a_1_resolution.py"
spec = importlib.util.spec_from_file_location("woo_map_001a_1_resolution", SCRIPT)
resolution = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = resolution
spec.loader.exec_module(resolution)


class WooMap001A1ResolutionTests(unittest.TestCase):
    def test_pending_rows_are_deduplicated_by_combination_entity(self) -> None:
        pending = [
            {"pending_type": "INCOMPLETE_WOO_COMPOSITION", "codigo": "PACK", "evidence_rows": "1"},
            {"pending_type": "WOO_COMPOSITION_DECISION", "codigo": "PACK", "evidence_rows": "1"},
        ]
        rebuilt = [{
            "woo_id": "10", "combination_sku": "PACK", "new_status": "COMPONENT_ALIAS_UNPROVEN",
            "human_decision_required": "YES", "resolution_evidence": "two source rows",
            "resolution_confidence": "LOW",
        }]
        rows = resolution.deduplicate_pending(pending, rebuilt, [], [], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_pending_rows"], 2)

    def test_parent_sku_shadowed_by_child_variation(self) -> None:
        nodes = [
            {"woo_id": "1", "parent_woo_id": "", "item_kind": "product", "product_type": "variable", "status": "publish", "sku": "DUP", "regular_price": "", "sale_price": ""},
            {"woo_id": "2", "parent_woo_id": "1", "item_kind": "variation", "product_type": "variation", "status": "publish", "sku": "DUP", "regular_price": "100", "sale_price": "90"},
        ]
        row = resolution.duplicate_sku_review(nodes, [], ["DUP"])[0]
        self.assertEqual(row["policy"], "PARENT_SKU_SHADOWED_BY_CHILD_VARIATION")
        self.assertEqual(row["publication_target"], "CHILD_VARIATION")

    def test_alias_exact_requires_explicit_exclusion_target(self) -> None:
        edges = [{"component_sku": "ITEM-A", "parent_woo_id": "10", "combination_parent_woo_id": "1", "parent_sku": "PACK", "edge_status": "BLOCKED"}]
        exclusions = [{"item_record_type": "alias", "hub_item_code": "ITEM-A", "heca_reference": "ITEM", "related_canonical_item_id": "7", "item_id": "70"}]
        physical = [{"item_id": "7", "sku": "ITEM"}]
        rows, promotions, _, promoted = resolution.resolve_aliases(edges, exclusions, physical)
        self.assertEqual(rows[0]["classification"], "ALIAS_EXACT_TO_CANONICAL")
        self.assertEqual(len(promotions), 1)
        self.assertEqual(promoted["ITEM-A"]["canonical_item_id"], "7")

    def test_suffix_is_not_stripped_without_registry_evidence(self) -> None:
        edges = [{"component_sku": "ITEM-1", "parent_woo_id": "10", "combination_parent_woo_id": "1", "parent_sku": "PACK", "edge_status": "BLOCKED"}]
        rows, promotions, blocked, _ = resolution.resolve_aliases(edges, [], [{"item_id": "7", "sku": "ITEM"}])
        self.assertEqual(rows[0]["classification"], "ALIAS_SUFFIX_CANDIDATE_UNPROVEN")
        self.assertEqual(promotions, [])
        self.assertEqual(len(blocked), 1)

    def test_placeholder_without_target_is_not_promoted(self) -> None:
        exclusions = [{"heca_reference": "0606011", "hub_item_code": "0606011", "item_record_type": "component_placeholder", "related_canonical_item_id": ""}]
        edges = [{"component_sku": "0606011", "parent_woo_id": "10"}]
        row = next(item for item in resolution.placeholder_review(exclusions, edges) if item["component_code"] == "0606011")
        self.assertEqual(row["classification"], "COMMERCIAL_COMPONENT_WITHOUT_PHYSICAL_NODE")
        self.assertEqual(row["human_decision_required"], "YES")

    def test_malformed_code_is_never_corrected_by_inference(self) -> None:
        edges = [{"component_sku": "01619002", "parent_woo_id": "10"}]
        row = next(item for item in resolution.placeholder_review([], edges) if item["component_code"] == "01619002")
        self.assertEqual(row["classification"], "MALFORMED_SKU_UNPROVEN")
        self.assertIn("NO_SUFFIX_STRIP", row["prohibited_inference"])

    def test_physical_without_woo_and_without_usage_is_not_listed(self) -> None:
        physical = [{"item_id": "1", "sku": "001", "map_status": "BLOCKED", "woo_combination_usage_count": "0"}]
        eligible = [{"item_id": "1", "dat_status": "ACTIVO_DAT"}]
        row = resolution.segment_missing_woo(physical, eligible)[0]
        self.assertEqual(row["missing_woo_segment"], "NOT_LISTED_STANDALONE_AND_UNUSED")

    def test_valid_component_does_not_need_standalone_woo(self) -> None:
        physical = [{"item_id": "1", "sku": "001", "map_status": "BLOCKED", "woo_combination_usage_count": "3"}]
        row = resolution.segment_missing_woo(physical, [{"item_id": "1"}])[0]
        self.assertEqual(row["missing_woo_segment"], "COMPONENT_REFERENCED_WITHOUT_STANDALONE_WOO")
        self.assertEqual(row["can_participate_in_combination_delta"], "YES")

    def test_historical_maestro_source_is_nonblocking(self) -> None:
        edges = [{"parent_sku": "PACK", "source": "MAESTRO", "component_sku": "A", "quantity_status": "EXACT", "parent_match_method": "MISSING_WOO_SKU"}]
        maestro = [{"combination_sku_exact": "PACK", "status": "DESCATALOGADO"}]
        row = resolution.segment_external_sources(edges, maestro)[0]
        self.assertEqual(row["classification"], "HISTORICAL_COMPOSITION_EVIDENCE")
        self.assertEqual(row["active_graph_blocker"], "NO")

    def test_active_maestro_source_without_woo_stays_blocked(self) -> None:
        edges = [{"parent_sku": "PACK", "source": "MAESTRO", "component_sku": "A", "quantity_status": "EXACT", "parent_match_method": "MISSING_WOO_SKU"}]
        maestro = [{"combination_sku_exact": "PACK", "status": "ACTIVO"}]
        row = resolution.segment_external_sources(edges, maestro)[0]
        self.assertEqual(row["classification"], "ACTIVE_SOURCE_COMPOSITION_WITHOUT_WOO_PARENT")
        self.assertEqual(row["human_decision_required"], "YES")

    def test_combination_rebuild_promotes_only_fully_resolved_alias(self) -> None:
        edges = [
            {"parent_woo_id": "10", "parent_sku": "PACK", "component_sku": "A", "edge_status": "EXACT"},
            {"parent_woo_id": "10", "parent_sku": "PACK", "component_sku": "B-A", "edge_status": "BLOCKED"},
        ]
        types = [{"woo_id": "10", "parent_woo_id": "1", "sku": "PACK", "name": "Pack", "composition_status": "BLOCKED_INCOMPLETE_COMPOSITION"}]
        promoted = {"B-A": {"canonical_item_id": "2", "canonical_sku": "B"}}
        aliases = [{"component_sku": "B-A", "classification": "ALIAS_EXACT_TO_CANONICAL"}]
        rows, promotions, blocked = resolution.rebuild_combinations(edges, types, promoted, aliases)
        self.assertEqual(rows[0]["new_status"], "COMPOSITION_EXACT_WOO_WITH_ALIAS")
        self.assertEqual(len(promotions), 1)
        self.assertEqual(blocked, [])

    def test_source_contains_no_woo_write_client(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for token in ("WooCommerceClient", "client.post(", "client.put(", "client.delete(", "requests.post("):
            self.assertNotIn(token, source)

    def test_source_contains_no_supabase_access_or_write(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for token in ("create_supabase_client", ".table(", ".upsert(", "supabase_url"):
            self.assertNotIn(token, source)

    def test_source_contains_no_git_execution(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("subprocess", source)
        self.assertNotIn("git commit", source)
        self.assertNotIn("git push", source)


if __name__ == "__main__":
    unittest.main()

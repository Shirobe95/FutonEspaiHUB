from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_woo_catalog_index import build_woo_read_only_index  # noqa: E402
from futonhub.services.woo_map_001a_5_reconciliation import approved_historical_links, reconcile_master  # noqa: E402


def physical(item_id: str, code: str, **overrides: str) -> dict[str, str]:
    row = {
        "item_id": item_id,
        "hub_item_code": code,
        "heca_reference": code,
        "name": "Futón Basic 90x200 Natural",
        "family": "Futones",
        "filter_family": "Futones",
        "filter_group": "Basic",
        "filter_size": "90x200",
        "filter_gama": "Natural",
        "item_record_type": "simple",
        "is_pack": "false",
    }
    row.update(overrides)
    return row


def product(woo_id: int, sku: str, *, kind: str = "simple", name: str = "Futón Basic 90x200 Natural", attributes: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "id": woo_id,
        "sku": sku,
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "type": kind,
        "status": "publish",
        "regular_price": "99.00",
        "sale_price": "",
        "price": "99.00",
        "attributes": attributes or [],
        "categories": [{"name": "Futones"}],
    }


def variation(woo_id: int, parent_id: int, *, sku: str = "", attributes: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "id": woo_id,
        "parent_id": parent_id,
        "sku": sku,
        "name": "",
        "status": "publish",
        "regular_price": "99.00",
        "sale_price": "",
        "price": "99.00",
        "attributes": attributes or [],
    }


class ReadOnlyWoo:
    def __init__(self, products: list[dict[str, object]], variations: dict[int, list[dict[str, object]]] | None = None) -> None:
        self.products = products
        self.variations = variations or {}

    def iter_products(self):
        yield from self.products

    def iter_product_variations(self, parent_id: int):
        yield from self.variations.get(parent_id, [])


def empty_graph() -> dict[str, object]:
    return {"physical_nodes": [], "woo_nodes": [], "composition_edges": []}


class WooMap001A5ReconciliationTests(unittest.TestCase):
    def test_exact_simple_and_literal_zero_suffix_are_safe(self) -> None:
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001"), product(11, "0201001-A")]))
        result = reconcile_master([physical("1", "0201001"), physical("2", "0201001-A")], woo_index=index, graph=empty_graph())
        self.assertEqual([row["final_result"] for row in result["master"]], ["SAFE_DIRECT_PRODUCT", "SAFE_DIRECT_PRODUCT"])

    def test_exact_variation_and_correct_parent_are_safe(self) -> None:
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "", kind="variable")], {20: [variation(21, 20, sku="0402014")]}))
        result = reconcile_master([physical("1", "0402014", family="Camas", filter_family="Camas", filter_group="Macao", filter_size="180x200")], woo_index=index, graph=empty_graph())
        self.assertEqual(result["master"][0]["final_result"], "SAFE_DIRECT_VARIATION")
        self.assertEqual(result["master"][0]["woo_parent_id"], "20")

    def test_unique_skuless_variation_with_full_attributes_is_safe(self) -> None:
        attrs = [{"name": "Modelo", "option": "Basic"}, {"name": "Tamaño", "option": "90x200"}, {"name": "Color", "option": "Natural"}]
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "", kind="variable")], {20: [variation(21, 20, attributes=attrs)]}))
        result = reconcile_master([physical("1", "NO-SKU")], woo_index=index, graph=empty_graph())
        self.assertEqual(result["master"][0]["final_result"], "SAFE_DIRECT_VARIATION")

    def test_ambiguous_skuless_attributes_require_user_review(self) -> None:
        attrs = [{"name": "Modelo", "option": "Basic"}, {"name": "Tamaño", "option": "90x200"}, {"name": "Color", "option": "Natural"}]
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "", kind="variable")], {20: [variation(21, 20, attributes=attrs), variation(22, 20, attributes=attrs)]}))
        result = reconcile_master([physical("1", "NO-SKU")], woo_index=index, graph=empty_graph())
        self.assertEqual(result["master"][0]["final_result"], "REVIEW_USER_MULTIPLE_CANDIDATES")

    def test_skuless_dimension_must_not_promote_14_to_14_5(self) -> None:
        attrs = [{"name": "Modelo", "option": "Basic"}, {"name": "Tamaño", "option": "150x200x14,5"}, {"name": "Color", "option": "Natural"}]
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "", kind="variable")], {20: [variation(21, 20, attributes=attrs)]}))
        row = physical("1", "NO-SKU", filter_size="150x200x14")
        result = reconcile_master([row], woo_index=index, graph=empty_graph())
        self.assertNotIn(result["master"][0]["final_result"], {"SAFE_DIRECT_PRODUCT", "SAFE_DIRECT_VARIATION"})

    def test_historical_uses_effective_superseding_status_and_live_identity(self) -> None:
        graph = {
            "physical_nodes": [{"item_id": "1", "map_status": "MAPPED_EXACT", "woo_node_id": "woo:77"}],
            "woo_nodes": [{"node_id": "woo:77", "woo_id": "77", "parent_woo_id": "", "item_kind": "product", "sku": "HIST"}],
            "composition_edges": [{"physical_item_id": "1", "edge_status": "BLOCKED", "new_edge_status": "EXACT", "resolution_status": "OLD", "new_resolution_status": "APPROVED"}],
        }
        links = approved_historical_links(graph)
        self.assertEqual(links["1"]["effective_edge_status"], "EXACT")
        self.assertEqual(links["1"]["effective_resolution_status"], "APPROVED")
        index = build_woo_read_only_index(ReadOnlyWoo([product(77, "HIST")]))
        result = reconcile_master([physical("1", "NO-DIRECT")], woo_index=index, graph=graph)
        self.assertEqual(result["master"][0]["final_result"], "SAFE_HISTORICAL_LINK_RECOVERED")

    def test_historical_variation_with_wrong_parent_is_conflict(self) -> None:
        graph = {
            "physical_nodes": [{"item_id": "1", "map_status": "MAPPED_EXACT", "woo_node_id": "woo:77"}],
            "woo_nodes": [{"node_id": "woo:77", "woo_id": "77", "parent_woo_id": "99", "item_kind": "variation", "sku": "HIST"}],
            "composition_edges": [],
        }
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "", kind="variable")], {20: [variation(77, 20, sku="HIST")]}))
        result = reconcile_master([physical("1", "NO-DIRECT")], woo_index=index, graph=graph)
        self.assertEqual(result["master"][0]["final_result"], "CONFLICT")

    def test_same_woo_entity_claimed_by_two_physicals_is_conflict(self) -> None:
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "SAME")]))
        result = reconcile_master([physical("1", "SAME"), physical("2", "SAME")], woo_index=index, graph=empty_graph())
        self.assertEqual({row["final_result"] for row in result["master"]}, {"CONFLICT"})

    def test_pack_and_fuzzy_name_do_not_auto_link(self) -> None:
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001-A")]))
        result = reconcile_master([
            physical("1", "0201001"),
            physical("2", "0201001-A", is_pack="true"),
        ], woo_index=index, graph=empty_graph())
        self.assertNotIn(result["master"][0]["final_result"], {"SAFE_DIRECT_PRODUCT", "SAFE_DIRECT_VARIATION", "SAFE_HISTORICAL_LINK_RECOVERED"})
        self.assertEqual(result["master"][1]["final_result"], "NO_DIRECT_WOO_ENTITY_CANDIDATE")

    def test_cama_macao_funda_and_futon_special_checks_are_explicit(self) -> None:
        index = build_woo_read_only_index(ReadOnlyWoo([]))
        result = reconcile_master([
            physical("1", "0402014", family="Camas", filter_family="Camas", filter_group="Macao", filter_size="180x200"),
            physical("2", "0608010", family="Fundas", filter_family="Fundas"),
            physical("3", "0724001", family="Futones", filter_family="Futones", filter_group="Algodón 1 Látex", filter_size="140x200"),
        ], woo_index=index, graph=empty_graph())
        checks = [row["special_check"] for row in result["master"]]
        self.assertIn("CAMA_MACAO_180X200_NATURAL_MANDATORY", checks)
        self.assertIn("FUNDA_PARENT_SIZE_COLOR_REQUIRED", checks)
        self.assertIn("FUTON_CONSTRUCTION_SIZE_GAMA_REQUIRED", checks)

    def test_no_write_path_is_present(self) -> None:
        source = inspect.getsource(reconcile_master)
        for forbidden in (".put(", ".post(", ".update(", ".insert(", ".delete("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

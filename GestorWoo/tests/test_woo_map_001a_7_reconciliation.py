from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_woo_catalog_index import build_woo_read_only_index  # noqa: E402
from futonhub.services.woo_map_001a_7_reconciliation import reconcile_exhaustive  # noqa: E402


class ReadOnlyWoo:
    def __init__(self, products: list[dict[str, object]], variations: dict[int, list[dict[str, object]]] | None = None) -> None:
        self.products = products
        self.variations = variations or {}

    def iter_products(self):
        yield from self.products

    def iter_product_variations(self, product_id: int):
        yield from self.variations.get(product_id, [])


def product(woo_id: int, name: str, *, sku: str = "", kind: str = "simple", status: str = "publish", visibility: str = "visible") -> dict[str, object]:
    return {
        "id": woo_id, "name": name, "sku": sku, "type": kind, "status": status,
        "catalog_visibility": visibility, "date_modified": "2026-08-08T00:00:00",
        "attributes": [], "categories": [], "images": [], "description": "",
    }


def variation(woo_id: int, parent_id: int, *, size: str, color: str, status: str = "publish", sku: str = "") -> dict[str, object]:
    return {
        "id": woo_id, "parent_id": parent_id, "name": "", "sku": sku, "type": "variation",
        "status": status, "catalog_visibility": "visible", "date_modified": "2026-08-08T00:00:00",
        "attributes": [{"name": "Tamano", "option": size}, {"name": "Color", "option": color}], "images": [],
    }


def physical(item_id: str, sku: str, **overrides: str) -> dict[str, str]:
    row = {
        "item_id": item_id, "hub_item_code": sku, "heca_reference": sku,
        "name": "Futon Basic 90x200 Natural", "family": "Futones", "filter_family": "Futones",
        "filter_group": "Basic", "filter_size": "90x200", "filter_gama": "Natural",
        "item_record_type": "simple", "is_pack": "false",
    }
    row.update(overrides)
    return row


def fixture() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, object]], dict[int, list[dict[str, object]]]]:
    rows: list[dict[str, str]] = []
    safe_rows: list[dict[str, str]] = []
    products: list[dict[str, object]] = []
    for position in range(1, 175):
        item_id = f"S{position:03d}"
        sku = f"S{position:04d}"
        rows.append(physical(item_id, sku))
        safe_rows.append({"item_id": item_id, "codigo": sku, "woo_id": str(1000 + position), "woo_parent_id": "", "woo_item_kind": "product", "woo_sku": sku})
        products.append(product(1000 + position, "Futon Basic 90x200 Natural", sku=sku))

    parent = product(3657, "Tatami plegable y futon portatil", kind="variable")
    parent["description"] = "Tatami plegable fijo de 90x200x1,2 cm."
    products.append(parent)
    rows.extend([
        physical("T001", "0201013", name="Tatami Plegable Azul", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Azul"),
        physical("T002", "0208001", name="Tatami Plegable Crudo", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Crudo"),
        physical("T003", "0216001", name="Tatami Plegable Negro", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Negro"),
        physical("406006", "406006", name="Cama Sumatra 160x200 Natural", family="Camas", filter_family="Camas", filter_group="Cama Sumatra", filter_size="160x200"),
        physical("402014", "0402014", name="Cama Macao 180x200 Natural", family="Camas", filter_family="Camas", filter_group="Macao", filter_size="180x200"),
        physical("206001", "0206001", name="Tatami Plegable Granate", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Granate"),
        physical("78009", "0078009", name="Duo Latex", filter_group="Duo Latex", filter_size="140x200x16", filter_gama="NO_GAMA"),
        physical("780002", "0780002", name="Futon Lana", filter_group="Lana", filter_size="120x200x14", filter_gama="NO_GAMA"),
        physical("214001", "0214001", name="Tatami Plegable Verde", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Verde"),
        physical("814003", "0814003", name="Futon Portatil Verde", filter_group="Portatil", filter_size="140x200x4", filter_gama="Verde"),
        physical("NEW001", "NEW001", name="Futon Basic 90x200 Natural", filter_group="Basic", filter_size="90x200", filter_gama="Natural"),
        physical("COMP001", "COMP001", name="Component Evidence", filter_group="Absent", filter_size="88x188", filter_gama="NO_GAMA"),
    ])
    variations = {3657: [
        variation(4556, 3657, size="90x200x1,2", color="Azul"),
        variation(4558, 3657, size="90x200x1,2", color="Crudo"),
        variation(4561, 3657, size="90x200x1,2", color="Negro"),
        variation(4557, 3657, size="90x200x1,2", color="Granate", status="private"),
        variation(4559, 3657, size="90x200x1,2", color="Verde oscuro"),
    ]}
    products.extend([
        product(9001, "Futon Basic 90x200 Natural"),
        product(9002, "Futon Lana 120x200x14,5", kind="simple"),
        product(9003, "Futon Portatil 140x200x4 Verde OUTLET", kind="simple"),
        product(9004, "Base para tatami Macao 180x200", kind="simple"),
    ])
    while len(rows) < 254:
        position = len(rows)
        rows.append(physical(f"R{position:03d}", f"R{position:04d}", name="Absent physical", filter_group="Absent", filter_size="77x177", filter_gama="NO_GAMA"))
    return rows, safe_rows, products, variations


def run() -> dict[str, object]:
    rows, safe_rows, products, variations = fixture()
    graph = {"composition_edges": [{
        "component_item_id": "COMP001", "operational_status_001a3": "INCLUDED_EXACT",
        "combination_woo_id": "7777", "combination_parent_woo_id": "", "combination_sku": "COMBO", "combination_name": "Combination", "quantity": "2",
    }]}
    index = build_woo_read_only_index(ReadOnlyWoo(products, variations))
    return reconcile_exhaustive(rows, safe_rows=safe_rows, graph=graph, woo_index=index)


class WooMap001A7ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = run()
        self.master = {row["physical_item_id"]: row for row in self.result["master"]}

    def test_item_id_never_replaces_leading_zero_physical_sku(self) -> None:
        row = self.master["406006"]
        self.assertEqual(row["physical_sku"], "0406006")
        self.assertEqual(row["woo_resolution_status"], "RETIRED_CONFIRMED_BY_USER")

    def test_complete_global_search_discovers_candidate_without_old_research_input(self) -> None:
        self.assertEqual(self.master["NEW001"]["woo_resolution_status"], "REVIEW_USER_LINK")
        candidates = [row for row in self.result["residual_review"] if row["physical_item_id"] == "NEW001"]
        self.assertTrue(any(row["woo_id"] == "9001" for row in candidates))

    def test_component_only_is_demonstrated_by_approved_graph(self) -> None:
        row = self.master["COMP001"]
        self.assertEqual(row["woo_resolution_status"], "NO_DIRECT_WOO_ENTITY_SUPPORTED")
        self.assertEqual(row["affected_combination_count"], "1")
        self.assertEqual(self.result["component_only"][0]["physical_sku"], "COMP001")

    def test_macao_is_never_confused_with_base_tatami(self) -> None:
        self.assertEqual(self.master["402014"]["woo_resolution_status"], "WOO_CATALOG_INCONSISTENCY")
        self.assertEqual(self.master["402014"]["woo_id"], "")

    def test_private_granate_is_not_automatically_retired(self) -> None:
        self.assertEqual(self.master["206001"]["woo_resolution_status"], "ACTIVE_HIDDEN_WOO_ENTITY")
        self.assertNotEqual(self.master["206001"]["woo_resolution_status"], "RETIRED_CONFIRMED_BY_USER")

    def test_outlet_does_not_win_as_active_direct_entity(self) -> None:
        self.assertNotIn(self.master["814003"]["woo_resolution_status"], {"ACTIVE_DIRECT_WOO_VERIFIED", "ACTIVE_DIRECT_WOO_SAFE_PLAN"})

    def test_leading_zero_duo_is_not_merged_with_078_identity(self) -> None:
        self.assertEqual(self.master["78009"]["woo_resolution_status"], "PHYSICAL_IDENTITY_REVIEW")
        self.assertEqual(self.master["78009"]["physical_sku"], "0078009")

    def test_fourteen_does_not_equal_fourteen_point_five(self) -> None:
        self.assertNotIn(self.master["780002"]["woo_resolution_status"], {"ACTIVE_DIRECT_WOO_VERIFIED", "ACTIVE_DIRECT_WOO_SAFE_PLAN"})

    def test_verde_does_not_equal_verde_oscuro(self) -> None:
        self.assertNotIn(self.master["214001"]["woo_resolution_status"], {"ACTIVE_DIRECT_WOO_VERIFIED", "ACTIVE_DIRECT_WOO_SAFE_PLAN"})

    def test_final_master_is_complete_and_safe_baseline_is_frozen(self) -> None:
        self.assertEqual(len(self.result["master"]), 254)
        self.assertEqual(len({row["physical_item_id"] for row in self.result["master"]}), 254)
        self.assertEqual(self.result["summary"]["unclassified"], 0)
        self.assertEqual(len(self.result["safe_baseline"]), 177)
        self.assertEqual(self.result["summary"]["safe_destination_conflicts"], 0)

    def test_service_has_no_write_path(self) -> None:
        source = inspect.getsource(reconcile_exhaustive)
        for forbidden in (".put(", ".post(", ".update(", ".insert(", ".delete("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

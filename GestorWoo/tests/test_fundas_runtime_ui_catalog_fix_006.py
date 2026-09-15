from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_catalog_reconciliation import (  # noqa: E402
    price_proposal_selectable_catalogue_rows,
)
from futonhub.services.price_woo_only_sources import (  # noqa: E402
    approved_woo_only_price_source_woo_ids,
    build_approved_woo_only_price_source_rows,
)
from futonhub.ui.erp.catalog_filters import CatalogFilterSelection, PhysicalCatalogSnapshot  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


class Response:
    def __init__(self, rows: list[dict[str, object]]):
        self.data = rows


class ReadOnlyTable:
    def __init__(self, rows: list[dict[str, object]], calls: list[tuple[str, object]]):
        self._rows = rows
        self._calls = calls
        self._in_column = ""
        self._in_values: set[object] = set()
        self._limit = len(rows)

    def select(self, columns: str) -> "ReadOnlyTable":
        self._calls.append(("select", columns))
        return self

    def in_(self, column: str, values: list[object]) -> "ReadOnlyTable":
        self._calls.append(("in", (column, tuple(values))))
        self._in_column = column
        self._in_values = set(values)
        return self

    def order(self, column: str) -> "ReadOnlyTable":
        self._calls.append(("order", column))
        return self

    def limit(self, count: int) -> "ReadOnlyTable":
        self._calls.append(("limit", count))
        self._limit = count
        return self

    def execute(self) -> Response:
        self._calls.append(("execute", "read_only"))
        rows = [
            dict(row)
            for row in self._rows
            if not self._in_column or row.get(self._in_column) in self._in_values
        ]
        return Response(rows[: self._limit])


class ReadOnlyClient:
    def __init__(self, tables: dict[str, list[dict[str, object]]]):
        self.tables = tables
        self.calls: list[tuple[str, object]] = []

    def table(self, name: str) -> ReadOnlyTable:
        self.calls.append(("table", name))
        return ReadOnlyTable(self.tables.get(name, []), self.calls)


class Session:
    def __init__(self, client: ReadOnlyClient):
        self.client = client


def live_variation(woo_id: int, parent_id: int, sku: str, *, price: str = "71.00") -> dict[str, object]:
    return {
        "woo_id": woo_id,
        "parent_woo_id": parent_id,
        "parent_name": "Funda Futon",
        "sku": sku,
        "status": "publish",
        "regular_price": price,
        "sale_price": "",
        "price": price,
        "stock_status": "instock",
        "stock_quantity": None,
        "attributes_label": sku,
    }


def make_app() -> FutonHubErpPrototype:
    app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
    app._inventory_catalog_snapshot_cache = PhysicalCatalogSnapshot.load()
    app._price_catalog_filter_selection_state = CatalogFilterSelection()
    app._price_catalog_applied_filter_state = CatalogFilterSelection()
    app._price_search_query = ""
    app._price_filter_metadata_generation = 0
    app._price_filter_options_cache = {}
    app._price_live_price_context_by_physical_item = {}
    app._price_live_sync_required = False
    app._price_candidate_page = 0
    app._price_edit_selected_code = ""
    app._price_proposal_model = {}
    app._current_key = "precios"
    return app


def physical_row(snapshot: PhysicalCatalogSnapshot, item_id: str, *, price: str = "71.00") -> dict[str, object]:
    row = dict(snapshot.rows_by_item_id[item_id])
    row.update({
        "item_id": item_id,
        "physical_item_id": item_id,
        "physical_sku": row.get("hub_item_code"),
        "commercial_status": "Normal",
        "catalog_live_status": "LIVE",
        "price_operable": True,
        "sale_item": "YES",
        "woo_id": 3804 if item_id == "616007" else 0,
        "woo_parent_id": 3631 if item_id == "616007" else "",
        "woo_item_kind": "variation" if item_id == "616007" else "",
        "woo_sku": row.get("hub_item_code"),
        "woo_price": price,
        "woo_link_status": "Enlazado" if item_id == "616007" else "Sin enlazar",
    })
    return row


class FundasRuntimeUiCatalogFix006Tests(unittest.TestCase):
    def test_approved_woo_only_sources_are_read_from_variation_mirror(self) -> None:
        client = ReadOnlyClient({
            "product_variations": [
                live_variation(9907, 3631, "0619005"),
                live_variation(9908, 3631, "0619006"),
                live_variation(9999, 3631, "0619007"),
            ]
        })
        app = make_app()
        app._cloud_session = Session(client)

        rows = app._price_approved_woo_only_variation_rows()
        woo_only_rows = build_approved_woo_only_price_source_rows([], variation_rows=rows)

        self.assertEqual(set(approved_woo_only_price_source_woo_ids()), {9907, 9908})
        self.assertEqual([row["hub_item_code"] for row in woo_only_rows], ["0619005", "0619006"])
        self.assertIn(("table", "product_variations"), client.calls)
        self.assertIn(("in", ("woo_id", (9907, 9908))), client.calls)

    def test_woo_only_fundas_reach_filter_search_pagination_and_ui_model(self) -> None:
        app = make_app()
        woo_only_rows = build_approved_woo_only_price_source_rows(
            [],
            variation_rows=[
                live_variation(9907, 3631, "0619005"),
                live_variation(9908, 3631, "0619006"),
                live_variation(9999, 3631, "0619007"),
            ],
        )
        items = [app._inventory_item_from_cloud_row(row) for row in woo_only_rows]
        selectable = app._price_selectable_catalog_items(items)
        app._price_prepare_catalog_filter_cache(selectable, 1)
        results = app._price_results_from_items(selectable)

        root_options = app._price_catalog_filter_options_for_selection(CatalogFilterSelection())
        self.assertIn("Fundas", root_options["filter_family"])
        self.assertIn("140x200x8", root_options["filter_size"])
        self.assertIn("Crudo", root_options["filter_gama"])
        self.assertIn("Negro", root_options["filter_gama"])

        app._price_catalog_applied_filter_state = CatalogFilterSelection(
            filter_family="Fundas",
            filter_group="Funda Futón",
            filter_size="140x200x8",
        )
        filtered = app._price_filtered_catalog_results(results)
        visible, page, pages = app._price_candidate_page_results(filtered)
        self.assertEqual(page, 0)
        self.assertEqual(pages, 1)
        self.assertEqual([row["code"] for row in visible], ["0619005", "0619006"])
        self.assertEqual([row["type"] for row in visible], ["Variacion", "Variacion"])

        app._price_catalog_applied_filter_state = CatalogFilterSelection(query="0619005")
        by_code = app._price_filtered_catalog_results(results)
        self.assertEqual([row["code"] for row in by_code], ["0619005"])
        self.assertEqual(by_code[0]["source"]["price_source_woo_only"], "YES")

    def test_0616007_black_funda_is_not_hidden_by_616008_exclusion(self) -> None:
        app = make_app()
        snapshot = app._price_catalog_snapshot()
        row_616007 = physical_row(snapshot, "616007")
        row_616008 = physical_row(snapshot, "616008")

        self.assertEqual(price_proposal_selectable_catalogue_rows([row_616007]), [row_616007])
        self.assertEqual(price_proposal_selectable_catalogue_rows([row_616008]), [])

        items = [
            app._inventory_item_from_cloud_row(row_616007),
            app._inventory_item_from_cloud_row(row_616008),
        ]
        selectable = app._price_selectable_catalog_items(items)
        app._price_prepare_catalog_filter_cache(selectable, 1)
        results = app._price_results_from_items(selectable)

        app._price_catalog_applied_filter_state = CatalogFilterSelection(query="0616007")
        by_code = app._price_filtered_catalog_results(results)
        self.assertEqual(len(by_code), 1)
        self.assertEqual(by_code[0]["source"]["physical_sku"], "0616007")

        app._price_catalog_applied_filter_state = CatalogFilterSelection(
            filter_family="Fundas",
            filter_group="Funda Futón",
            filter_size="80x200x13",
            filter_gama="Negro",
        )
        filtered = app._price_filtered_catalog_results(results)
        visible, _page, _pages = app._price_candidate_page_results(filtered)
        self.assertEqual([row["source"]["physical_sku"] for row in visible], ["0616007"])

    def test_woo_only_sources_do_not_contaminate_physical_snapshot(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()

        self.assertNotIn("930000009907", snapshot.rows_by_item_id)
        self.assertNotIn("930000009908", snapshot.rows_by_item_id)
        self.assertIn("616007", snapshot.rows_by_item_id)


if __name__ == "__main__":
    unittest.main()

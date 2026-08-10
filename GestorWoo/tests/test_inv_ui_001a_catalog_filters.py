from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterConfigurationError,
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    catalog_filter_options,
    filter_catalog_rows,
    natural_catalog_sort_key,
)
from futonhub.cloud.services.inventory import INVENTORY_SELECT_COLUMNS, list_cloud_inventory_items_by_ids  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


def inventory_item(raw: dict[str, object]) -> InventoryItem:
    return InventoryItem(
        code=str(raw.get("item_id") or "-"),
        name=str(raw.get("name") or "-"),
        price="100.00 EUR",
        stock="0",
        status="OK",
        family=str(raw.get("family") or "-"),
        provider="-",
        m3="-",
        sku_woo="-",
        measures=str(raw.get("size") or "-"),
        material="-",
        sync_woo="-",
        notes="-",
        woo_id=str(raw.get("woo_id") or "-"),
        woo_item_kind=str(raw.get("woo_item_kind") or "product"),
        raw=raw,
    )


class CatalogFilterEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"item_id": "1", "name": "Futón Ágata", "filter_family": "Futones", "filter_group": "Algodón", "filter_size": "80x200", "filter_gama": "Natural"},
            {"item_id": "2", "name": "Funda 10", "filter_family": "Fundas", "filter_group": "Funda Sofá", "filter_size": "140x200", "filter_gama": "Crudo"},
            {"item_id": "3", "name": "Funda 2", "filter_family": "Fundas", "filter_group": "Funda Sofá", "filter_size": "90x200", "filter_gama": "Natural"},
        ]

    def test_hierarchy_applies_all_selected_levels(self) -> None:
        selection = CatalogFilterSelection(filter_family="Fundas", filter_group="Funda Sofá", filter_size="90x200", filter_gama="Natural")
        self.assertEqual([row["item_id"] for row in filter_catalog_rows(self.rows, selection)], ["3"])

    def test_selector_resets_descendants(self) -> None:
        selection = CatalogFilterSelection("Futones", "Algodón", "80x200", "Natural")
        self.assertEqual(selection.with_filter("filter_group", "Portátil"), CatalogFilterSelection("Futones", "Portátil", "", "", ""))

    def test_search_is_case_and_accent_insensitive_for_code_and_name(self) -> None:
        self.assertEqual([row["item_id"] for row in filter_catalog_rows(self.rows, CatalogFilterSelection(query="futon agata"))], ["1"])
        self.assertEqual([row["item_id"] for row in filter_catalog_rows(self.rows, CatalogFilterSelection(query="2"))], ["2", "3"])

    def test_options_follow_parent_selection_and_are_naturally_sorted(self) -> None:
        options = catalog_filter_options(self.rows, CatalogFilterSelection(filter_family="Fundas"))
        self.assertEqual(options["filter_group"], ["Funda Sofá"])
        self.assertEqual(sorted(["10x200", "2x200"], key=natural_catalog_sort_key), ["2x200", "10x200"])

    def test_snapshot_matches_its_versioned_expected_count(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()
        self.assertEqual(len(snapshot.item_ids), snapshot.expected_count)
        self.assertEqual(len(set(snapshot.item_ids)), snapshot.expected_count)

    def test_invalid_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            path.write_text("item_id\n1\n", encoding="utf-8")
            with self.assertRaises(CatalogFilterConfigurationError):
                PhysicalCatalogSnapshot.load(path)

    def test_live_eligibility_excludes_pack_incomplete_and_unlisted_rows(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()
        row = dict(next(iter(snapshot.rows_by_item_id.values())))
        pack = {**row, "is_pack": "true"}
        incomplete = {**row, "filter_size": ""}
        unlisted = {**row, "item_id": "999999"}
        self.assertEqual(snapshot.eligible_live_rows([pack, incomplete, unlisted, row]), [row])

    def test_inventory_read_columns_include_all_four_filter_dimensions(self) -> None:
        for field in ("filter_family", "filter_group", "filter_size", "filter_gama", "catalog_review_status"):
            self.assertIn(field, INVENTORY_SELECT_COLUMNS)

    def test_inventory_read_columns_exclude_snapshot_only_metadata(self) -> None:
        for field in ("physical_validation_source", "canonical_resolution_status", "ui_eligibility_status"):
            self.assertNotIn(field, INVENTORY_SELECT_COLUMNS)

    def test_snapshot_source_is_not_required_on_live_row(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()
        snapshot_row = dict(next(iter(snapshot.rows_by_item_id.values())))
        live_row = {
            key: value
            for key, value in snapshot_row.items()
            if key not in {"physical_validation_source", "canonical_resolution_status", "ui_eligibility_status"}
        }
        self.assertEqual(snapshot.eligible_live_rows([live_row]), [live_row])
        self.assertIn(snapshot.rows_by_item_id[live_row["item_id"]]["physical_validation_source"], {"DAT", "MAESTRO"})

    def test_snapshot_rows_produce_real_cascade_options(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()
        rows = list(snapshot.rows_by_item_id.values())
        options = catalog_filter_options(rows, CatalogFilterSelection())
        self.assertTrue(options["filter_family"])
        family = options["filter_family"][0]
        options = catalog_filter_options(rows, CatalogFilterSelection(filter_family=family))
        self.assertTrue(options["filter_group"])
        group = options["filter_group"][0]
        options = catalog_filter_options(rows, CatalogFilterSelection(filter_family=family, filter_group=group))
        self.assertTrue(options["filter_size"])
        size = options["filter_size"][0]
        options = catalog_filter_options(rows, CatalogFilterSelection(filter_family=family, filter_group=group, filter_size=size))
        self.assertTrue(options["filter_gama"])


class InventoryReadByIdTests(unittest.TestCase):
    class Response:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.data = rows

    class Query:
        def __init__(self, rows: list[dict[str, object]], calls: list[tuple[str, object]]) -> None:
            self.rows = rows
            self.calls = calls
            self.ids: list[int] = []

        def select(self, columns: str):
            self.calls.append(("select", columns))
            forbidden = {"physical_validation_source", "canonical_resolution_status", "ui_eligibility_status"}
            selected = {column.strip() for column in columns.split(",")}
            unknown = forbidden & selected
            if unknown:
                raise RuntimeError(f"column inventory_items.{sorted(unknown)[0]} does not exist")
            return self

        def in_(self, column: str, values):
            self.calls.append(("in", (column, tuple(values))))
            self.ids = [int(value) for value in values]
            return self

        def limit(self, value: int):
            self.calls.append(("limit", value))
            return self

        def execute(self):
            return InventoryReadByIdTests.Response([row for row in self.rows if int(row["item_id"]) in self.ids])

    class Session:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows
            self.calls: list[tuple[str, object]] = []
            self.client = self

        def table(self, name: str):
            self.calls.append(("table", name))
            return InventoryReadByIdTests.Query(self.rows, self.calls)

    def test_read_by_ids_is_bounded_ordered_and_has_no_write_method(self) -> None:
        session = self.Session([{"item_id": 1}, {"item_id": 2}, {"item_id": 3}])
        rows = list_cloud_inventory_items_by_ids(session, [2, 1, 2, "invalid"], chunk_size=1)
        self.assertEqual([row["item_id"] for row in rows], [2, 1])
        self.assertEqual([call for call in session.calls if call[0] == "in"], [("in", ("item_id", (2,))), ("in", ("item_id", (1,)))])
        self.assertFalse(any(call[0] in {"update", "insert", "delete", "upsert"} for call in session.calls))

    def test_read_by_ids_survives_postgrest_rejection_of_snapshot_columns(self) -> None:
        session = self.Session([{"item_id": 1}, {"item_id": 2}])
        rows = list_cloud_inventory_items_by_ids(session, [1, 2])
        self.assertEqual([row["item_id"] for row in rows], [1, 2])


class PriceCatalogFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = PhysicalCatalogSnapshot.load()
        self.metadata = dict(next(iter(self.snapshot.rows_by_item_id.values())))
        self.app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        self.app._inventory_catalog_snapshot_cache = self.snapshot
        self.app._price_catalog_filter_selection_state = CatalogFilterSelection()
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection()
        self.app._price_search_query = ""
        self.app._price_edit_selected_code = "selected"
        self.app._price_proposal_model = {"product:1": {"keep": True}}
        self.app._current_key = "other"

    def _result(self, raw: dict[str, object]) -> dict[str, object]:
        item = inventory_item(raw)
        return {"code": item.code, "name": item.name, "type": "Simple", "price": item.price, "item": item, "source": {"item_kind": "product", "woo_id": 1}}

    def test_no_hierarchy_keeps_existing_candidates_even_when_unmapped(self) -> None:
        mapped = self._result(self.metadata)
        unmapped = self._result({"item_id": "not-linked", "name": "Sin metadata"})
        self.assertEqual(self.app._price_filtered_catalog_results([mapped, unmapped]), [mapped, unmapped])

    def test_hierarchy_filters_only_exactly_mapped_candidates(self) -> None:
        live_metadata = {
            key: value
            for key, value in self.metadata.items()
            if key not in {"physical_validation_source", "canonical_resolution_status", "ui_eligibility_status"}
        }
        mapped = self._result(live_metadata)
        unmapped = self._result({"item_id": "not-linked", "name": "Sin metadata"})
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection(filter_family=self.metadata["filter_family"])
        self.assertEqual(self.app._price_filtered_catalog_results([mapped, unmapped]), [mapped])

    def test_exact_heca_and_base_code_are_allowed_but_name_is_not_identity(self) -> None:
        via_heca = self._result({"item_id": "variation-1", "heca_reference": self.metadata["heca_reference"], "name": "Nombre cambiado", "item_record_type": "woo_variation"})
        via_base = self._result({"item_id": "variation-2", "base_item_code": self.metadata["hub_item_code"], "name": "Otro nombre", "item_record_type": "woo_variation"})
        by_name_only = self._result({"item_id": "variation-3", "name": self.metadata["name"], "item_record_type": "woo_variation"})
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection(filter_family=self.metadata["filter_family"])
        self.assertEqual(self.app._price_filtered_catalog_results([via_heca, via_base, by_name_only]), [via_heca, via_base])

    def test_packs_aliases_and_component_placeholders_cannot_match_hierarchy(self) -> None:
        self.app._price_catalog_applied_filter_state = CatalogFilterSelection(filter_family=self.metadata["filter_family"])
        rows = [
            self._result({**self.metadata, "is_pack": True}),
            self._result({**self.metadata, "item_record_type": "alias"}),
            self._result({**self.metadata, "item_record_type": "component_placeholder"}),
        ]
        self.assertEqual(self.app._price_filtered_catalog_results(rows), [])

    def test_clear_does_not_reset_selected_candidate_or_price_model(self) -> None:
        self.app._price_catalog_filter_selection_state = CatalogFilterSelection(filter_family=self.metadata["filter_family"])
        self.app._price_catalog_applied_filter_state = self.app._price_catalog_filter_selection_state
        self.app._clear_price_catalog_filters(object())
        self.assertEqual(self.app._price_edit_selected_code, "selected")
        self.assertEqual(self.app._price_proposal_model, {"product:1": {"keep": True}})
        self.assertEqual(self.app._price_catalog_applied_filter_state, CatalogFilterSelection())

    def test_new_filter_code_does_not_reference_write_operations(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_filtered_catalog_results)
        self.assertNotIn(".update(", source)
        self.assertNotIn(".insert(", source)
        self.assertNotIn(".delete(", source)


if __name__ == "__main__":
    unittest.main()

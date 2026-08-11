from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import CatalogFilterSelection, PhysicalCatalogSnapshot  # noqa: E402
from futonhub.ui.erp.inventory_list import ErpInventoryListMixin  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402
from futonhub.services.catalog_operational_baseline import CatalogOperationalBaselineError  # noqa: E402


class Parent:
    def winfo_exists(self) -> bool:
        return True


class ImmediateThread:
    def __init__(self, target, daemon=False) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


class Session:
    pass


class InventoryListCollector(ErpInventoryListMixin):
    def __init__(self, session: object | None) -> None:
        self._cloud_session = session
        self._inventory_items: list[InventoryItem] = []
        self._inventory_error = ""
        self._inventory_loading = False
        self._inventory_loaded_once = False
        self._inventory_query = ""
        self._inventory_catalog_source_rows: list[dict[str, object]] = []
        self._inventory_catalog_filter_selection_state = CatalogFilterSelection()
        self._inventory_catalog_applied_filter_state = CatalogFilterSelection()
        self._inventory_catalog_snapshot_cache = PhysicalCatalogSnapshot.load()
        self._selected_inventory_item: InventoryItem | None = None
        self._current_key = "inventario"
        self.show_calls: list[str] = []

    def after(self, _delay: int, callback) -> None:
        callback()

    def _show_view(self, key: str) -> None:
        self.show_calls.append(key)

    def _inventory_item_from_cloud_row(self, row: dict[str, object]) -> InventoryItem:
        code = str(row.get("item_id") or "-")
        return InventoryItem(
            code=code,
            name=str(row.get("name") or code),
            price="0.00",
            stock="0",
            status="OK",
            family=str(row.get("family") or "-"),
            provider="-",
            m3="-",
            sku_woo="-",
            measures=str(row.get("size") or "-"),
            material="-",
            sync_woo="-",
            notes="-",
            raw=dict(row),
        )


class InventoryListRefreshTests(unittest.TestCase):
    def _eligible_row(self) -> dict[str, object]:
        snapshot = PhysicalCatalogSnapshot.load()
        return dict(next(iter(snapshot.rows_by_item_id.values())))

    def test_refresh_requires_query_when_empty_search_is_not_allowed(self) -> None:
        app = InventoryListCollector(Session())
        with patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items_by_ids") as list_items:
            app._refresh_inventory(Parent(), "", allow_empty=False)
        self.assertEqual(app._inventory_error, "Introduce un texto o ID para buscar inventario real en Supabase.")
        self.assertFalse(app._inventory_loading)
        self.assertEqual(app.show_calls, ["inventario"])
        list_items.assert_not_called()

    def test_refresh_blocks_without_cloud_session_before_reading_allowlist_ids(self) -> None:
        app = InventoryListCollector(None)
        with patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items_by_ids") as list_items:
            app._refresh_inventory(Parent(), "0201001", allow_empty=True)
        self.assertEqual(app._inventory_error, "No hay sesion Supabase activa.")
        self.assertFalse(app._inventory_loading)
        list_items.assert_not_called()

    def test_refresh_reads_allowlisted_ids_and_excludes_nonphysical_live_rows(self) -> None:
        app = InventoryListCollector(Session())
        snapshot = PhysicalCatalogSnapshot.load()
        eligible_rows = [dict(row) for row in snapshot.rows_by_item_id.values()]
        eligible = eligible_rows[0]
        pack = {**eligible, "is_pack": True}
        incomplete = {**eligible, "filter_group": ""}
        unlisted = {**eligible, "item_id": "999999"}
        with (
            patch("futonhub.ui.erp.inventory_list.threading.Thread", ImmediateThread),
            patch(
                "futonhub.ui.erp.inventory_list.list_cloud_inventory_items_by_ids",
                return_value=[pack, incomplete, unlisted, *eligible_rows],
            ) as list_items,
        ):
            app._refresh_inventory(Parent(), "", allow_empty=True)
        requested_ids = list_items.call_args.args[1]
        self.assertEqual(len(requested_ids), snapshot.expected_count)
        self.assertEqual(len(app._inventory_items), snapshot.expected_count)
        self.assertEqual(len(app._inventory_catalog_source_rows), snapshot.expected_count)
        self.assertEqual(app._inventory_error, "")

    def test_runtime_baseline_failure_is_not_reported_as_supabase_failure(self) -> None:
        app = InventoryListCollector(Session())
        row = self._eligible_row()
        with (
            patch("futonhub.ui.erp.inventory_list.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items_by_ids", return_value=[row]),
            patch.object(
                InventoryListCollector,
                "_inventory_operational_baseline",
                side_effect=CatalogOperationalBaselineError("baseline runtime roto"),
            ),
        ):
            app._refresh_inventory(Parent(), "", allow_empty=True)
        self.assertIn("configuracion runtime de inventario", app._inventory_error)
        self.assertNotIn("Supabase", app._inventory_error)

    def test_apply_catalog_filters_is_local_and_accent_insensitive(self) -> None:
        app = InventoryListCollector(Session())
        row = self._eligible_row()
        row["name"] = "Futón de prueba"
        app._inventory_catalog_source_rows = [row]
        app._inventory_items = [app._inventory_item_from_cloud_row(row)]
        app._apply_inventory_catalog_filters(CatalogFilterSelection(filter_family=row["filter_family"], query="futon"))
        self.assertEqual([item.code for item in app._inventory_filtered_items()], [str(row["item_id"])])
        self.assertEqual(app._inventory_query, "futon")


if __name__ == "__main__":
    unittest.main()

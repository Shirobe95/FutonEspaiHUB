from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.inventory_list import ErpInventoryListMixin  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


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
        self._selected_inventory_item: InventoryItem | None = None
        self._current_key = "inventario"
        self.show_calls: list[str] = []

    def after(self, _delay: int, callback) -> None:
        callback()

    def _show_view(self, key: str) -> None:
        self.show_calls.append(key)

    def _inventory_item_from_cloud_row(self, row: dict[str, object]) -> InventoryItem:
        code = str(row.get("item_id") or row.get("woo_id") or "-")
        return InventoryItem(
            code=code,
            name=str(row.get("name") or code),
            price=str(row.get("woo_price") or "0.00"),
            stock=str(row.get("stock") or "0"),
            status=str(row.get("status") or "OK"),
            family="-",
            provider="-",
            m3="-",
            sku_woo=str(row.get("woo_sku") or "-"),
            measures="-",
            material="-",
            sync_woo="-",
            notes="-",
            raw=row,
        )

    def _inventory_query_is_code_like(self, query: str) -> bool:
        text = (query or "").strip()
        return bool(text and re.fullmatch(r"[A-Za-z0-9_\-|]+", text))

    def _merge_inventory_rows(self, groups: list[list[dict[str, object]]]) -> list[dict[str, object]]:
        merged: list[dict[str, object]] = []
        seen: set[str] = set()
        for group in groups:
            for row in group:
                key = str(row.get("item_id") or row.get("woo_id") or row)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(row)
        return merged

    def _accent_insensitive_inventory_search(self, rows: list[dict[str, object]], query: str) -> list[dict[str, object]]:
        query_text = query.lower()
        return [row for row in rows if query_text in str(row.get("name") or "").lower()]


class InventoryListRefreshTests(unittest.TestCase):
    def test_refresh_requires_query_when_empty_search_is_not_allowed(self) -> None:
        app = InventoryListCollector(Session())

        with (
            patch("futonhub.ui.erp.inventory_list.search_cloud_inventory_items") as search,
            patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items") as list_items,
        ):
            app._refresh_inventory(Parent(), "", allow_empty=False)

        self.assertEqual(app._inventory_error, "Introduce un texto o ID para buscar inventario real en Supabase.")
        self.assertFalse(app._inventory_loading)
        self.assertEqual(app.show_calls, ["inventario"])
        search.assert_not_called()
        list_items.assert_not_called()

    def test_refresh_blocks_without_cloud_session_before_querying_services(self) -> None:
        app = InventoryListCollector(None)

        with (
            patch("futonhub.ui.erp.inventory_list.search_cloud_inventory_items") as search,
            patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items") as list_items,
        ):
            app._refresh_inventory(Parent(), "0201001", allow_empty=True)

        self.assertEqual(app._inventory_error, "No hay sesion Supabase activa.")
        self.assertFalse(app._inventory_loading)
        search.assert_not_called()
        list_items.assert_not_called()

    def test_code_like_search_uses_ranked_server_rows_without_full_inventory_merge(self) -> None:
        app = InventoryListCollector(Session())

        with (
            patch("futonhub.ui.erp.inventory_list.threading.Thread", ImmediateThread),
            patch(
                "futonhub.ui.erp.inventory_list.search_cloud_inventory_items",
                return_value=[{"item_id": "0201001", "name": "Futon"}],
            ) as search,
            patch("futonhub.ui.erp.inventory_list.list_cloud_inventory_items") as list_items,
        ):
            app._refresh_inventory(Parent(), "0201001", allow_empty=True)

        search.assert_called_once_with(app._cloud_session, "0201001", limit=100)
        list_items.assert_not_called()
        self.assertEqual([item.code for item in app._inventory_items], ["0201001"])
        self.assertEqual(app._selected_inventory_item, app._inventory_items[0])
        self.assertTrue(app._inventory_loaded_once)
        self.assertFalse(app._inventory_loading)

    def test_text_search_merges_server_rows_with_accent_insensitive_local_matches(self) -> None:
        app = InventoryListCollector(Session())

        with (
            patch("futonhub.ui.erp.inventory_list.threading.Thread", ImmediateThread),
            patch(
                "futonhub.ui.erp.inventory_list.search_cloud_inventory_items",
                return_value=[{"item_id": "A1", "name": "Tatami"}],
            ) as search,
            patch(
                "futonhub.ui.erp.inventory_list.list_cloud_inventory_items",
                return_value=[{"item_id": "A1", "name": "Tatami"}, {"item_id": "A2", "name": "tatami extra"}],
            ) as list_items,
        ):
            app._refresh_inventory(Parent(), "tatami extra", allow_empty=True)

        search.assert_called_once_with(app._cloud_session, "tatami extra", limit=100)
        list_items.assert_called_once_with(app._cloud_session, limit=500)
        self.assertEqual([item.code for item in app._inventory_items], ["A1", "A2"])
        self.assertEqual(app._inventory_error, "")

    def test_empty_allowed_refresh_loads_default_inventory_window(self) -> None:
        app = InventoryListCollector(Session())

        with (
            patch("futonhub.ui.erp.inventory_list.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_list.search_cloud_inventory_items") as search,
            patch(
                "futonhub.ui.erp.inventory_list.list_cloud_inventory_items",
                return_value=[{"item_id": "A1", "name": "Base"}],
            ) as list_items,
        ):
            app._refresh_inventory(Parent(), "", allow_empty=True)

        search.assert_not_called()
        list_items.assert_called_once_with(app._cloud_session, limit=150)
        self.assertEqual(app._inventory_query, "")
        self.assertEqual([item.name for item in app._inventory_items], ["Base"])


if __name__ == "__main__":
    unittest.main()

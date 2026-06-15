from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.inventory_detail import ErpInventoryDetailMixin  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


class ImmediateThread:
    def __init__(self, target, daemon=False) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


class Session:
    pass


class InventoryDetailCollector(ErpInventoryDetailMixin):
    def __init__(self, session: object | None = None) -> None:
        self._cloud_session = session
        self.cards: list[tuple[str, list[dict[str, object]], str, str]] = []

    def after(self, _delay: int, callback) -> None:
        callback()

    def _clean_inventory_value(self, value: object, fallback: str = "-") -> str:
        text = str(value or "").strip()
        return text if text else fallback

    def _inventory_pack_parent_code(self, item: InventoryItem) -> str:
        return str((item.raw or {}).get("hub_item_code") or "")

    def _inventory_pack_contents_text(self, item: InventoryItem | None, *, multiline: bool = False) -> str:
        if item is None:
            return ""
        return str((item.raw or {}).get("hub_pack_components_text") or "")

    def _render_inventory_history_card(
        self,
        _parent,
        title: str,
        history: list[dict[str, object]],
        empty_text: str,
        current_value: str,
        _color: str,
    ) -> None:
        self.cards.append((title, history, empty_text, current_value))


def inventory_item(**raw_overrides: object) -> InventoryItem:
    raw = {
        "hub_item_code": "PACK-001",
        "item_record_type": "simple",
        "hub_pack_components_text": "",
    }
    raw.update(raw_overrides)
    return InventoryItem(
        code="0201001",
        name="Futon prueba",
        price="249.00",
        stock="3",
        status="OK",
        family="Futones",
        provider="Proveedor",
        m3="0.42",
        sku_woo="SKU-1",
        measures="140 x 200",
        material="Algodon",
        sync_woo="product / 10 / linked",
        notes="Notas",
        subgroup="Subgrupo",
        store_stock="1",
        warehouse_stock="2",
        stock_total="3",
        woo_id="10",
        woo_parent_id="-",
        woo_name="Woo Futon",
        woo_price="249.00",
        woo_categories="Futones",
        woo_item_kind="product",
        woo_link_status="linked",
        order_calculated_price="200.00",
        weighted_average_cost="190.00",
        supplier_order_qty="1",
        supplier_order_provider="Proveedor",
        status_reasons=("Sin incidencias detectadas con las reglas actuales.",),
        raw=raw,
    )


class InventoryDetailRowsTests(unittest.TestCase):
    def test_detail_rows_preserve_selected_item_fields_and_pack_row_position(self) -> None:
        app = InventoryDetailCollector()
        item = inventory_item(hub_pack_components_text="0201001 x1; 0201002 x2")

        rows = app._inventory_detail_rows(item)

        self.assertEqual(rows[0], ("ID", "0201001"))
        self.assertEqual(rows[1], ("CÃ³digo HUB", "PACK-001"))
        self.assertEqual(rows[3], ("Contenido pack", "0201001 x1; 0201002 x2"))
        self.assertIn(("Precio Woo", "249.00"), rows)
        self.assertIn(("Stock total", "3 unidades"), rows)
        self.assertIn(("Estado vinculo Woo", "linked"), rows)


class InventoryHistoryTests(unittest.TestCase):
    def test_history_rows_are_split_between_price_and_stock_cards(self) -> None:
        app = InventoryDetailCollector()
        item = inventory_item()
        history = [
            {"field": "woo_price", "after": "249.00"},
            {"field": "store_stock", "after": "2"},
            {"field": "notes", "after": "sin cambio"},
        ]

        app._render_inventory_history("price", "stock", history, item)

        self.assertEqual(app.cards[0][0], "Historial completo")
        self.assertEqual(app.cards[0][1], [{"field": "woo_price", "after": "249.00"}])
        self.assertEqual(app.cards[1][0], "Historial de stock")
        self.assertEqual(app.cards[1][1], [{"field": "store_stock", "after": "2"}])

    def test_load_history_uses_current_service_and_renders_success(self) -> None:
        app = InventoryDetailCollector(Session())
        item = inventory_item()
        rows = [{"field": "price", "after": "249.00"}]

        with (
            patch("futonhub.ui.erp.inventory_detail.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_detail.fetch_inventory_item_history", return_value=rows) as fetch_history,
        ):
            app._load_inventory_history("price", "stock", item)

        fetch_history.assert_called_once_with(app._cloud_session, 201001, limit=120)
        self.assertEqual(app.cards[0][2], "Cargando historial real...")
        self.assertEqual(app.cards[2][1], rows)

    def test_load_history_without_session_renders_error_cards_without_service_call(self) -> None:
        app = InventoryDetailCollector(None)
        item = inventory_item()

        with (
            patch("futonhub.ui.erp.inventory_detail.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_detail.fetch_inventory_item_history") as fetch_history,
        ):
            app._load_inventory_history("price", "stock", item)

        fetch_history.assert_not_called()
        self.assertIn("No se pudo cargar historial: No hay sesion Supabase activa.", app.cards[2][2])
        self.assertIn("No se pudo cargar historial: No hay sesion Supabase activa.", app.cards[3][2])


if __name__ == "__main__":
    unittest.main()

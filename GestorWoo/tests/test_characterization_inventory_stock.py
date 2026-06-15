from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import inventory as inventory_service  # noqa: E402
from futonhub.ui.erp.inventory_stock import ErpInventoryStockMixin  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


class Session:
    user_id = "USER-1"
    email = "admin@example.com"
    role = "admin"


class InventoryStockCollector(ErpInventoryStockMixin):
    def __init__(self, session: object | None = None) -> None:
        self._cloud_session = session


def inventory_item() -> InventoryItem:
    return InventoryItem(
        code="0201014",
        name="Futon prueba",
        price="128.00",
        stock="3",
        status="OK",
        family="Futones",
        provider="-",
        m3="0.42",
        sku_woo="0201014",
        measures="140 x 200",
        material="Algodon",
        sync_woo="-",
        notes="",
        raw={"item_id": 201014, "store_stock": 1, "warehouse_stock": 2},
    )


class InventoryStockMovementTests(unittest.TestCase):
    def test_stock_movement_requires_reason(self) -> None:
        app = InventoryStockCollector(Session())

        with self.assertRaisesRegex(ValueError, "motivo"):
            app._inventory_stock_form_values("2", "", "   ")

    def test_preview_keeps_store_and_warehouse_separate(self) -> None:
        app = InventoryStockCollector(Session())

        with patch("futonhub.ui.erp.inventory_stock.preview_internal_inventory_update", return_value={"before": {}, "after": {}}) as preview, patch(
            "futonhub.ui.erp.inventory_stock.format_internal_inventory_preview",
            return_value="PREVIEW",
        ):
            text = app._inventory_stock_preview_text(inventory_item(), "4", "", "Ajuste tienda")

        self.assertEqual(text, "PREVIEW")
        preview.assert_called_once_with(app._cloud_session, 201014, "4", None, "Ajuste tienda")

    def test_existing_service_blocks_negative_store_stock(self) -> None:
        with patch("futonhub.cloud.services.inventory._fetch_inventory_item_by_id", return_value={"item_id": 201014, "store_stock": 1, "warehouse_stock": 2}):
            with self.assertRaisesRegex(Exception, "Stock tienda no puede ser negativo"):
                inventory_service.preview_internal_inventory_update(Session(), 201014, "-1", None, "Ajuste")

    def test_apply_uses_existing_service_and_preserves_operation_id(self) -> None:
        app = InventoryStockCollector(Session())
        result = {"operation_id": "INVREAL-1"}

        with patch("futonhub.ui.erp.inventory_stock.update_internal_inventory_item", return_value=result) as update_item, patch(
            "futonhub.ui.erp.inventory_stock.load_settings",
            return_value=Mock(machine_name="TEST"),
        ):
            applied = app._apply_inventory_stock_change(inventory_item(), "", "5", "Ajuste almacen")

        self.assertIs(applied, result)
        update_item.assert_called_once()
        self.assertEqual(update_item.call_args.args[:5], (app._cloud_session, 201014, None, "5", "Ajuste almacen"))

    def test_apply_does_not_touch_woocommerce(self) -> None:
        app = InventoryStockCollector(Session())

        with patch("futonhub.ui.erp.inventory_stock.update_internal_inventory_item", return_value={"operation_id": "INVREAL-1"}), patch(
            "futonhub.ui.erp.inventory_stock.load_settings",
            return_value=Mock(machine_name="TEST"),
        ), patch("futonhub.cloud.services.woocommerce_publish.publish_woocommerce_price") as publish_woo:
            app._apply_inventory_stock_change(inventory_item(), "3", "4", "Ajuste")

        publish_woo.assert_not_called()


if __name__ == "__main__":
    unittest.main()

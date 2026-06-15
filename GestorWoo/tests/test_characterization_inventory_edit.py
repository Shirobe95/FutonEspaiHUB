from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.inventory_edit import ErpInventoryEditMixin  # noqa: E402
from futonhub.ui.erp.shared_ui import InventoryItem  # noqa: E402


class Var:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class ImmediateThread:
    def __init__(self, target, daemon=False) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


class Child:
    def __init__(self) -> None:
        self.cursors: list[str] = []

    def configure(self, **kwargs) -> None:
        if "cursor" in kwargs:
            self.cursors.append(kwargs["cursor"])


class Review:
    def __init__(self) -> None:
        self.child = Child()
        self.destroyed = False
        self.updated = False

    def winfo_children(self) -> list[Child]:
        return [self.child]

    def update_idletasks(self) -> None:
        self.updated = True

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def destroy(self) -> None:
        self.destroyed = True


class DetailWindow:
    def __init__(self) -> None:
        self.destroyed = False

    def winfo_exists(self) -> bool:
        return not self.destroyed

    def destroy(self) -> None:
        self.destroyed = True


class Session:
    user_id = "USER-1"
    email = "admin@example.com"
    role = "admin"


class InventoryEditCollector(ErpInventoryEditMixin):
    def __init__(self, session: object | None = None) -> None:
        self._cloud_session = session
        self._content = object()
        self._current_key = "inventario"
        self._inventory_loaded_once = True
        self._inventory_query = "0201014"
        self.refresh_calls: list[tuple[object, str, bool]] = []

    def after(self, _delay: int, callback) -> None:
        callback()

    def _refresh_inventory(self, content: object, query: str, *, allow_empty: bool) -> None:
        self.refresh_calls.append((content, query, allow_empty))


def inventory_item(**raw_overrides: object) -> InventoryItem:
    raw = {
        "name": "Futon prueba",
        "family": "Futones",
        "subgroup": "Algodon",
        "materials": "Algodon",
        "size": "140 x 200",
        "cubic_meters": "0.42",
        "rotation_c": "",
        "packages": "1",
        "primary_supplier_price": "100.00",
        "pascal_price": "",
        "commercial_status": "Normal",
        "heca_reference": "0201014",
        "woo_sku": "0201014",
        "store_stock": "1",
        "warehouse_stock": "2",
        "notes": "",
    }
    raw.update(raw_overrides)
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
        raw=raw,
    )


class InventoryEditTests(unittest.TestCase):
    def test_initial_editable_values_preserve_item_fields(self) -> None:
        app = InventoryEditCollector()

        values = app._inventory_editable_initial_values(inventory_item(notes="nota interna", pascal_price="88.5"))

        self.assertEqual(values["name"], "Futon prueba")
        self.assertEqual(values["woo_sku"], "0201014")
        self.assertEqual(values["pascal_price"], "88.5")
        self.assertEqual(values["notes"], "nota interna")

    def test_collect_changes_detects_real_changes(self) -> None:
        app = InventoryEditCollector()
        initial = {"name": "Futon prueba", "notes": ""}
        vars_by_field = {"name": Var("Futon prueba XL"), "notes": Var("")}

        changes = app._collect_inventory_detail_changes(initial, vars_by_field)

        self.assertEqual(changes, {"name": ("Futon prueba", "Futon prueba XL")})

    def test_collect_changes_treats_blank_field_as_change_when_previous_value_exists(self) -> None:
        app = InventoryEditCollector()
        initial = {"notes": "nota anterior"}
        vars_by_field = {"notes": Var("   ")}

        changes = app._collect_inventory_detail_changes(initial, vars_by_field)

        self.assertEqual(changes, {"notes": ("nota anterior", "")})

    def test_noop_review_reports_no_pending_changes(self) -> None:
        app = InventoryEditCollector()

        with patch("futonhub.ui.erp.inventory_edit.messagebox.showinfo") as showinfo:
            app._open_inventory_changes_review(object(), inventory_item(), {}, on_discard=None, on_applied=None)

        showinfo.assert_called_once_with("Inventario", "No hay cambios pendientes.")

    def test_apply_changes_calls_internal_inventory_service_and_does_not_touch_woo(self) -> None:
        app = InventoryEditCollector(Session())
        review = Review()
        applied: list[bool] = []

        with (
            patch("futonhub.ui.erp.inventory_edit.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_edit.update_inventory_item_fields", return_value={"operation_id": "INVITEM-1"}) as update_item,
            patch("futonhub.cloud.services.woocommerce_publish.publish_woocommerce_price") as publish_woo,
            patch("futonhub.ui.erp.inventory_edit.messagebox.showinfo") as showinfo,
        ):
            app._apply_inventory_detail_changes(review, inventory_item(), {"name": ("Futon prueba", "Futon XL")}, lambda: applied.append(True))

        update_item.assert_called_once_with(
            app._cloud_session,
            201014,
            {"name": "Futon XL"},
            notes="Cambio aceptado desde detalle completo de Inventario UI ERP.",
        )
        publish_woo.assert_not_called()
        self.assertTrue(review.destroyed)
        self.assertEqual(applied, [True])
        showinfo.assert_called_once()

    def test_apply_changes_reports_service_failure_without_destroying_review(self) -> None:
        app = InventoryEditCollector(Session())
        review = Review()

        with (
            patch("futonhub.ui.erp.inventory_edit.threading.Thread", ImmediateThread),
            patch("futonhub.ui.erp.inventory_edit.update_inventory_item_fields", side_effect=RuntimeError("servicio caido")),
            patch("futonhub.ui.erp.inventory_edit.messagebox.showerror") as showerror,
        ):
            app._apply_inventory_detail_changes(review, inventory_item(), {"name": ("A", "B")}, None)

        self.assertFalse(review.destroyed)
        self.assertEqual(review.child.cursors, ["watch", ""])
        showerror.assert_called_once()
        self.assertIn("servicio caido", showerror.call_args.args[1])

    def test_after_inventory_item_updated_refreshes_current_inventory_view(self) -> None:
        app = InventoryEditCollector(Session())
        detail_window = DetailWindow()

        app._after_inventory_item_updated(detail_window)

        self.assertTrue(detail_window.destroyed)
        self.assertFalse(app._inventory_loaded_once)
        self.assertEqual(app.refresh_calls, [(app._content, "0201014", True)])


if __name__ == "__main__":
    unittest.main()

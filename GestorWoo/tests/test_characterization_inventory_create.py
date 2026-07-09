from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp import inventory_create  # noqa: E402
from futonhub.cloud.services import inventory as inventory_service  # noqa: E402
from futonhub.ui.erp.inventory_create import ErpInventoryCreateMixin  # noqa: E402


class Session:
    user_id = "USER-1"
    email = "admin@example.com"
    role = "admin"


class FakeWidget:
    def __init__(self, *args, **kwargs) -> None:
        self.destroyed = False

    def pack(self, *args, **kwargs) -> None:
        return None

    def grid(self, *args, **kwargs) -> None:
        return None

    def columnconfigure(self, *args, **kwargs) -> None:
        return None

    def rowconfigure(self, *args, **kwargs) -> None:
        return None

    def configure(self, *args, **kwargs) -> None:
        return None

    def bind(self, *args, **kwargs) -> None:
        return None

    def title(self, *args, **kwargs) -> None:
        return None

    def geometry(self, *args, **kwargs) -> None:
        return None

    def transient(self, *args, **kwargs) -> None:
        return None

    def grab_set(self, *args, **kwargs) -> None:
        return None

    def destroy(self) -> None:
        self.destroyed = True

    def set(self, *args, **kwargs) -> None:
        return None


class FakeCanvas(FakeWidget):
    def create_window(self, *args, **kwargs) -> None:
        return None

    def yview(self, *args, **kwargs) -> None:
        return None

    def bbox(self, *args, **kwargs) -> tuple[int, int, int, int]:
        return (0, 0, 1, 1)


class FakeEntry(FakeWidget):
    instances: list["FakeEntry"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.value = ""
        FakeEntry.instances.append(self)

    def insert(self, _index: int, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeText(FakeWidget):
    instances: list["FakeText"] = []

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.value = ""
        FakeText.instances.append(self)

    def get(self, *args, **kwargs) -> str:
        return self.value


class FakeStringVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeButton(FakeWidget):
    def __init__(self, label: str, command) -> None:
        super().__init__()
        self.label = label
        self.command = command


class InventoryCreateCollector(ErpInventoryCreateMixin):
    def __init__(self, session: object | None = None) -> None:
        self._cloud_session = session
        self._content = object()
        self._inventory_loaded_once = True
        self.buttons: dict[str, FakeButton] = {}
        self.refresh_calls: list[tuple[object, str, bool]] = []

    def _card(self, parent) -> FakeWidget:
        return FakeWidget(parent)

    def _button(self, parent, label: str, command=None, primary: bool = False) -> FakeButton:
        button = FakeButton(label, command)
        self.buttons[label] = button
        return button

    def _refresh_inventory(self, content: object, query: str, *, allow_empty: bool) -> None:
        self.refresh_calls.append((content, query, allow_empty))


def install_tk_fakes():
    FakeEntry.instances = []
    FakeText.instances = []
    return (
        patch.object(inventory_create.tk, "Toplevel", FakeWidget),
        patch.object(inventory_create.tk, "Frame", FakeWidget),
        patch.object(inventory_create.tk, "Label", FakeWidget),
        patch.object(inventory_create.tk, "Canvas", FakeCanvas),
        patch.object(inventory_create.tk, "Entry", FakeEntry),
        patch.object(inventory_create.tk, "Text", FakeText),
        patch.object(inventory_create.tk, "StringVar", FakeStringVar),
        patch.object(inventory_create.ttk, "Scrollbar", FakeWidget),
    )


def fill_required_form_values() -> None:
    # Field order follows _open_create_inventory_item_modal.
    values = {
        0: "201014",
        1: "",
        2: "Futon prueba",
        3: "Normal",
    }
    for index, value in values.items():
        FakeEntry.instances[index].value = value


class InventoryCreateTests(unittest.TestCase):
    def test_inventory_select_columns_include_created_inventory_fields(self) -> None:
        columns = set(inventory_service.INVENTORY_SELECT_COLUMNS.split(","))

        self.assertIn("rotation_c", columns)
        self.assertIn("packages", columns)
        self.assertIn("primary_supplier_price", columns)
        self.assertIn("pascal_price", columns)
        self.assertIn("commercial_status", columns)

    def test_cloud_row_preserves_created_fields_in_inventory_item_raw(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        row = {
            "item_id": 201014,
            "name": "Futon prueba",
            "store_stock": 1,
            "warehouse_stock": 2,
            "rotation_c": 2,
            "packages": 1,
            "primary_supplier_price": 15,
            "pascal_price": 12,
            "commercial_status": "Normal",
        }
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)

        item = app._inventory_item_from_cloud_row(row)

        self.assertIs(item.raw, row)
        self.assertEqual(item.raw["rotation_c"], 2)
        self.assertEqual(item.raw["packages"], 1)
        self.assertEqual(item.raw["primary_supplier_price"], 15)
        self.assertEqual(item.raw["pascal_price"], 12)
        self.assertEqual(item.raw["commercial_status"], "Normal")

    def test_erp_prototype_resolves_create_modal_from_inventory_create_mixin(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        mixin_names = [cls.__name__ for cls in FutonHubErpPrototype.__mro__]

        self.assertLess(mixin_names.index("ErpInventoryCreateMixin"), mixin_names.index("ErpInventoryListMixin"))
        self.assertEqual(FutonHubErpPrototype._open_create_inventory_item_modal.__module__, "futonhub.ui.erp.inventory_create")

    def test_modal_blocks_without_session(self) -> None:
        app = InventoryCreateCollector(None)

        with patch("futonhub.ui.erp.inventory_create.messagebox.showwarning") as showwarning:
            app._open_create_inventory_item_modal()

        showwarning.assert_called_once_with("Inventario", "Inicia sesion en Supabase para crear articulos.")
        self.assertEqual(app.buttons, {})

    def test_preview_payload_preserves_defaults_and_autocompletes_heca_reference(self) -> None:
        app = InventoryCreateCollector(Session())

        with install_tk_fakes()[0], install_tk_fakes()[1], install_tk_fakes()[2], install_tk_fakes()[3], install_tk_fakes()[4], install_tk_fakes()[5], install_tk_fakes()[6], install_tk_fakes()[7]:
            app._open_create_inventory_item_modal()
            fill_required_form_values()
            with patch("futonhub.ui.erp.inventory_create.preview_create_cloud_inventory_item", return_value={"exists": False, "payload": {"item_id": 201014, "name": "Futon prueba"}}) as preview, patch(
                "futonhub.ui.erp.inventory_create.messagebox.showinfo"
            ):
                app.buttons["Preview"].command()

        payload = preview.call_args.args[1]
        self.assertEqual(payload["commercial_status"], "Normal")
        self.assertEqual(payload["packages"], "1")
        self.assertEqual(payload["store_stock"], "0")
        self.assertEqual(payload["warehouse_stock"], "0")
        self.assertEqual(payload["heca_reference"], "0201014")

    def test_duplicate_preview_blocks_create(self) -> None:
        app = InventoryCreateCollector(Session())

        with install_tk_fakes()[0], install_tk_fakes()[1], install_tk_fakes()[2], install_tk_fakes()[3], install_tk_fakes()[4], install_tk_fakes()[5], install_tk_fakes()[6], install_tk_fakes()[7]:
            app._open_create_inventory_item_modal()
            fill_required_form_values()
            with patch(
                "futonhub.ui.erp.inventory_create.preview_create_cloud_inventory_item",
                return_value={"exists": True, "existing": {"item_id": 201014, "name": "Existente"}, "payload": {}},
            ), patch("futonhub.ui.erp.inventory_create.create_cloud_inventory_item") as create_item, patch("futonhub.ui.erp.inventory_create.messagebox.showwarning"):
                app.buttons["Crear articulo"].command()

        create_item.assert_not_called()

    def test_save_after_confirmation_calls_create_and_refreshes_inventory(self) -> None:
        app = InventoryCreateCollector(Session())
        preview_result = {"exists": False, "payload": {"item_id": 201014, "name": "Futon prueba"}}

        with install_tk_fakes()[0], install_tk_fakes()[1], install_tk_fakes()[2], install_tk_fakes()[3], install_tk_fakes()[4], install_tk_fakes()[5], install_tk_fakes()[6], install_tk_fakes()[7]:
            app._open_create_inventory_item_modal()
            fill_required_form_values()
            with patch("futonhub.ui.erp.inventory_create.preview_create_cloud_inventory_item", return_value=preview_result) as preview, patch(
                "futonhub.ui.erp.inventory_create.create_cloud_inventory_item",
                return_value={"operation_id": "INVITEM-1"},
            ) as create_item, patch("futonhub.cloud.services.woocommerce_publish.publish_woocommerce_price") as publish_woo, patch(
                "futonhub.ui.erp.inventory_create.messagebox.askyesno",
                return_value=True,
            ), patch("futonhub.ui.erp.inventory_create.messagebox.showinfo"):
                app.buttons["Crear articulo"].command()

        self.assertEqual(preview.call_count, 1)
        create_item.assert_called_once()
        publish_woo.assert_not_called()
        self.assertFalse(app._inventory_loaded_once)
        self.assertEqual(app.refresh_calls, [(app._content, "201014", True)])
        self.assertIsNot(preview.call_args.args[1], create_item.call_args.args[1])


if __name__ == "__main__":
    unittest.main()

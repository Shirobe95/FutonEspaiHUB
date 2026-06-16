from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import orders as orders_service  # noqa: E402
from futonhub.ui.erp import prototype as prototype_module  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import OrderItem  # noqa: E402


class Entry:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class Window:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class Session:
    user_id = "USER-1"
    email = "admin@example.com"
    role = "admin"


def app() -> FutonHubErpPrototype:
    instance = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
    instance._cloud_session = None
    instance._orders_loaded_once = True
    instance._supplier_orders = []
    instance._selected_supplier_order = None
    constants = {
        "IMPORTE_DESCARGA_MT": 0.0,
        "PC_GASTOS_MANIPULACION": 0.0,
        "PC_GASTOS_FINANCIACION": 0.0,
        "IMPORTES_VARIOS": 0.0,
        "COSTE_TOTAL_DESCARGA_FUTONES_IVA": 0.0,
        "COSTE_DESCARGA_FUTONES_UNIDAD": 0.0,
        "IVA_RECARGO_EQUIVALENCIA": 0.0,
        "IVA_RECARGO_EQUIVALENCIA_FACTOR": 0.0,
        "COSTE_DIARIO_ALMACENAJE_M3": 0.0,
    }
    instance._current_business_constant_values = lambda: constants
    instance._fill_supplier_prices_for_order_items = lambda _provider, items: items
    instance._show_view = lambda _key: None
    return instance


def general_item() -> OrderItem:
    source = {
        "m3_total": 1,
        "m3_und": 1,
        "precio_proveedor": 93.65,
        "rotation_c": 1,
        "packages": 1,
        "cuenta_reparto_descarga": True,
    }
    return OrderItem("201014", "Futon prueba", 1, "1", "Pendiente", "OK", raw={"source_row": source})


def heimei_item() -> OrderItem:
    source = {
        "m3_total": 1,
        "m3_und": 1,
        "precio_proveedor": 94.652,
        "rotation_c": 1,
        "packages": 1,
        "cuenta_reparto_descarga": True,
    }
    return OrderItem("301014", "Tatami prueba", 1, "1", "Pendiente", "OK", raw={"source_row": source})


class SupplierOrderCostTests(unittest.TestCase):
    def test_general_supplier_separates_cost_margin_and_pvp(self) -> None:
        ui = app()

        items, _raw, summary = ui._calculate_supplier_order_in_memory(
            "ekomat",
            {"Rentabilidad %": "30", "Coste transporte + IVA": "1"},
            (general_item(),),
            [],
        )

        source = items[0].raw["source_row"]
        self.assertEqual(source["unit_cost"], 100.0)
        self.assertEqual(source["line_cost"], 100.0)
        self.assertEqual(summary["total_cost"], 100.0)
        self.assertEqual(source["rentabilidad_percent"], 30.0)
        self.assertEqual(source["pvp_unit"], 130.0)
        self.assertEqual(source["pvp_line"], 130.0)

    def test_zero_margin_keeps_pvp_equal_to_real_cost(self) -> None:
        ui = app()

        items, _raw, summary = ui._calculate_supplier_order_in_memory(
            "ekomat",
            {"Rentabilidad %": "0", "Coste transporte + IVA": "1"},
            (general_item(),),
            [],
        )

        source = items[0].raw["source_row"]
        self.assertEqual(source["unit_cost"], 100.0)
        self.assertEqual(source["pvp_unit"], 100.0)
        self.assertEqual(source["pvp_line"], 100.0)
        self.assertEqual(summary["total_cost"], 100.0)

    def test_heimei_supplier_separates_cost_margin_and_pvp(self) -> None:
        ui = app()

        items, _raw, summary = ui._calculate_supplier_order_in_memory(
            "heimei",
            {
                "Rentabilidad %": "30",
                "Precio en Dolares": "100",
                "Precio pagado en Euros": "100",
                "Factura transporte": "0",
                "Derechos aranceles": "0",
            },
            (heimei_item(),),
            [],
        )

        source = items[0].raw["source_row"]
        self.assertEqual(source["unit_cost"], 100.0)
        self.assertEqual(source["line_cost"], 100.0)
        self.assertEqual(summary["total_cost"], 100.0)
        self.assertEqual(source["pvp_unit"], 130.0)
        self.assertEqual(source["pvp_line"], 130.0)

    def test_old_margin_formula_is_not_used_in_order_calculation(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._calculate_supplier_order_in_memory)

        self.assertNotIn("/ (1 - rent_percent / 100)", source)
        self.assertIn("* (1 + rent_percent / 100)", source)

    def test_calculation_rows_show_cost_margin_and_pvp_in_order(self) -> None:
        ui = app()
        items, _raw, _summary = ui._calculate_supplier_order_in_memory(
            "ekomat",
            {"Rentabilidad %": "30", "Coste transporte + IVA": "1"},
            (general_item(),),
            [],
        )

        row = ui._calculation_rows(items, provider="ekomat")[0]

        self.assertEqual(row[-5], "100.00 €")
        self.assertEqual(row[-4], "30")
        self.assertEqual(row[-3], "130.00 €")

    def test_legacy_rows_without_pvp_unit_get_display_fallback_only(self) -> None:
        ui = app()
        item = OrderItem(
            "201014",
            "Futon antiguo",
            1,
            "1",
            "100.00 €",
            "Calculado",
            raw={
                "source_row": {
                    "m3_total": 1,
                    "m3_und": 1,
                    "unit_cost": 100,
                    "precio_coste_final": 100,
                    "line_cost": 100,
                    "rentabilidad_percent": 30,
                    "cuenta_reparto_descarga": True,
                }
            },
        )

        row = ui._calculation_rows((item,), provider="ekomat")[0]

        self.assertEqual(row[-5], "100.00 €")
        self.assertEqual(row[-4], "30")
        self.assertEqual(row[-3], "130.00 €")
        self.assertNotIn("pvp_unit", item.raw["source_row"])

    def test_save_payload_keeps_real_cost_and_pvp_separate(self) -> None:
        ui = app()
        ui._cloud_session = Session()
        items, _raw, _summary = ui._calculate_supplier_order_in_memory(
            "ekomat",
            {"Rentabilidad %": "30", "Coste transporte + IVA": "1"},
            (general_item(),),
            [],
        )
        entries = {"Nombre del pedido": Entry("PED-TEST"), "Rentabilidad %": Entry("30"), "Coste transporte + IVA": Entry("1")}

        with (
            patch.object(prototype_module, "create_supplier_order_draft", return_value={"order_id": "ORDER-1"}),
            patch.object(prototype_module, "update_supplier_order_calculation") as update_calc,
            patch.object(prototype_module.messagebox, "showinfo"),
        ):
            ui._save_supplier_order_draft_from_calc(Window(), "ekomat", entries, {"items": items, "raw_lines": [items[0].raw["source_row"]], "calculated": True})

        payload_item = update_calc.call_args.kwargs["items"][0]
        self.assertEqual(payload_item["unit_cost"], 100.0)
        self.assertEqual(payload_item["line_cost"], 100.0)
        self.assertEqual(payload_item["source_row"]["pvp_unit"], 130.0)
        self.assertEqual(payload_item["source_row"]["pvp_line"], 130.0)

    def test_export_contains_cost_margin_and_pvp_columns(self) -> None:
        ui = app()
        items, _raw, _summary = ui._calculate_supplier_order_in_memory(
            "ekomat",
            {"Rentabilidad %": "30", "Coste transporte + IVA": "1"},
            (general_item(),),
            [],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pedido.xlsx"
            with patch.object(prototype_module.messagebox, "showinfo"):
                ui._export_supplier_order_audit_excel(None, provider="ekomat", values={"Nombre del pedido": "PED-TEST"}, items=items, path=str(path))
            wb = load_workbook(path)
            ws = wb["Líneas calculadas"]
            headers = [cell.value for cell in ws[1]]
            cost_index = headers.index("Coste Final Artículo")

            self.assertEqual(headers[cost_index : cost_index + 3], ["Coste Final Artículo", "Rentabilidad %", "P.V.P."])
            self.assertEqual(ws.cell(row=2, column=cost_index + 1).value, 100)
            self.assertEqual(ws.cell(row=2, column=cost_index + 2).value, 30)
            self.assertEqual(ws.cell(row=2, column=cost_index + 3).value, 130)

    def test_receive_flow_does_not_use_pvp_fields_for_costs(self) -> None:
        receive_source = inspect.getsource(orders_service.receive_supplier_order)

        self.assertIn("unit_cost", orders_service.SUPPLIER_ORDER_ITEM_COLUMNS)
        self.assertIn("line_cost", orders_service.SUPPLIER_ORDER_ITEM_COLUMNS)
        self.assertNotIn("pvp", orders_service.SUPPLIER_ORDER_ITEM_COLUMNS.lower())
        self.assertNotIn("pvp_", receive_source)


if __name__ == "__main__":
    unittest.main()

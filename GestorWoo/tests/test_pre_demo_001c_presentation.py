from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PreDemo001CPresentationTests(unittest.TestCase):
    def test_shell_has_no_global_search_for_any_destination(self) -> None:
        from futonhub.ui.erp.shell import ErpShellNavigationMixin, NAV_ITEMS

        shell = object.__new__(ErpShellNavigationMixin)
        self.assertTrue(all(not shell._global_search_visible_for_view(item.key) for item in NAV_ITEMS))
        self.assertNotIn("Buscar producto, proveedor, informe o incidencia", inspect.getsource(ErpShellNavigationMixin))

    def test_dashboard_is_navigation_only_with_nine_real_cards(self) -> None:
        from futonhub.ui.erp.dashboard import DASHBOARD_MODULES, ErpDashboardMixin
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        source = inspect.getsource(ErpDashboardMixin._build_dashboard)
        self.assertEqual(len(DASHBOARD_MODULES), 9)
        self.assertNotIn('"INICIO"', source)
        self.assertNotIn("Selecciona un módulo", source)
        for card in DASHBOARD_MODULES:
            self.assertTrue(hasattr(FutonHubErpPrototype, {
                "inventario": "_build_inventory", "precios": "_build_prices", "calcular": "_build_order_calc",
                "woocommerce": "_build_woocommerce", "precios_proveedor": "_build_suppliers",
                "informes": "_build_reports", "formulas": "_build_formula_library",
                "seguridad": "_build_security", "configuracion": "_build_settings",
            }[card.key]))

    def test_inventory_hides_internal_cut_label_but_keeps_filters(self) -> None:
        from futonhub.ui.erp.inventory_list import ErpInventoryListMixin

        source = inspect.getsource(ErpInventoryListMixin)
        self.assertNotIn("Inventario fisico 003A", source)
        self.assertNotIn("003A", source)
        self.assertIn("build_catalog_filter_bar", source)
        self.assertIn("Treeview", source)

    def test_price_sync_ui_hides_technical_counters_but_keeps_real_progress(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        popup = inspect.getsource(FutonHubErpPrototype._price_start_live_sync_overlay)
        update = inspect.getsource(FutonHubErpPrototype._price_update_live_sync_overlay)
        workspace = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)
        self.assertIn("Cargando precios...", popup)
        self.assertIn("Progressbar", popup)
        self.assertNotIn("Catálogo canónico esperado", popup)
        self.assertNotIn("Catalogo fisico", workspace)
        self.assertIn("_price_sync_progress.configure", update)
        self.assertIn("Reintentar errores", workspace)

    def test_detail_keeps_two_histories_and_visible_current_value_below_each_chart(self) -> None:
        from futonhub.ui.erp.inventory_detail import ErpInventoryDetailMixin
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        history = inspect.getsource(ErpInventoryDetailMixin._render_inventory_history_card)
        detail = inspect.getsource(FutonHubErpPrototype._open_inventory_detail_window)
        self.assertIn("Valor actual:", history)
        self.assertIn("height=185", history)
        self.assertIn("price_host", detail)
        self.assertIn("stock_host", detail)
        self.assertIn("modal_dimensions_for_viewport", detail)
        self.assertIn("set_minsize_safely(win, min_width, min_height)", detail)


if __name__ == "__main__":
    unittest.main()

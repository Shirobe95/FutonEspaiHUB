from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PreDemo001C2PresentationTests(unittest.TestCase):
    def _sync_app(self):
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        app = object.__new__(FutonHubErpPrototype)
        app._price_live_sync_generation = 1
        app._price_live_sync_in_progress = True
        app._price_catalog_items = []
        app._price_available_items = []
        app._inventory_items = []
        app._price_live_price_context_by_physical_item = {}
        app._price_live_sync_summary = {}
        app._price_live_sync_error_physical_item_ids = set()
        app._price_catalog_stage_counts = {}
        app._price_filter_performance = {}
        app._price_search_results = []
        app._price_line_sources = {}
        app._price_live_sync_overlay = None
        app._current_key = "precios"
        app._price_results_from_items = Mock(return_value=[])
        app._price_source_from_inventory_item = Mock(return_value={})
        app._price_update_live_sync_overlay = Mock()
        app._price_stop_live_sync_overlay = Mock()
        app._show_view = Mock()
        return app

    def test_dashboard_has_clean_title_and_exactly_nine_cards(self) -> None:
        from futonhub.ui.erp.dashboard import DASHBOARD_MODULES, ErpDashboardMixin

        source = inspect.getsource(ErpDashboardMixin._build_dashboard)
        self.assertEqual(len(DASHBOARD_MODULES), 9)
        self.assertIn('text="Dashboard"', source)
        self.assertNotIn('"INICIO"', source)
        self.assertNotIn("Selecciona un mÃ³dulo", source)
        self.assertIn("row=(index // 2) + 1", source)

    def test_price_sync_success_closes_the_single_modal_without_success_popup(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        app = self._sync_app()
        result = {
            "live_price_context_by_physical_item": {},
            "counts": {},
            "woo_index": None,
            "approved_edges_by_item_id": {},
        }
        with patch("futonhub.ui.erp.prototype.write_catalog_count_audit"), patch("futonhub.ui.erp.prototype.write_filter_performance"), patch("futonhub.ui.erp.prototype.messagebox.showinfo") as success_popup:
            app._finish_initial_live_sync(result, "", 1)
        app._price_stop_live_sync_overlay.assert_called_once_with()
        app._show_view.assert_called_once_with("precios")
        success_popup.assert_not_called()
        self.assertEqual(app._price_items_error, "")
        self.assertEqual(app._price_live_sync_completed, True)

    def test_price_sync_error_closes_modal_and_leaves_a_visible_module_error(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        app = self._sync_app()
        terminal = {"live_price_context_by_physical_item": {}, "error_physical_item_ids": [], "counts": {}}
        with patch("futonhub.ui.erp.prototype.terminal_reconciliation_error", return_value=terminal), patch("futonhub.ui.erp.prototype.write_catalog_count_audit"), patch("futonhub.ui.erp.prototype.write_filter_performance"):
            app._finish_initial_live_sync(None, "Woo timeout", 1)
        app._price_stop_live_sync_overlay.assert_called_once_with()
        app._show_view.assert_called_once_with("precios")
        self.assertIn("ERROR_SYNC", app._price_items_error)

    def test_price_sync_keeps_real_progress_and_reuses_one_modal(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        start = inspect.getsource(FutonHubErpPrototype._price_start_live_sync_overlay)
        update = inspect.getsource(FutonHubErpPrototype._price_update_live_sync_overlay)
        finish = inspect.getsource(FutonHubErpPrototype._finish_initial_live_sync)
        self.assertIn("if current is not None", start)
        self.assertIn("return current", start)
        self.assertIn("Progressbar", start)
        self.assertIn("_price_sync_progress.configure", update)
        self.assertNotIn("Precios cargados.", update)
        self.assertIn("_price_stop_live_sync_overlay()", finish)
        self.assertNotIn("messagebox", finish)

    def test_only_requested_module_labels_are_removed_and_controls_remain(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        orders = inspect.getsource(FutonHubErpPrototype._build_order_calc)
        woo = inspect.getsource(FutonHubErpPrototype._build_woocommerce)
        supplier_prices = inspect.getsource(FutonHubErpPrototype._build_supplier_prices)
        self.assertNotIn('"Operaciones"', orders)
        self.assertIn("_order_provider_button", orders)
        self.assertIn("_order_table", orders)
        self.assertNotIn('"Gestion"', woo)
        self.assertIn("Sincronizar + Autoclasificar", woo)
        self.assertNotIn('"Gestion"', supplier_prices)
        self.assertIn('"Actualizar"', supplier_prices)

    def test_formula_library_removes_summary_indicators_without_losing_read_only_catalogue(self) -> None:
        from futonhub.ui.erp.formula_library import (
            FORMULA_LIBRARY,
            ErpFormulaLibraryMixin,
            render_formula_library_html,
        )

        source = inspect.getsource(ErpFormulaLibraryMixin._build_formula_library)
        self.assertEqual(len(FORMULA_LIBRARY), 31)
        self.assertNotIn("metrics =", source)
        self.assertNotIn("self._metric", source)
        self.assertIn("formula_sections", source)
        self.assertIn("FORMULA_CATEGORIES", source)
        self.assertIn("_formula_library_card", source)
        html = render_formula_library_html()
        self.assertNotIn('class="metrics"', html)
        self.assertNotIn('class="metric"', html)

    def test_shell_hides_prototype_subtitle_without_restoring_global_search(self) -> None:
        from futonhub.ui.erp.shell import ErpShellNavigationMixin, NAV_ITEMS

        source = inspect.getsource(ErpShellNavigationMixin)
        shell = object.__new__(ErpShellNavigationMixin)
        self.assertNotIn("ERP privado - prototipo", source)
        self.assertTrue(all(not shell._global_search_visible_for_view(item.key) for item in NAV_ITEMS))
        self.assertIn("if tag:", inspect.getsource(ErpShellNavigationMixin._page_header))


if __name__ == "__main__":
    unittest.main()

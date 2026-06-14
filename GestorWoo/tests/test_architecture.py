from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class NamespaceArchitectureTests(unittest.TestCase):
    def test_hub_implementation_lives_in_futonhub_ui(self) -> None:
        from futonhub.app.hub import FutonEspaiHub, FutonHubApp, run_hub
        from gestorwoo.hub import FutonEspaiHub as LegacyHub

        self.assertIs(FutonHubApp, FutonEspaiHub)
        self.assertIs(LegacyHub, FutonEspaiHub)
        self.assertEqual(run_hub.__module__, "futonhub.ui.erp.hub")

    def test_hub_large_blocks_are_split_into_mixins(self) -> None:
        from futonhub.ui.erp.hub import FutonEspaiHub

        mixin_names = [cls.__name__ for cls in FutonEspaiHub.__mro__]
        for expected in (
            "LoginMixin",
            "DiagnosticsMixin",
            "ProjectCatalogMixin",
            "ProjectCardsMixin",
            "ProjectLaunchingMixin",
            "CloudInventoryBoardMixin",
            "CloudPriceBoardMixin",
            "CloudAdminToolsMixin",
        ):
            self.assertIn(expected, mixin_names)

        self.assertEqual(FutonEspaiHub._login_supabase.__module__, "futonhub.ui.erp.login")
        self.assertEqual(FutonEspaiHub._show_diagnostics.__module__, "futonhub.ui.erp.diagnostics")
        self.assertEqual(FutonEspaiHub._build_projects.__module__, "futonhub.ui.erp.project_catalog")
        self.assertEqual(FutonEspaiHub._project_card.__module__, "futonhub.ui.erp.project_cards")
        self.assertEqual(FutonEspaiHub._launch.__module__, "futonhub.ui.erp.launching")

    def test_cloud_services_legacy_modules_reexport_futonhub_implementations(self) -> None:
        from futonhub.cloud.services.prices import price_safety_preview
        from gestorwoo.cloud.services.prices import price_safety_preview as legacy_price_safety_preview
        from gestorwoo.cloud.operational import list_real_price_proposals

        self.assertIs(legacy_price_safety_preview, price_safety_preview)
        self.assertEqual(list_real_price_proposals.__module__, "futonhub.cloud.services.price_proposals")

    def test_legacy_cli_imports_canonical_hub(self) -> None:
        import gestorwoo.cli as cli

        self.assertEqual(cli.run_hub.__module__, "futonhub.ui.erp.hub")

    def test_erp_prototype_is_isolated_and_includes_real_navigation(self) -> None:
        from futonhub.ui.erp.prototype import NAV_ITEMS, FutonHubErpPrototype, run_erp_prototype

        labels = [item.label for item in NAV_ITEMS]
        for expected in (
            "Dashboard",
            "Inventario",
            "Cambio de Precios",
            "Pedidos",
            "WooCommerce",
            "Informes / Exportaciones",
            "Configuracion",
            "Seguridad / Logs",
        ):
            self.assertIn(expected, labels)
        self.assertNotIn("Proveedores", labels)
        self.assertEqual(run_erp_prototype.__module__, "futonhub.ui.erp.prototype")
        self.assertEqual(FutonHubErpPrototype._show_startup_login.__module__, "futonhub.ui.erp.prototype")
        self.assertEqual(FutonHubErpPrototype._login_supabase.__module__, "futonhub.ui.erp.prototype")
        self.assertEqual(FutonHubErpPrototype._finish_login.__module__, "futonhub.ui.erp.prototype")


if __name__ == "__main__":
    unittest.main()

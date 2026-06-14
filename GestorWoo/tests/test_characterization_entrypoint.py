from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))


class EntrypointContractTests(unittest.TestCase):
    def test_official_bat_opens_erp_prototype_command(self) -> None:
        bat_text = (PROJECT_ROOT / "Abrir ERP.bat").read_text(encoding="utf-8")

        self.assertIn('cd /d "%~dp0GestorWoo"', bat_text)
        self.assertIn("%PYTHON_CMD% gestorwoo.py erp-prototype", bat_text)
        self.assertNotIn("%PYTHON_CMD% gestorwoo.py hub", bat_text)

    def test_cli_keeps_erp_prototype_bound_to_prototype_module(self) -> None:
        import gestorwoo.cli as cli

        self.assertEqual(cli.run_erp_prototype.__module__, "futonhub.ui.erp.prototype")

        cli_source = Path(cli.__file__).read_text(encoding="utf-8")
        self.assertIn('subparsers.add_parser("erp-prototype"', cli_source)
        self.assertIn('if args.command == "erp-prototype":', cli_source)
        self.assertIn("run_erp_prototype()", cli_source)


class NavigationContractTests(unittest.TestCase):
    def test_navigation_keys_labels_groups_and_order_are_stable(self) -> None:
        from futonhub.ui.erp.prototype import NAV_ITEMS

        actual = [(item.key, item.label, item.group) for item in NAV_ITEMS]

        self.assertEqual(
            actual,
            [
                ("dashboard", "Dashboard", "Principal"),
                ("inventario", "Inventario", "Operaciones"),
                ("precios", "Cambio de Precios", "Operaciones"),
                ("calcular", "Pedidos", "Operaciones"),
                ("woocommerce", "WooCommerce", "Gestion"),
                ("precios_proveedor", "Precio Proveedores", "Gestion"),
                ("informes", "Informes / Exportaciones", "Gestion"),
                ("seguridad", "Seguridad / Logs", "Sistema"),
                ("configuracion", "Configuracion", "Sistema"),
            ],
        )

    def test_navigation_still_uses_prototype_view_methods(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        expected_methods = {
            "dashboard": "_build_dashboard",
            "inventario": "_build_inventory",
            "precios": "_build_prices",
            "calcular": "_build_order_calc",
            "woocommerce": "_build_woocommerce",
            "precios_proveedor": "_build_suppliers",
            "informes": "_build_reports",
            "seguridad": "_build_security",
            "configuracion": "_build_settings",
        }

        for key, method_name in expected_methods.items():
            with self.subTest(nav_key=key):
                self.assertTrue(hasattr(FutonHubErpPrototype, method_name))


if __name__ == "__main__":
    unittest.main()


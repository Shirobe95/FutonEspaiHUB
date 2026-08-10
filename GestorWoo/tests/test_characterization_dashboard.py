from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.dashboard import DASHBOARD_MODULES, ErpDashboardMixin, dashboard_modules, dashboard_summary  # noqa: E402
from futonhub.ui.erp.shell import NAV_ITEMS  # noqa: E402


class DashboardNavigationTests(unittest.TestCase):
    def test_dashboard_exposes_only_real_shell_destinations(self) -> None:
        nav_keys = {item.key for item in NAV_ITEMS}
        self.assertTrue(DASHBOARD_MODULES)
        self.assertTrue({module.key for module in DASHBOARD_MODULES}.issubset(nav_keys))
        self.assertEqual(len({module.key for module in DASHBOARD_MODULES}), len(DASHBOARD_MODULES))

    def test_dashboard_reports_truthful_access_by_session_role(self) -> None:
        standard = {row["key"]: row for row in dashboard_modules(is_admin=False)}
        admin = {row["key"]: row for row in dashboard_modules(is_admin=True)}

        self.assertEqual(standard["seguridad"]["access"], "RESTRICTED")
        self.assertEqual(admin["seguridad"]["access"], "OPEN")
        self.assertEqual(standard["inventario"]["availability"], "Disponible")
        self.assertEqual(dashboard_summary(admin.values()), {"modules": len(DASHBOARD_MODULES), "available": len(DASHBOARD_MODULES), "restricted": 0})

    def test_dashboard_is_navigation_only_without_kpis_logs_or_service_reads(self) -> None:
        source = inspect.getsource(ErpDashboardMixin._build_dashboard)
        forbidden = (
            "_dashboard_collect_data",
            "list_cloud_supplier_orders",
            "list_real_price_proposals",
            "list_security_audit_logs",
            "Actividad reciente",
            "KPI",
            "Métrica",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, source)

    def test_dashboard_has_scroll_and_official_navigation_actions(self) -> None:
        source = inspect.getsource(ErpDashboardMixin._build_dashboard)
        card_source = inspect.getsource(ErpDashboardMixin._dashboard_module_card)
        self.assertIn("Scrollbar", source)
        self.assertIn("_show_view", card_source)
        self.assertIn("Abrir", card_source)


if __name__ == "__main__":
    unittest.main()

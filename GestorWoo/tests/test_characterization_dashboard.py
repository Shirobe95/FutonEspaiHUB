from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.dashboard import ErpDashboardMixin  # noqa: E402


class Session:
    pass


class DashboardCollector(ErpDashboardMixin):
    def __init__(self, session: object | None) -> None:
        self._cloud_session = session

    def _format_datetime_short(self, value: object) -> str:
        text = str(value or "")
        if not text:
            return "-"
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return text[:16]

    def _normalize_security_level(self, raw: str) -> str:
        value = str(raw or "").strip().upper()
        if value in {"CRITICAL"}:
            return "Critical"
        if value in {"ERROR", "BLOCKED", "REJECTED"}:
            return "Error"
        if value in {"WARNING", "WARN"}:
            return "Warning"
        if value in {"OK", "SUCCESS"}:
            return "OK"
        return "Info"


class DashboardCollectDataTests(unittest.TestCase):
    def test_without_cloud_session_returns_offline_systems_without_service_calls(self) -> None:
        app = DashboardCollector(None)

        with (
            patch("futonhub.ui.erp.dashboard.list_cloud_supplier_orders") as orders,
            patch("futonhub.ui.erp.dashboard.list_real_price_proposals") as proposals,
            patch("futonhub.ui.erp.dashboard.list_security_audit_logs") as logs,
        ):
            data = app._dashboard_collect_data()

        self.assertEqual(data["kpis"]["open_orders"], 0)
        self.assertEqual(
            data["systems"],
            [
                ("Supabase", "Sin sesion activa", "Warning"),
                ("WooCommerce", "Pendiente de validar desde modulo Woo", "Info"),
                ("Seguridad", "Sin logs hasta iniciar sesion", "Info"),
            ],
        )
        orders.assert_not_called()
        proposals.assert_not_called()
        logs.assert_not_called()

    def test_collects_orders_pending_proposals_recent_activity_and_errors_today(self) -> None:
        app = DashboardCollector(Session())
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

        with (
            patch(
                "futonhub.ui.erp.dashboard.list_cloud_supplier_orders",
                return_value=[
                    {
                        "order_id": "PED-1",
                        "provider": "Heimei",
                        "status": "Validacion",
                        "updated_at": "2026-06-15T08:30:00+00:00",
                    },
                    {
                        "order_id": "PED-2",
                        "provider": "Ekomat",
                        "status": "Recibido parcial",
                        "updated_at": "2026-06-15T09:30:00+00:00",
                    },
                    {
                        "order_id": "PED-3",
                        "provider": "Pascal",
                        "status": "Recibido completo",
                        "updated_at": "2026-06-15T10:30:00+00:00",
                    },
                ],
            ) as orders,
            patch(
                "futonhub.ui.erp.dashboard.list_real_price_proposals",
                return_value=[
                    {"name": "Subida general", "status": "pending", "created_at": "2026-06-15T11:00:00+00:00"},
                    {"proposal_name": "Tatamis", "status": "pending", "created_at": "2026-06-15T12:00:00+00:00"},
                ],
            ) as proposals,
            patch(
                "futonhub.ui.erp.dashboard.list_security_audit_logs",
                return_value=[
                    {
                        "created_at": now,
                        "visual_module": "WooCommerce",
                        "visual_action": "Publicar precio",
                        "user_email": "admin@example.com",
                        "status": "ERROR",
                        "message": "Fallo validado",
                    },
                    {
                        "created_at": "2026-06-14T12:00:00+00:00",
                        "visual_module": "Inventario",
                        "visual_action": "Lectura",
                        "user_email": "user@example.com",
                        "status": "SUCCESS",
                    },
                ],
            ) as logs,
        ):
            data = app._dashboard_collect_data()

        self.assertEqual(data["kpis"]["open_orders"], 2)
        self.assertEqual(data["kpis"]["validation_orders"], 1)
        self.assertEqual(data["kpis"]["partial_receipts"], 1)
        self.assertEqual(data["kpis"]["pending_proposals"], 2)
        self.assertEqual(data["kpis"]["errors_today"], 1)
        self.assertEqual(data["open_order_items"][0][0], "PED-1")
        self.assertEqual(data["validation_order_items"][0][2], "Warning")
        self.assertEqual(data["partial_receipt_items"][0][0], "PED-2")
        self.assertEqual(data["proposal_items"][1][0], "Tatamis")
        self.assertEqual(data["error_items"][0], ("WooCommerce - Publicar precio", "Fallo validado", "Error"))
        self.assertEqual(data["systems"][0], ("Supabase", "Sesion activa y lectura operativa", "OK"))
        orders.assert_called_once()
        proposals.assert_called_once_with(app._cloud_session, status="pending", limit=80)
        logs.assert_called_once_with(app._cloud_session, filters={}, limit=80)

    def test_service_errors_are_reported_without_blocking_other_dashboard_sections(self) -> None:
        app = DashboardCollector(Session())

        with (
            patch("futonhub.ui.erp.dashboard.list_cloud_supplier_orders", side_effect=RuntimeError("orders down")),
            patch("futonhub.ui.erp.dashboard.list_real_price_proposals", return_value=[]),
            patch("futonhub.ui.erp.dashboard.list_security_audit_logs", return_value=[]),
        ):
            data = app._dashboard_collect_data()

        self.assertIn("Pedidos no cargados: orders down", data["errors"])
        self.assertEqual(data["kpis"]["pending_proposals"], 0)
        self.assertEqual(data["activity"], [])
        self.assertEqual(data["systems"][2], ("Seguridad", "Logs y rollback activos", "OK"))


if __name__ == "__main__":
    unittest.main()

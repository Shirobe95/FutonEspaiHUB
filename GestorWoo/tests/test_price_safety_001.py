"""Seguridad de precios (auditoria 2026-10, corte 5a): NaN/inf y confirmacion al publicar (los workers SI pueden publicar)."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.audit import CloudAuditError  # noqa: E402
from futonhub.cloud.services.prices import money_or_none, price_safety_preview  # noqa: E402

SETTINGS = SimpleNamespace(price_drop_block_percent=60.0, price_drop_warning_percent=20.0)
ITEM = {"price": "100", "type": "simple"}


class NonFinitePriceTests(unittest.TestCase):
    def test_money_or_none_rejects_non_finite_values(self) -> None:
        for raw in ("nan", "NaN", "inf", "-inf", "Infinity", "1e999", float("nan"), float("inf")):
            with self.subTest(raw=raw):
                self.assertIsNone(money_or_none(raw))

    def test_money_or_none_keeps_valid_values(self) -> None:
        self.assertEqual(money_or_none("12,5"), 12.5)
        self.assertEqual(money_or_none(" 99.90 "), 99.9)
        self.assertEqual(money_or_none(0), 0.0)
        self.assertIsNone(money_or_none(""))
        self.assertIsNone(money_or_none(None))

    def test_safety_preview_blocks_non_finite_proposals(self) -> None:
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                result = price_safety_preview(ITEM, "product", bad, SETTINGS)
                self.assertEqual(result["status"], "ERROR")
                self.assertTrue(any("no es un numero valido" in m for m in result["messages"]))

    def test_safety_preview_still_accepts_normal_prices(self) -> None:
        self.assertEqual(price_safety_preview(ITEM, "product", 105.0, SETTINGS)["status"], "OK")
        self.assertEqual(price_safety_preview(ITEM, "product", 0.0, SETTINGS)["status"], "ERROR")

    def test_ui_price_helpers_reject_non_finite(self) -> None:
        try:
            from futonhub.ui.erp.prototype import FutonHubErpPrototype as App
        except Exception as exc:  # pragma: no cover - sin tkinter
            self.skipTest(f"prototype no importable: {exc}")
        for call in (
            lambda: App._price_calculate_new_price(None, 100.0, "nan", ""),
            lambda: App._price_calculate_new_price(None, 100.0, "", "inf"),
            lambda: App._price_parse_money(None, "nan"),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(App._price_calculate_new_price(None, 100.0, "10", ""), 110.0)
        self.assertEqual(App._price_calculate_new_price(None, 100.0, "", "-5"), 95.0)
        level, message = App._price_validate_proposed_price(None, 100.0, math.nan)
        self.assertEqual(level, "Critical")
        self.assertIn("NaN", message)


class _ExplodingClient:
    def __getattr__(self, name):  # cualquier acceso a red/BD es un fallo del test
        raise AssertionError(f"No debe haber E/S antes de validar rol y confirmacion: {name}")


class PublishGuardsTests(unittest.TestCase):
    def session(self, role: str):
        return SimpleNamespace(client=_ExplodingClient(), user_id="u-1", email="a@b.c", role=role, display_name="Ana")

    def publish(self, role: str, confirm: str):
        from futonhub.cloud.services.woocommerce_publish import publish_woocommerce_price

        return publish_woocommerce_price(
            self.session(role), proposal_id="p-1", confirm=confirm, acknowledge_warnings=True, settings=SimpleNamespace()
        )

    def test_worker_can_publish_when_confirmed(self) -> None:
        # Decision de negocio: los workers publican. Pasa los controles y falla despues, en la E/S (cliente falso).
        with self.assertRaises(Exception) as caught:
            self.publish("worker", "PUBLICAR")
        self.assertNotIn("admin", str(caught.exception).lower().replace("administr", ""))
        self.assertNotIn("confirmacion explicita", str(caught.exception))

    def test_missing_or_wrong_confirmation_is_rejected_before_any_io(self) -> None:
        for confirm in ("", "publicar ya", "SI", None):
            with self.subTest(confirm=confirm), self.assertRaisesRegex(CloudAuditError, "PUBLICAR"):
                self.publish("admin", confirm or "")

    def test_admin_with_confirmation_proceeds_past_the_guards(self) -> None:
        # Pasa los dos controles y falla despues, al intentar usar la BD (prueba de que los controles no bloquean el flujo legitimo).
        with self.assertRaises(Exception) as caught:
            self.publish("admin", " publicar ")
        self.assertNotIn("Solo un admin", str(caught.exception))
        self.assertNotIn("confirmacion explicita", str(caught.exception))


class PublishButtonRoleTests(unittest.TestCase):
    def test_price_window_shows_publish_buttons_to_workers_too(self) -> None:
        source = (SRC / "futonhub" / "ui" / "erp" / "cloud_prices.py").read_text(encoding="utf-8")
        self.assertIn('self._effective_role() or "") in {"admin", "worker"}', source)
        self.assertNotIn("if self._is_authenticated_admin():\n            ttk.Button(buttons, text=\"Preview Woo\"", source)


if __name__ == "__main__":
    unittest.main()

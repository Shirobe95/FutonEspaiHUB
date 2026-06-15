from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import security_logs  # noqa: E402
from gestorwoo.config import Settings  # noqa: E402


def _settings() -> Settings:
    return Settings(
        woocommerce_url="https://example.test",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        db_path=ROOT / "data" / "gestorwoo.sqlite3",
        app_mode="supabase_guarded",
        machine_name="TEST",
        env_path=ROOT / ".env",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        supabase_service_key="",
        sync_role="admin",
        hub_user_email="admin@example.test",
        price_drop_warning_percent=30.0,
        price_drop_block_percent=60.0,
    )


class Response:
    def __init__(self, data=None) -> None:
        self.data = data or []


class TableRecorder:
    def __init__(self, table_name: str, calls: list[dict]) -> None:
        self.table_name = table_name
        self.calls = calls
        self.payload = None
        self.filters: list[tuple[str, object]] = []

    def update(self, payload):
        self.payload = dict(payload)
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        self.calls.append({"table": self.table_name, "payload": self.payload, "filters": self.filters})
        return Response([self.payload or {}])


class ClientRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def table(self, table_name: str) -> TableRecorder:
        return TableRecorder(table_name, self.calls)


class Session:
    def __init__(self) -> None:
        self.client = ClientRecorder()
        self.user_id = "admin"
        self.email = "admin@example.test"
        self.role = "admin"


class JsonResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return dict(self._data)


class FakeWooClient:
    instances: list["FakeWooClient"] = []
    verified_data = {"price": "128.00", "regular_price": "150.00", "sale_price": "128.00"}

    def __init__(self, *_args, **_kwargs) -> None:
        self.product_updates: list[tuple[int, dict]] = []
        self.variation_updates: list[tuple[int, int, dict]] = []
        self.get_paths: list[str] = []
        type(self).instances.append(self)

    def update_product_pricing(self, woo_id: int, payload: dict) -> None:
        self.product_updates.append((woo_id, dict(payload)))

    def update_variation_pricing(self, parent_id: int, woo_id: int, payload: dict) -> None:
        self.variation_updates.append((parent_id, woo_id, dict(payload)))

    def get(self, path: str) -> JsonResponse:
        self.get_paths.append(path)
        return JsonResponse(type(self).verified_data)


def _snapshot(*, kind: str = "product", item_woo_id: int = 777, parent_woo_id: int | None = None) -> dict:
    source_row = {"item_snapshot": {"parent_woo_id": parent_woo_id}} if parent_woo_id else {}
    return {
        "operation_id": "WOOPUBLISH-ORIGINAL",
        "module": "woocommerce_publish",
        "action": "admin_publish_woocommerce_price",
        "entity_type": "price_change_proposal",
        "entity_id": "proposal-1",
        "before_data": {
            "proposal": {
                "id": "proposal-1",
                "item_kind": kind,
                "item_woo_id": item_woo_id,
                "source_row": source_row,
            },
            "cloud_item": {"parent_woo_id": parent_woo_id} if parent_woo_id else {},
            "woo_before": {"price": "128.00", "regular_price": "150.00", "sale_price": "128.00"},
        },
    }


class WooRollbackContractTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeWooClient.instances = []
        FakeWooClient.verified_data = {"price": "128.00", "regular_price": "150.00", "sale_price": "128.00"}

    def test_product_rollback_restores_regular_and_sale_and_marks_proposal(self) -> None:
        session = Session()

        with patch("futonhub.core.config.load_settings", return_value=_settings()), patch(
            "futonhub.cloud.audit.new_operation_id", return_value="RESTORE-1"
        ), patch("futonhub.cloud.audit.write_audit_event", return_value={"ok": True}), patch(
            "gestorwoo.woocommerce.WooCommerceClient", FakeWooClient
        ), patch(
            "futonhub.cloud.services.inventory.sync_woocommerce_price_inventory_state",
            return_value={"history": {}, "resolution": {}},
        ):
            result = security_logs.restore_snapshot_to_previous_state(session, _snapshot())

        woo = FakeWooClient.instances[0]
        self.assertEqual(woo.product_updates, [(777, {"regular_price": "150.00", "sale_price": "128.00"})])
        self.assertEqual(woo.get_paths, ["products/777"])
        self.assertEqual(result["operation_id"], "RESTORE-1")
        self.assertEqual(session.client.calls[0]["table"], "products")
        self.assertEqual(session.client.calls[0]["payload"]["regular_price"], "150.00")
        self.assertEqual(session.client.calls[0]["payload"]["sale_price"], "128.00")
        self.assertEqual(session.client.calls[1]["table"], "price_change_proposals")
        self.assertEqual(session.client.calls[1]["payload"]["status"], "rolled_back")
        self.assertTrue(session.client.calls[1]["payload"]["source_row"]["rolled_back"])

    def test_variation_rollback_uses_parent_path_and_restores_both_price_fields(self) -> None:
        session = Session()

        with patch("futonhub.core.config.load_settings", return_value=_settings()), patch(
            "futonhub.cloud.audit.new_operation_id", return_value="RESTORE-2"
        ), patch("futonhub.cloud.audit.write_audit_event", return_value={"ok": True}), patch(
            "gestorwoo.woocommerce.WooCommerceClient", FakeWooClient
        ), patch(
            "futonhub.cloud.services.inventory.sync_woocommerce_price_inventory_state",
            return_value={"history": {}, "resolution": {}},
        ):
            security_logs.restore_snapshot_to_previous_state(
                session,
                _snapshot(kind="variation", item_woo_id=888, parent_woo_id=777),
            )

        woo = FakeWooClient.instances[0]
        self.assertEqual(woo.variation_updates, [(777, 888, {"regular_price": "150.00", "sale_price": "128.00"})])
        self.assertEqual(woo.get_paths, ["products/777/variations/888"])
        self.assertEqual(session.client.calls[0]["table"], "product_variations")
        self.assertEqual(session.client.calls[0]["filters"], [("woo_id", 888)])

    def test_rollback_fails_if_woo_reread_does_not_confirm_sale_price(self) -> None:
        FakeWooClient.verified_data = {"price": "150.00", "regular_price": "150.00", "sale_price": ""}

        with patch("futonhub.core.config.load_settings", return_value=_settings()), patch(
            "futonhub.cloud.audit.new_operation_id", return_value="RESTORE-3"
        ), patch("futonhub.cloud.audit.write_audit_event", return_value={"ok": True}), patch(
            "gestorwoo.woocommerce.WooCommerceClient", FakeWooClient
        ), patch(
            "futonhub.cloud.services.inventory.sync_woocommerce_price_inventory_state",
            return_value={"history": {}, "resolution": {}},
        ):
            with self.assertRaises(ValueError):
                security_logs.restore_snapshot_to_previous_state(Session(), _snapshot())


if __name__ == "__main__":
    unittest.main()

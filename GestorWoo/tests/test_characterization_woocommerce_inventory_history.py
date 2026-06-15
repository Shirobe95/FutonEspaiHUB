from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import security_logs  # noqa: E402
from futonhub.cloud.services import woocommerce_publish  # noqa: E402
from futonhub.cloud.audit import CloudAuditError  # noqa: E402
from futonhub.cloud.services.inventory import record_woo_price_inventory_history, resolve_inventory_item_id_for_woo_price_event, sync_woocommerce_price_inventory_state  # noqa: E402
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
        self.data = [] if data is None else data


class Query:
    def __init__(self, client: "Client", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.payload = None
        self.filters: list[tuple[str, object]] = []

    def select(self, _columns: str) -> "Query":
        self.operation = "select"
        return self

    def update(self, payload: dict) -> "Query":
        self.operation = "update"
        self.payload = dict(payload)
        return self

    def insert(self, payload: dict) -> "Query":
        self.operation = "insert"
        self.payload = dict(payload)
        return self

    def eq(self, field: str, value: object) -> "Query":
        self.filters.append((field, value))
        return self

    def order(self, _column: str, desc: bool = False) -> "Query":
        return self

    def limit(self, _limit: int) -> "Query":
        return self

    def execute(self) -> Response:
        failure_key = (self.table, self.operation)
        if failure_key in self.client.failures:
            raise RuntimeError(self.client.failures[failure_key])
        rows = self.client.tables.setdefault(self.table, [])
        if self.operation == "insert":
            rows.append(dict(self.payload or {}))
            self.client.calls.append({"table": self.table, "operation": "insert", "payload": dict(self.payload or {})})
            return Response([dict(self.payload or {})])
        matched = list(rows)
        for field, value in self.filters:
            matched = [row for row in matched if row.get(field) == value]
        if self.operation == "update":
            updated = []
            for row in rows:
                if all(row.get(field) == value for field, value in self.filters):
                    row.update(self.payload or {})
                    updated.append(dict(row))
            if not updated and self.table in {"price_change_proposals", "product_variations", "products"}:
                updated = [dict(self.payload or {})]
            self.client.calls.append({
                "table": self.table,
                "operation": "update",
                "payload": dict(self.payload or {}),
                "filters": list(self.filters),
            })
            return Response(updated)
        return Response(matched)


class Client:
    def __init__(self, tables: dict[str, list[dict]], failures: dict[tuple[str, str], str] | None = None) -> None:
        self.tables = tables
        self.failures = failures or {}
        self.calls: list[dict] = []

    def table(self, table: str) -> Query:
        return Query(self, table)


class Session:
    def __init__(self, tables: dict[str, list[dict]], failures: dict[tuple[str, str], str] | None = None) -> None:
        self.client = Client(tables, failures)
        self.user_id = "admin"
        self.email = "admin@example.test"
        self.role = "admin"


class JsonResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return dict(self._data)


class FakeWooClient:
    verified_data = {"price": "138.00", "regular_price": "165.00", "sale_price": "138.00"}

    def __init__(self, *_args, **_kwargs) -> None:
        self.variation_updates: list[tuple[int, int, dict]] = []

    def update_variation_pricing(self, parent_id: int, woo_id: int, payload: dict) -> None:
        self.variation_updates.append((parent_id, woo_id, dict(payload)))

    def update_product_pricing(self, woo_id: int, payload: dict) -> None:
        pass

    def get(self, _path: str) -> JsonResponse:
        return JsonResponse(type(self).verified_data)


def _proposal() -> dict:
    return {
        "id": "proposal-0201014",
        "status": "approved",
        "item_kind": "variation",
        "item_woo_id": 9909,
        "local_id": 9909,
        "old_price": "128.00",
        "new_price": "138.00",
        "notes": "",
        "source_row": {
            "item_snapshot": {
                "item_id": 201014,
                "sku": "0201014",
                "woo_id": 9909,
                "parent_woo_id": 3639,
            }
        },
    }


class WooInventoryHistoryPersistenceTests(unittest.TestCase):
    def test_publish_128_to_138_generates_woo_price_history_for_item(self) -> None:
        session = Session(
            {
                "price_change_proposals": [_proposal()],
                "inventory_change_history": [],
                "product_variations": [{"woo_id": 9909}],
                "inventory_items": [{"item_id": 201014, "name": "0201014", "woo_id": 9909, "woo_price": "128.00"}],
            }
        )
        preview_row = {
            "status": "OK",
            "item_kind": "variation",
            "item_woo_id": 9909,
            "name": "0201014",
            "new_price": 138.0,
        }

        with (
            patch.object(woocommerce_publish, "new_operation_id", return_value="WOOPUBLISH-0201014"),
            patch.object(woocommerce_publish, "acquire_system_lock", return_value=True),
            patch.object(woocommerce_publish, "release_system_lock", return_value=True),
            patch.object(woocommerce_publish, "WooCommerceClient", FakeWooClient),
            patch.object(woocommerce_publish, "preview_woocommerce_publish", return_value={"rows": [preview_row]}),
            patch.object(
                woocommerce_publish,
                "_fetch_cloud_item_for_proposal",
                return_value={"parent_woo_id": 3639, "woo_id": 9909},
            ),
            patch.object(
                woocommerce_publish,
                "_fetch_woo_item_readonly",
                side_effect=[
                    {"price": "128.00", "regular_price": "165.00", "sale_price": "128.00"},
                    {"price": "138.00", "regular_price": "165.00", "sale_price": "138.00"},
                ],
            ),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted", return_value={"ok": True}),
            patch.object(woocommerce_publish, "_ensure_audit_persisted", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_woocommerce_price(
                session,
                proposal_id="proposal-0201014",
                confirm="PUBLICAR",
                settings=_settings(),
            )

        self.assertEqual(result["inventory_sync"]["item_id"], 201014)
        self.assertEqual(result["inventory_history_resolution"]["strategy"], "direct_item_id")
        self.assertTrue(result["inventory_history"]["inserted"])
        self.assertEqual(session.client.tables["inventory_items"][0]["woo_price"], "138.00")
        self.assertEqual(
            session.client.tables["inventory_change_history"],
            [
                {
                    "item_id": 201014,
                    "item_name": "0201014",
                    "field": "woo_price",
                    "field_name": "woo_price",
                    "old_value": "128.00",
                    "new_value": "138.00",
                    "operation_id": "WOOPUBLISH-0201014",
                    "message": "Precio Woo publicado y verificado.",
                    "notes": "Precio Woo publicado y verificado.",
                    "source": "woocommerce_publish",
                    "change_source": "woocommerce_publish",
                    "action": "admin_publish_woocommerce_price",
                    "metadata": result["inventory_history"]["row"]["metadata"],
                }
            ],
        )

    def test_rollback_138_to_128_appends_second_history_event_without_deleting_publish_event(self) -> None:
        session = Session(
            {
                "price_change_proposals": [{"id": "proposal-0201014", "status": "published", "source_row": {}}],
                "inventory_change_history": [
                    {
                        "item_id": 201014,
                        "field": "woo_price",
                        "old_value": "128.00",
                        "new_value": "138.00",
                        "operation_id": "WOOPUBLISH-0201014",
                    }
                ],
                "product_variations": [{"woo_id": 9909}],
                "inventory_items": [{"item_id": 201014, "name": "0201014", "woo_id": 9909, "woo_price": "138.00"}],
            }
        )
        snapshot = {
            "operation_id": "WOOPUBLISH-0201014",
            "module": "woocommerce_publish",
            "action": "admin_publish_woocommerce_price",
            "entity_type": "price_change_proposal",
            "entity_id": "proposal-0201014",
            "before_data": {
                "proposal": _proposal(),
                "cloud_item": {"parent_woo_id": 3639, "woo_id": 9909},
                "woo_before": {"price": "128.00", "regular_price": "165.00", "sale_price": "128.00"},
                "preview_row": {"new_price": "138.00"},
            },
        }
        FakeWooClient.verified_data = {"price": "128.00", "regular_price": "165.00", "sale_price": "128.00"}

        with (
            patch("futonhub.core.config.load_settings", return_value=_settings()),
            patch("futonhub.cloud.audit.new_operation_id", return_value="RESTORE-0201014"),
            patch("futonhub.cloud.audit.write_audit_event", return_value={"ok": True}),
            patch("gestorwoo.woocommerce.WooCommerceClient", FakeWooClient),
        ):
            result = security_logs.restore_snapshot_to_previous_state(session, snapshot)

        self.assertEqual(result["inventory_sync"]["item_id"], 201014)
        self.assertTrue(result["inventory_history"]["inserted"])
        self.assertEqual(session.client.tables["inventory_items"][0]["woo_price"], "128.00")
        self.assertEqual(len(session.client.tables["inventory_change_history"]), 2)
        self.assertEqual(session.client.tables["inventory_change_history"][0]["operation_id"], "WOOPUBLISH-0201014")
        self.assertEqual(session.client.tables["inventory_change_history"][1]["operation_id"], "RESTORE-0201014")
        self.assertEqual(session.client.tables["inventory_change_history"][1]["old_value"], "138.00")
        self.assertEqual(session.client.tables["inventory_change_history"][1]["new_value"], "128.00")

    def test_inventory_mirror_failure_does_not_declare_publish_success(self) -> None:
        session = Session(
            {
                "price_change_proposals": [_proposal()],
                "inventory_change_history": [],
                "product_variations": [{"woo_id": 9909}],
                "inventory_items": [{"item_id": 201014, "name": "0201014", "woo_id": 9909, "woo_price": "128.00"}],
                "audit_logs": [],
            },
            failures={("inventory_items", "update"): "RLS denied inventory_items update"},
        )
        preview_row = {"status": "OK", "item_kind": "variation", "item_woo_id": 9909, "name": "0201014", "new_price": 138.0}

        with (
            patch.object(woocommerce_publish, "new_operation_id", return_value="WOOPUBLISH-FAIL-MIRROR"),
            patch.object(woocommerce_publish, "acquire_system_lock", return_value=True),
            patch.object(woocommerce_publish, "release_system_lock", return_value=True),
            patch.object(woocommerce_publish, "WooCommerceClient", FakeWooClient),
            patch.object(woocommerce_publish, "preview_woocommerce_publish", return_value={"rows": [preview_row]}),
            patch.object(woocommerce_publish, "_fetch_cloud_item_for_proposal", return_value={"parent_woo_id": 3639, "woo_id": 9909}),
            patch.object(
                woocommerce_publish,
                "_fetch_woo_item_readonly",
                side_effect=[
                    {"price": "128.00", "regular_price": "165.00", "sale_price": "128.00"},
                    {"price": "138.00", "regular_price": "165.00", "sale_price": "138.00"},
                ],
            ),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted", return_value={"ok": True}),
            patch.object(woocommerce_publish, "_ensure_audit_persisted", return_value={"ok": True}),
            patch.object(woocommerce_publish, "write_audit_event", return_value={"ok": True}) as write_audit,
        ):
            with self.assertRaises(CloudAuditError):
                woocommerce_publish.publish_woocommerce_price(session, proposal_id="proposal-0201014", confirm="PUBLICAR", settings=_settings())

        self.assertEqual(session.client.tables["inventory_items"][0]["woo_price"], "128.00")
        self.assertEqual(session.client.tables["inventory_change_history"], [])
        self.assertEqual(write_audit.call_args.args[1].action, "admin_publish_woocommerce_price_partial_internal_sync_failed")

    def test_inventory_history_failure_does_not_declare_publish_success(self) -> None:
        session = Session(
            {
                "price_change_proposals": [_proposal()],
                "inventory_change_history": [],
                "product_variations": [{"woo_id": 9909}],
                "inventory_items": [{"item_id": 201014, "name": "0201014", "woo_id": 9909, "woo_price": "128.00"}],
            },
            failures={("inventory_change_history", "insert"): "RLS denied inventory_change_history insert"},
        )

        with self.assertRaises(CloudAuditError):
            sync_woocommerce_price_inventory_state(
                session,
                operation_id="WOOPUBLISH-FAIL-HISTORY",
                proposal=_proposal(),
                cloud_item={"parent_woo_id": 3639, "woo_id": 9909},
                woo_id=9909,
                before_price="128.00",
                verified_price="138.00",
                action="admin_publish_woocommerce_price",
                message="Precio Woo publicado y verificado.",
            )

        self.assertEqual(session.client.tables["inventory_items"][0]["woo_price"], "138.00")
        self.assertEqual(session.client.tables["inventory_change_history"], [])

    def test_internal_retry_sync_does_not_write_woo_again(self) -> None:
        session = Session(
            {
                "inventory_change_history": [],
                "inventory_items": [{"item_id": 201014, "name": "0201014", "woo_id": 9909, "woo_price": "128.00"}],
            }
        )

        result = sync_woocommerce_price_inventory_state(
            session,
            operation_id="WOOPUBLISH-RETRY",
            proposal=_proposal(),
            cloud_item={"parent_woo_id": 3639, "woo_id": 9909},
            woo_id=9909,
            before_price="128.00",
            verified_price="138.00",
            action="admin_publish_woocommerce_price",
            message="Retry interno sin Woo.",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(any(call["table"] == "products" for call in session.client.calls))
        self.assertFalse(any(call["table"] == "product_variations" for call in session.client.calls))

    def test_ambiguous_sku_resolution_does_not_associate_wrong_item(self) -> None:
        proposal = {
            "source_row": {"item_snapshot": {"sku": "0201014"}},
        }
        session = Session(
            {
                "inventory_items": [
                    {"item_id": 1, "woo_sku": "0201014"},
                    {"item_id": 2, "woo_sku": "0201014"},
                ]
            }
        )

        resolution = resolve_inventory_item_id_for_woo_price_event(session, proposal=proposal)

        self.assertIsNone(resolution["item_id"])
        self.assertIn("ambigua", "; ".join(resolution["diagnostics"]))

    def test_variable_product_uses_internal_identity_before_sku(self) -> None:
        proposal = {
            "source_row": {"item_snapshot": {"item_id": 201014, "sku": "0201014", "woo_id": 9909}},
            "item_woo_id": 9909,
        }
        session = Session(
            {
                "inventory_items": [
                    {"item_id": 999999, "woo_sku": "0201014", "woo_id": 9909},
                ]
            }
        )

        resolution = resolve_inventory_item_id_for_woo_price_event(session, proposal=proposal, woo_id=9909)

        self.assertEqual(resolution["item_id"], 201014)
        self.assertEqual(resolution["strategy"], "direct_item_id")

    def test_same_operation_id_does_not_duplicate_inventory_history(self) -> None:
        session = Session(
            {
                "inventory_change_history": [
                    {
                        "item_id": 201014,
                        "field": "woo_price",
                        "old_value": "128.00",
                        "new_value": "138.00",
                        "operation_id": "WOOPUBLISH-0201014",
                    }
                ]
            }
        )

        result = record_woo_price_inventory_history(
            session,
            operation_id="WOOPUBLISH-0201014",
            item_id=201014,
            before="128.00",
            after="138.00",
            action="admin_publish_woocommerce_price",
        )

        self.assertFalse(result["inserted"])
        self.assertEqual(result["reason"], "duplicate")
        self.assertEqual(len(session.client.tables["inventory_change_history"]), 1)

    def test_unresolved_item_id_leaves_diagnostic_without_inventing_history(self) -> None:
        session = Session({"inventory_change_history": []})

        result = record_woo_price_inventory_history(
            session,
            operation_id="WOOPUBLISH-NOITEM",
            item_id=None,
            before="128.00",
            after="138.00",
            action="admin_publish_woocommerce_price",
        )

        self.assertFalse(result["inserted"])
        self.assertEqual(result["reason"], "missing_item_id")
        self.assertEqual(session.client.tables["inventory_change_history"], [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.inventory import fetch_inventory_item_history  # noqa: E402


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class Query:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []

    def select(self, _columns: str) -> "Query":
        return self

    def eq(self, column: str, value: Any) -> "Query":
        self.filters.append((column, value))
        return self

    def order(self, _column: str, desc: bool = False) -> "Query":
        return self

    def limit(self, _limit: int) -> "Query":
        return self

    def execute(self) -> Response:
        rows = list(self.rows)
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return Response(rows)


class Client:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> Query:
        return Query(self.tables.get(name, []))


class Session:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.client = Client(tables)


class InventoryHistorySourceTests(unittest.TestCase):
    def test_woo_publish_and_rollback_logs_are_persisted_but_not_inventory_history_rows(self) -> None:
        session = Session(
            {
                "inventory_change_history": [],
                "audit_logs": [
                    {
                        "created_at": "2026-06-15T10:00:00+00:00",
                        "operation_id": "WOOPUBLISH-1",
                        "module": "woocommerce_publish",
                        "action": "admin_publish_woocommerce_price",
                        "entity_type": "price_change_proposal",
                        "entity_id": "proposal-0201014",
                        "before_data": {
                            "proposal": {
                                "id": "proposal-0201014",
                                "item_kind": "variation",
                                "item_woo_id": 9909,
                                "old_price": "128.00",
                                "new_price": "138.00",
                                "source_row": {
                                    "item_snapshot": {
                                        "sku": "0201014",
                                        "woo_id": 9909,
                                        "parent_woo_id": 3639,
                                    }
                                },
                            },
                            "woo_before": {"regular_price": "165.00", "sale_price": "128.00"},
                        },
                        "after_data": {
                            "woo_after_verified": {"regular_price": "165.00", "sale_price": "138.00"},
                            "pricing_payload": {"sale_price": "138.00"},
                        },
                        "message": "Precio efectivo publicado y verificado en WooCommerce.",
                    },
                    {
                        "created_at": "2026-06-15T10:05:00+00:00",
                        "operation_id": "RESTORE-1",
                        "module": "woocommerce_publish",
                        "action": "restore_woocommerce_price_snapshot",
                        "entity_type": "price_change_proposal",
                        "entity_id": "proposal-0201014",
                        "before_data": {
                            "snapshot": {
                                "operation_id": "WOOPUBLISH-1",
                                "entity_type": "price_change_proposal",
                                "entity_id": "proposal-0201014",
                            }
                        },
                        "after_data": {
                            "woo_verified": {"regular_price": "165.00", "sale_price": "128.00"},
                            "payload": {"regular_price": "165.00", "sale_price": "128.00"},
                        },
                        "message": "Precio Woo restaurado desde snapshot y verificado mediante lectura posterior.",
                    },
                ],
            }
        )

        history = fetch_inventory_item_history(session, 201014, limit=120)

        self.assertEqual(history, [])

    def test_inventory_entity_logs_are_converted_to_visible_history_rows(self) -> None:
        session = Session(
            {
                "inventory_change_history": [],
                "audit_logs": [
                    {
                        "created_at": "2026-06-15T11:00:00+00:00",
                        "operation_id": "INVFIELD-1",
                        "module": "inventory_items",
                        "action": "inventory_item_field_update",
                        "entity_type": "inventory_item",
                        "entity_id": "201014",
                        "before_data": {"item_id": 201014, "woo_price": "128.00", "updated_at": "old"},
                        "after_data": {"item_id": 201014, "woo_price": "138.00", "updated_at": "new"},
                        "message": "Campos internos del item actualizados desde UI ERP.",
                    }
                ],
            }
        )

        history = fetch_inventory_item_history(session, 201014, limit=120)

        self.assertEqual(
            history,
            [
                {
                    "created_at": "2026-06-15T11:00:00+00:00",
                    "operation_id": "INVFIELD-1",
                    "source": "inventory_items.inventory_item_field_update",
                    "field": "woo_price",
                    "before": "128.00",
                    "after": "138.00",
                    "message": "Campos internos del item actualizados desde UI ERP.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

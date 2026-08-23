from __future__ import annotations

import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook, load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import updates  # noqa: E402


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, object]] = []
        self.limit_value: int | None = None
        self.operation = "select"
        self.payload = None

    def select(self, *_args, **_kwargs):
        self.operation = "select"
        return self

    def eq(self, column: str, value):
        self.filters.append((column, value))
        return self

    def limit(self, value: int):
        self.limit_value = int(value)
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = dict(payload)
        return self

    def upsert(self, payload, **_kwargs):
        self.operation = "upsert"
        self.payload = dict(payload)
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def execute(self):
        if self.operation == "update":
            return self._execute_update()
        if self.operation == "upsert":
            return self._execute_upsert()
        if self.operation == "delete":
            return self._execute_delete()
        return self._execute_select()

    def _rows(self):
        return self.client.tables.setdefault(self.table_name, [])

    def _matches(self, row: dict) -> bool:
        for column, value in self.filters:
            if row.get(column) != value:
                return False
        return True

    def _execute_select(self):
        if self.table_name == "supplier_prices":
            self.client.supplier_select_calls += 1
            if self.client.supplier_select_calls in self.client.fail_supplier_select_on_calls:
                raise RuntimeError("forced supplier_prices select failure")
        rows = [dict(row) for row in self._rows() if self._matches(row)]
        if self.limit_value is not None:
            rows = rows[: self.limit_value]
        return FakeResponse(rows)

    def _execute_update(self):
        matched = []
        for row in self._rows():
            if not self._matches(row):
                continue
            if self.client.fail_inventory_update_item_id == row.get("item_id"):
                raise RuntimeError("forced inventory update failure")
            before_payload = dict(self.payload or {})
            self.client.update_payloads.append((self.table_name, row.get("item_id"), before_payload))
            row.update(before_payload)
            matched.append(dict(row))
        return FakeResponse(matched)

    def _execute_upsert(self):
        payload = dict(self.payload or {})
        self.client.upsert_payloads.append((self.table_name, payload))
        if self.table_name == "supplier_prices":
            supplier = str(payload.get("supplier") or "")
            remaining_failures = self.client.fail_supplier_upsert_once_by_supplier.get(supplier, 0)
            if remaining_failures > 0:
                self.client.fail_supplier_upsert_once_by_supplier[supplier] = remaining_failures - 1
                raise RuntimeError(f"forced supplier_prices upsert failure for {supplier}")
        rows = self._rows()
        if self.table_name == "supplier_prices":
            for row in rows:
                if row.get("item_id") == payload.get("item_id") and row.get("supplier") == payload.get("supplier"):
                    row.update(payload)
                    return FakeResponse([dict(row)])
        rows.append(dict(payload))
        return FakeResponse([payload])

    def _execute_delete(self):
        removed = []
        remaining = []
        for row in self._rows():
            if self._matches(row):
                removed.append(dict(row))
            else:
                remaining.append(row)
        self.client.tables[self.table_name] = remaining
        return FakeResponse(removed)


class FakeClient:
    def __init__(self):
        self.tables = {"inventory_items": [], "supplier_prices": []}
        self.update_payloads: list[tuple[str, object, dict]] = []
        self.upsert_payloads: list[tuple[str, dict]] = []
        self.fail_inventory_update_item_id = None
        self.supplier_select_calls = 0
        self.fail_supplier_select_on_calls: set[int] = set()
        self.fail_supplier_upsert_once_by_supplier: dict[str, int] = {}

    def table(self, name: str):
        return FakeQuery(self, name)


def inventory_row(
    item_id: int,
    code: str,
    *,
    name: str = "Item",
    primary_supplier: str | None = "Ekomat",
    commercial_status: str = "Normal",
    rotation_c=1.0,
    store_stock=2,
    warehouse_stock=3,
    primary_supplier_price=10.0,
    pascal_price=8.0,
):
    source_row = {"primary_supplier": primary_supplier} if primary_supplier else {}
    return {
        "item_id": item_id,
        "name": name,
        "hub_item_code": code,
        "heca_reference": code,
        "woo_sku": code,
        "item_record_type": "simple",
        "base_item_code": "",
        "is_pack": False,
        "commercial_status": commercial_status,
        "rotation_c": rotation_c,
        "store_stock": store_stock,
        "warehouse_stock": warehouse_stock,
        "weighted_average_cost": 99.9,
        "primary_supplier_price": primary_supplier_price,
        "pascal_price": pascal_price,
        "supplier_order_provider": "",
        "source_row": source_row,
        "updated_at": "2026-08-01T00:00:00Z",
    }


def supplier_price(item_id: int, supplier: str, price):
    return {
        "item_id": item_id,
        "supplier": supplier,
        "price": price,
        "currency": "EUR",
        "source": "test",
        "updated_at": "2026-08-01T00:00:00Z",
    }


def fake_session(client: FakeClient):
    return SimpleNamespace(user_id="user-1", email="worker@example.test", role="worker", client=client)


def fake_settings():
    return SimpleNamespace(machine_name="test-machine", sync_role="worker")


class UpdatesModule004Tests(unittest.TestCase):
    def test_template_generation_and_excel_parse_preserve_leading_zeros(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "Plantilla_RotacionC.xlsx"
            updates.write_update_template(updates.PROCESS_ROTATION_C, template_path)
            wb = load_workbook(template_path)
            ws = wb.active
            self.assertEqual([ws.cell(1, 1).value, ws.cell(1, 2).value], ["ID", "Rotación C"])
            self.assertIsNone(ws.cell(2, 1).value)
            wb.close()

            data_path = Path(tmp) / "datos.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append(["ID", "Rotación C"])
            ws.append(["0725002", "1,25"])
            ws.append([725003, 2])
            ws.cell(row=3, column=1).number_format = "0000000"
            wb.save(data_path)

            rows = updates.read_updates_workbook(data_path, updates.PROCESS_ROTATION_C)
            self.assertEqual(rows[0]["ID"], "0725002")
            self.assertEqual(rows[1]["ID"], "0725003")

            bad_path = Path(tmp) / "headers_invalidos.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.append([" ID", "Rotación C"])
            wb.save(bad_path)
            with self.assertRaises(updates.UpdatesValidationError):
                updates.read_updates_workbook(bad_path, updates.PROCESS_ROTATION_C)

    def test_rotation_preview_no_change_invalid_duplicate_and_apply_mapping(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(725002, "0725002", rotation_c=1.0),
            inventory_row(725003, "0725003", rotation_c=2.0),
        ]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [
                {"ID": "0725002", "Rotación C": "1,50"},
                {"ID": "0725003", "Rotación C": 2},
            ],
        )
        self.assertTrue(preview["apply_enabled"])
        self.assertEqual(preview["status_counts"], {updates.READY: 1, updates.NO_CHANGE: 1})

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            result = updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(result["status"], "APPLIED")
        self.assertEqual(client.tables["inventory_items"][0]["rotation_c"], 1.5)
        payload_fields = {key for _table, _item_id, payload in client.update_payloads for key in payload}
        self.assertIn("rotation_c", payload_fields)
        self.assertNotIn("weighted_average_cost", payload_fields)

        blocked = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [
                {"ID": "9999999", "Rotación C": 1},
                {"ID": "0725002", "Rotación C": "mal"},
                {"ID": "0725003", "Rotación C": 1},
                {"ID": "0725003", "Rotación C": 1},
            ],
        )
        self.assertFalse(blocked["apply_enabled"])
        self.assertEqual(blocked["status_counts"][updates.INVALID_ID], 1)
        self.assertEqual(blocked["status_counts"][updates.INVALID_VALUE], 1)
        self.assertEqual(blocked["status_counts"][updates.DUPLICATE_ID], 2)

    def test_stock_preview_apply_descatalogado_blank_and_no_weighted_cost_write(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(725002, "0725002", store_stock=2, warehouse_stock=3),
            inventory_row(725004, "0725004", commercial_status="Descatalogado"),
        ]
        session = fake_session(client)

        blocked = updates.preview_updates(
            session,
            updates.PROCESS_STOCK,
            [
                {"ID": "0725004", "Stock Tienda": 1, "Stock Warehouse": 1},
                {"ID": "0725002", "Stock Tienda": "", "Stock Warehouse": 4},
            ],
        )
        self.assertFalse(blocked["apply_enabled"])
        self.assertEqual(blocked["status_counts"][updates.DESCATALOGADO_NO_ACTUALIZABLE], 1)
        self.assertEqual(blocked["status_counts"][updates.INVALID_VALUE], 1)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_STOCK,
            [{"ID": "0725002", "Stock Tienda": 7, "Stock Warehouse": "9"}],
        )
        self.assertEqual(preview["rows"][0]["stock_total_current"], 5.0)
        self.assertEqual(preview["rows"][0]["stock_total_new"], 16.0)
        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            updates.apply_update_preview(session, preview, settings=fake_settings())
        row = client.tables["inventory_items"][0]
        self.assertEqual(row["store_stock"], 7.0)
        self.assertEqual(row["warehouse_stock"], 9.0)
        self.assertEqual(row["weighted_average_cost"], 99.9)
        payload_fields = {key for _table, _item_id, payload in client.update_payloads for key in payload}
        self.assertNotIn("weighted_average_cost", payload_fields)

    def test_supplier_prices_primary_resolution_pascal_blank_and_sync(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(725002, "0725002", primary_supplier="Ekomat", primary_supplier_price=10, pascal_price=8),
            inventory_row(302009, "0302009", primary_supplier="Cipta", primary_supplier_price=20, pascal_price=18),
            inventory_row(201001, "0201001", primary_supplier="Hemei", primary_supplier_price=30, pascal_price=28),
            inventory_row(999001, "0999001", primary_supplier=None, primary_supplier_price=11, pascal_price=9),
        ]
        client.tables["supplier_prices"] = [
            supplier_price(725002, "Ekomat", 10),
            supplier_price(725002, "Pascal", 8),
            supplier_price(302009, "Cipta", 20),
            supplier_price(201001, "Hemei", 30),
        ]
        session = fake_session(client)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [
                {"ID": "0725002", "Precio Principal": "10,50", "Pascal": ""},
                {"ID": "0302009", "Precio Principal": "21.25", "Pascal": ""},
                {"ID": "0201001", "Precio Principal": "", "Pascal": "29,75"},
            ],
        )
        self.assertEqual(preview["status_counts"], {updates.READY: 3})
        self.assertEqual([row["primary_supplier"] for row in preview["rows"]], ["Ekomat", "Cipta", "Hemei"])

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            result = updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(result["status"], "APPLIED")
        by_item = {row["item_id"]: row for row in client.tables["inventory_items"]}
        self.assertEqual(by_item[725002]["primary_supplier_price"], 10.5)
        self.assertEqual(by_item[302009]["primary_supplier_price"], 21.25)
        self.assertEqual(by_item[201001]["pascal_price"], 29.75)
        supplier_lookup = {(row["item_id"], row["supplier"]): row["price"] for row in client.tables["supplier_prices"]}
        self.assertEqual(supplier_lookup[(725002, "Ekomat")], 10.5)
        self.assertEqual(supplier_lookup[(302009, "Cipta")], 21.25)
        self.assertEqual(supplier_lookup[(201001, "Pascal")], 29.75)

        blocked = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [
                {"ID": "0999001", "Precio Principal": "12", "Pascal": ""},
                {"ID": "0725002", "Precio Principal": "", "Pascal": ""},
            ],
        )
        self.assertFalse(blocked["apply_enabled"])
        self.assertEqual(blocked["status_counts"][updates.PRIMARY_SUPPLIER_UNRESOLVED], 1)
        self.assertEqual(blocked["status_counts"][updates.NO_CHANGE], 1)

    def test_six_digit_numeric_id_can_resolve_unique_zero_prefixed_physical_item(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(725002, "0725002"),
            inventory_row(758087, "0758087"),
            inventory_row(1020007, "1020007"),
        ]
        session = fake_session(client)

        valid = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "0725002", "Rotación C": 1.5}],
        )

        self.assertTrue(valid["apply_enabled"])
        self.assertEqual(valid["rows"][0]["item_id"], 725002)
        self.assertEqual(valid["rows"][0]["id"], "0725002")

        without_zero = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "725002", "Rotación C": 1.5}],
        )

        self.assertTrue(without_zero["apply_enabled"])
        self.assertEqual(without_zero["rows"][0]["item_id"], 725002)
        self.assertEqual(without_zero["rows"][0]["id"], "0725002")
        self.assertEqual(without_zero["rows"][0]["requested_id"], "725002")

        invalid = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [
                {"ID": "0758007", "Rotación C": 1},
                {"ID": "1020011", "Rotación C": 1},
            ],
        )

        self.assertFalse(invalid["apply_enabled"])
        self.assertEqual(invalid["status_counts"][updates.INVALID_ID], 2)

    def test_alias_with_same_heca_reference_does_not_make_unique_physical_item_ambiguous(self) -> None:
        client = FakeClient()
        alias = inventory_row(724012, "0724011A")
        alias.update(
            {
                "heca_reference": "0724011",
                "item_record_type": "alias",
                "base_item_code": "0724011",
            }
        )
        client.tables["inventory_items"] = [
            inventory_row(724011, "0724011"),
            alias,
        ]
        session = fake_session(client)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "724011", "Rotación C": 1.5}],
        )

        self.assertTrue(preview["apply_enabled"])
        self.assertEqual(preview["status_counts"], {updates.READY: 1})
        self.assertEqual(preview["rows"][0]["item_id"], 724011)
        self.assertEqual(preview["rows"][0]["id"], "0724011")

    def test_multiple_physical_exact_candidates_still_block_as_ambiguous(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(724011, "0724011"),
            inventory_row(724099, "0724011"),
        ]
        session = fake_session(client)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "0724011", "Rotación C": 1.5}],
        )

        self.assertFalse(preview["apply_enabled"])
        self.assertEqual(preview["status_counts"], {updates.INVALID_ID: 1})
        self.assertIn("ambigua", preview["rows"][0]["reason"])

    def test_zero_prefixed_resolution_does_not_bypass_descatalogado_block(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725001, "0725001", commercial_status="Descatalogado")]
        session = fake_session(client)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_STOCK,
            [{"ID": "725001", "Stock Tienda": 1, "Stock Warehouse": 1}],
        )

        self.assertFalse(preview["apply_enabled"])
        self.assertEqual(preview["status_counts"], {updates.DESCATALOGADO_NO_ACTUALIZABLE: 1})
        self.assertEqual(preview["rows"][0]["id"], "0725001")

    def test_supplier_price_upsert_failure_rolls_back_current_inventory_update(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", primary_supplier_price=10)]
        client.tables["supplier_prices"] = [supplier_price(725002, "Ekomat", 10)]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [{"ID": "0725002", "Precio Principal": 11, "Pascal": ""}],
        )
        client.fail_supplier_upsert_once_by_supplier = {"Ekomat": 1}

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError) as ctx:
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(ctx.exception.result["status"], "ROLLED_BACK")
        self.assertEqual(client.tables["inventory_items"][0]["primary_supplier_price"], 10)
        supplier_lookup = {(row["item_id"], row["supplier"]): row["price"] for row in client.tables["supplier_prices"]}
        self.assertEqual(supplier_lookup[(725002, "Ekomat")], 10)

    def test_pascal_failure_rolls_back_inventory_primary_supplier_and_pascal(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", primary_supplier_price=10, pascal_price=8)]
        client.tables["supplier_prices"] = [
            supplier_price(725002, "Ekomat", 10),
            supplier_price(725002, "Pascal", 8),
        ]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [{"ID": "0725002", "Precio Principal": 11, "Pascal": 9}],
        )
        client.fail_supplier_upsert_once_by_supplier = {"Pascal": 1}

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError) as ctx:
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(ctx.exception.result["status"], "ROLLED_BACK")
        item = client.tables["inventory_items"][0]
        self.assertEqual(item["primary_supplier_price"], 10)
        self.assertEqual(item["pascal_price"], 8)
        supplier_lookup = {(row["item_id"], row["supplier"]): row["price"] for row in client.tables["supplier_prices"]}
        self.assertEqual(supplier_lookup[(725002, "Ekomat")], 10)
        self.assertEqual(supplier_lookup[(725002, "Pascal")], 8)

    def test_supplier_prices_read_failure_blocks_preview(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", primary_supplier_price=10)]
        client.fail_supplier_select_on_calls = {1}
        session = fake_session(client)

        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [{"ID": "0725002", "Precio Principal": 11, "Pascal": ""}],
        )

        self.assertFalse(preview["apply_enabled"])
        self.assertEqual(preview["rows"][0]["status"], updates.SUPPLIER_PRICES_READ_ERROR)
        self.assertIn(updates.SUPPLIER_PRICES_READ_ERROR, updates.BLOCKING_STATUSES)

    def test_supplier_prices_read_failure_before_apply_writes_zero_rows(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", primary_supplier_price=10)]
        client.tables["supplier_prices"] = [supplier_price(725002, "Ekomat", 10)]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [{"ID": "0725002", "Precio Principal": 11, "Pascal": ""}],
        )
        client.fail_supplier_select_on_calls = {client.supplier_select_calls + 1}

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError):
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(client.tables["inventory_items"][0]["primary_supplier_price"], 10)
        self.assertEqual(client.update_payloads, [])
        self.assertEqual(client.upsert_payloads, [])

    def test_supplier_prices_read_failure_during_postcheck_rolls_back(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", primary_supplier_price=10)]
        client.tables["supplier_prices"] = [supplier_price(725002, "Ekomat", 10)]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_SUPPLIER_PRICES,
            [{"ID": "0725002", "Precio Principal": 11, "Pascal": ""}],
        )
        client.fail_supplier_select_on_calls = {client.supplier_select_calls + 2}

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError) as ctx:
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(ctx.exception.result["status"], "ROLLED_BACK")
        self.assertEqual(client.tables["inventory_items"][0]["primary_supplier_price"], 10)
        supplier_lookup = {(row["item_id"], row["supplier"]): row["price"] for row in client.tables["supplier_prices"]}
        self.assertEqual(supplier_lookup[(725002, "Ekomat")], 10)

    def test_drift_before_apply_blocks_without_write(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", rotation_c=1.0)]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "0725002", "Rotación C": 1.5}],
        )
        client.tables["inventory_items"][0]["rotation_c"] = 1.2

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError):
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(client.tables["inventory_items"][0]["rotation_c"], 1.2)
        self.assertEqual(client.update_payloads, [])

    def test_partial_failure_rolls_back_already_applied_rows(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [
            inventory_row(725002, "0725002", store_stock=2, warehouse_stock=3),
            inventory_row(725003, "0725003", store_stock=4, warehouse_stock=5),
        ]
        client.fail_inventory_update_item_id = 725003
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_STOCK,
            [
                {"ID": "0725002", "Stock Tienda": 7, "Stock Warehouse": 8},
                {"ID": "0725003", "Stock Tienda": 9, "Stock Warehouse": 10},
            ],
        )

        with patch.object(updates, "write_snapshot"), patch.object(updates, "write_audit_event"):
            with self.assertRaises(updates.UpdateApplyError) as ctx:
                updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(ctx.exception.result["status"], "ROLLED_BACK")
        by_item = {row["item_id"]: row for row in client.tables["inventory_items"]}
        self.assertEqual(by_item[725002]["store_stock"], 2)
        self.assertEqual(by_item[725002]["warehouse_stock"], 3)
        self.assertEqual(by_item[725003]["store_stock"], 4)
        self.assertEqual(by_item[725003]["warehouse_stock"], 5)

    def test_snapshot_audit_actor_and_postcheck_are_recorded(self) -> None:
        client = FakeClient()
        client.tables["inventory_items"] = [inventory_row(725002, "0725002", rotation_c=1.0)]
        session = fake_session(client)
        preview = updates.preview_updates(
            session,
            updates.PROCESS_ROTATION_C,
            [{"ID": "0725002", "Rotación C": 1.5}],
        )

        with patch.object(updates, "write_snapshot") as snapshots, patch.object(updates, "write_audit_event") as audits:
            result = updates.apply_update_preview(session, preview, settings=fake_settings())

        self.assertEqual(len(result["postcheck"]), 1)
        snapshot_arg = snapshots.call_args.args[1]
        self.assertEqual(snapshot_arg.before_data["actor"]["user_id"], "user-1")
        audit_arg = audits.call_args.args[1]
        self.assertEqual(audit_arg.status, "OK")
        self.assertEqual(audit_arg.after_data["applied_rows"], 1)


class UpdatesNavigationContractTests(unittest.TestCase):
    def test_updates_navigation_entry_and_builder_exist(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype, NAV_ITEMS

        self.assertIn(("actualizaciones", "Actualizaciones", "Operaciones"), [(item.key, item.label, item.group) for item in NAV_ITEMS])
        self.assertTrue(hasattr(FutonHubErpPrototype, "_build_updates"))

    def test_updates_apply_runs_in_background_and_blocks_double_apply(self) -> None:
        from futonhub.ui.erp.prototype import FutonHubErpPrototype

        source = inspect.getsource(FutonHubErpPrototype._build_updates)
        self.assertIn('state: dict[str, Any] = {"preview": None, "applying": False}', source)
        self.assertIn('if state.get("applying"):', source)
        self.assertIn('self._show_working_overlay("Aplicando actualizacion"', source)
        self.assertIn("threading.Thread(target=worker, daemon=True).start()", source)
        self.assertIn("self.after(0, callback)", source)
        self.assertIn("preview_updates_from_excel(session, process, source_path)", source)


if __name__ == "__main__":
    unittest.main()

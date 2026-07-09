from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.audit import CloudAuditError  # noqa: E402
from futonhub.cloud.services import woocommerce_publish  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


def settings():
    return SimpleNamespace(
        woocommerce_url="https://example.invalid",
        consumer_key="key",
        consumer_secret="secret",
        price_drop_warning_percent=30.0,
        price_drop_block_percent=60.0,
        machine_name="TEST",
    )


def proposal(
    row_id: str,
    kind: str,
    woo_id: int,
    *,
    status: str = "published",
    old_price: float = 100.0,
    new_price: float = 110.0,
    parent_id: int | None = None,
) -> dict:
    snapshot = {"type": "simple"}
    if parent_id:
        snapshot["parent_woo_id"] = parent_id
    return {
        "id": row_id,
        "item_kind": kind,
        "item_woo_id": woo_id,
        "old_price": old_price,
        "new_price": new_price,
        "status": status,
        "name": f"{kind} {woo_id}",
        "source_row": {
            "ui_canonical_item_kind": kind,
            "ui_canonical_woo_id": woo_id,
            "ui_line_code": str(woo_id),
            "ui_line_name": f"{kind} {woo_id}",
            "publish_operation_id": "WOOBATCH-1",
            "item_snapshot": snapshot,
        },
    }


def target(kind: str, woo_id: int, parent_id: int | None = None) -> dict:
    if parent_id:
        return {
            "canonical_key": f"{kind}:{woo_id}",
            "canonical_kind": kind,
            "woo_id": woo_id,
            "parent_woo_id": parent_id,
            "remote_kind": "variation",
            "remote_key": f"variation:{parent_id}:{woo_id}",
            "endpoint": f"products/{parent_id}/variations/{woo_id}",
            "cloud_item": {"parent_woo_id": parent_id},
        }
    return {
        "canonical_key": f"{kind}:{woo_id}",
        "canonical_kind": kind,
        "woo_id": woo_id,
        "remote_kind": "product",
        "remote_key": f"product:{woo_id}",
        "endpoint": f"products/{woo_id}",
        "cloud_item": {},
    }


def snapshot_row(row: dict, resolved_target: dict) -> dict:
    return {
        "proposal_id": row["id"],
        "canonical_key": resolved_target["canonical_key"],
        "target": resolved_target,
        "woo_before": {
            "price": str(row["old_price"]),
            "regular_price": str(row["old_price"]),
            "sale_price": "",
        },
        "old_price": row["old_price"],
        "new_price": row["new_price"],
    }


class Response:
    def __init__(self, data=None):
        self.data = data or []


class Query:
    def __init__(self, session, table):
        self.session = session
        self.table_name = table
        self.ids = None
        self.equals = []
        self.payload = None

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, column, values):
        if column == "id":
            self.ids = [str(value) for value in values]
        return self

    def eq(self, column, value):
        self.equals.append((column, value))
        return self

    def limit(self, *_args):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        rows = self.session.tables.setdefault(self.table_name, [])
        selected = list(rows)
        if self.ids is not None:
            selected = [row for row in selected if str(row.get("id")) in self.ids]
        for column, value in self.equals:
            selected = [row for row in selected if row.get(column) == value]
        if self.payload is not None:
            for row in selected:
                row.update(self.payload)
            self.session.updates.append((self.table_name, dict(self.payload), list(self.equals)))
        return Response([dict(row) for row in selected])


class Session:
    def __init__(self, rows, snapshots=None):
        self.tables = {
            "price_change_proposals": rows,
            "operation_snapshots": snapshots or [],
        }
        self.role = "admin"
        self.user_id = "user"
        self.email = "admin@example.invalid"
        self.updates = []
        self.client = self

    def table(self, name):
        return Query(self, name)


class Woo:
    def __init__(self, reads):
        self.reads = {key: [dict(value) for value in values] for key, values in reads.items()}
        self.writes = []

    def get(self, endpoint):
        data = self.reads[endpoint].pop(0)
        return SimpleNamespace(json=lambda: dict(data))

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", woo_id, dict(payload)))
        return {"id": woo_id}

    def update_variation_pricing(self, parent_id, woo_id, payload):
        self.writes.append(("variation", parent_id, woo_id, dict(payload)))
        return {"id": woo_id}


class FailingWoo(Woo):
    def __init__(self, reads, fail_on_write: int, fail_compensation: bool = False):
        super().__init__(reads)
        self.fail_on_write = fail_on_write
        self.fail_compensation = fail_compensation
        self.write_count = 0

    def update_product_pricing(self, woo_id, payload):
        self.write_count += 1
        if self.write_count == self.fail_on_write:
            raise RuntimeError("restore write failed")
        if self.fail_compensation and self.write_count > self.fail_on_write:
            raise RuntimeError("compensation failed")
        return super().update_product_pricing(woo_id, payload)


def restore_preview(rows: list[dict], targets: list[dict]) -> dict:
    preview_rows = []
    for row, resolved_target in zip(rows, targets):
        preview_rows.append({
            "proposal_id": row["id"],
            "canonical_key": resolved_target["canonical_key"],
            "item_kind": row["item_kind"],
            "code": str(row["item_woo_id"]),
            "name": row["name"],
            "published_price": row["new_price"],
            "woo_current_price": row["new_price"],
            "restore_price": row["old_price"],
            "status": "VALIDO",
            "reason": "Restauracion disponible.",
            "target": resolved_target,
            "woo_current_snapshot": {
                "price": str(row["new_price"]),
                "regular_price": str(row["new_price"]),
                "sale_price": "",
            },
            "woo_restore_snapshot": {
                "price": str(row["old_price"]),
                "regular_price": str(row["old_price"]),
                "sale_price": "",
            },
            "proposal": row,
        })
    return {
        "publish_operation_id": "WOOBATCH-1",
        "rows": preview_rows,
        "counts": {"total": len(rows), "valid": len(rows), "errors": 0, "stale": 0},
        "blocking": False,
        "already_restored": False,
    }


class PriceProposalRestoreAndSyncTests(unittest.TestCase):
    def test_publish_updates_inventory_price_through_existing_helper(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("sync_woocommerce_price_inventory_state", source)
        self.assertLess(source.index("_fetch_remote_target"), source.index("sync_woocommerce_price_inventory_state"))

    def test_publish_does_not_mutate_historical_old_price(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertNotIn('"old_price":', source[source.index("now = datetime"):source.index("_ensure_audit_persisted")])

    def test_sync_uses_one_injected_woo_client(self):
        row = proposal("p", "product", 10)
        resolved_target = target("product", 10)
        woo = Woo({"products/10": [{"price": "110", "regular_price": "110"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}) as sync,
        ):
            result = woocommerce_publish.sync_price_proposal_inventory_prices(
                Session([row]), proposal_ids=["p"], settings=settings(), client=woo
            )
        self.assertEqual(result["synced_count"], 1)
        sync.assert_called_once()

    def test_sync_reads_product_destination(self):
        row = proposal("p", "product", 10)
        resolved_target = target("product", 10)
        woo = Woo({"products/10": [{"price": "111"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.sync_price_proposal_inventory_prices(
                Session([row]), proposal_ids=["p"], settings=settings(), client=woo
            )
        self.assertEqual(result["synced"][0]["woo_price"], 111.0)

    def test_sync_reads_variation_destination(self):
        row = proposal("v", "variation", 20, parent_id=7)
        resolved_target = target("variation", 20, 7)
        woo = Woo({"products/7/variations/20": [{"price": "112"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.sync_price_proposal_inventory_prices(
                Session([row]), proposal_ids=["v"], settings=settings(), client=woo
            )
        self.assertEqual(result["synced"][0]["remote_key"], "variation:7:20")

    def test_sync_pack_uses_inventory_resolution_helper(self):
        row = proposal("pack", "pack", 30)
        resolved_target = target("pack", 30)
        woo = Woo({"products/30": [{"price": "113"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}) as sync,
        ):
            woocommerce_publish.sync_price_proposal_inventory_prices(
                Session([row]), proposal_ids=["pack"], settings=settings(), client=woo
            )
        self.assertEqual(sync.call_args.kwargs["proposal"]["item_kind"], "pack")

    def test_sync_duplicate_remote_destination_is_blocked(self):
        rows = [proposal("v", "variation", 20), proposal("pack", "pack", 20)]
        targets = [target("variation", 20, 7), {**target("pack", 20, 7), "remote_key": "variation:7:20"}]
        woo = Woo({"products/7/variations/20": [{"price": "110"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", side_effect=targets),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            with self.assertRaisesRegex(CloudAuditError, "comparten"):
                woocommerce_publish.sync_price_proposal_inventory_prices(
                    Session(rows), proposal_ids=["v", "pack"], settings=settings(), client=woo
                )

    def test_entry_sync_has_required_overlay_and_recency_guard(self):
        source = inspect.getsource(FutonHubErpPrototype._maybe_start_price_woo_sync)
        worker = inspect.getsource(FutonHubErpPrototype._sync_price_module_prices)
        self.assertIn("elapsed < 300", source)
        self.assertIn("Sincronizando precios con WooCommerce...", worker)

    def test_manual_refresh_syncs_before_reloading_proposals(self):
        source = inspect.getsource(FutonHubErpPrototype._sync_price_module_prices)
        sync_call = source.index("sync_price_proposal_inventory_prices")
        refresh_after_sync = source.index("_refresh_price_proposals", sync_call)
        self.assertLess(sync_call, refresh_after_sync)

    def test_sync_failure_is_controlled_and_overlay_closes(self):
        source = inspect.getsource(FutonHubErpPrototype._sync_price_module_prices)
        self.assertIn("_price_stop_working_overlay", source)
        self.assertIn("No se pudieron sincronizar precios Woo", source)

    def test_cache_invalidation_clears_search_and_inventory_copies(self):
        source = inspect.getsource(FutonHubErpPrototype._invalidate_price_inventory_caches)
        for field in ("_price_available_items", "_price_search_results", "_inventory_items"):
            self.assertIn(field, source)
        self.assertIn("_inventory_loaded_once = False", source)

    def test_publish_success_invalidates_cache_without_reopening_erp(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertIn("_invalidate_price_inventory_caches", source)
        self.assertIn("_refresh_price_proposals", source)

    def _snapshot(self, rows, targets):
        return [{
            "operation_id": "WOOBATCH-1",
            "action": "admin_publish_price_proposal_group",
            "before_data": [snapshot_row(row, resolved_target) for row, resolved_target in zip(rows, targets)],
        }]

    def test_restore_preview_requires_complete_snapshot(self):
        row = proposal("p", "product", 10)
        with self.assertRaisesRegex(CloudAuditError, "No existe el snapshot"):
            woocommerce_publish.preview_price_proposal_group_restore(
                Session([row]), proposal_ids=["p"], settings=settings(), client=Woo({})
            )

    def test_restore_preview_shows_previous_current_and_restore_price(self):
        row = proposal("p", "product", 10)
        resolved_target = target("product", 10)
        woo = Woo({"products/10": [{"price": "110", "regular_price": "110"}]})
        with patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target):
            result = woocommerce_publish.preview_price_proposal_group_restore(
                Session([row], self._snapshot([row], [resolved_target])),
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )
        restored = result["rows"][0]
        self.assertEqual((restored["published_price"], restored["woo_current_price"], restored["restore_price"]), (110.0, 110.0, 100.0))

    def test_restore_preview_blocks_stale_remote_price(self):
        row = proposal("p", "product", 10)
        resolved_target = target("product", 10)
        woo = Woo({"products/10": [{"price": "115"}]})
        with patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=resolved_target):
            result = woocommerce_publish.preview_price_proposal_group_restore(
                Session([row], self._snapshot([row], [resolved_target])),
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )
        self.assertEqual(result["rows"][0]["status"], "DESACTUALIZADO")
        self.assertTrue(result["blocking"])

    def test_restore_preview_blocks_duplicate_destination(self):
        rows = [proposal("v", "variation", 20), proposal("pack", "pack", 20)]
        targets = [target("variation", 20, 7), {**target("pack", 20, 7), "remote_key": "variation:7:20"}]
        woo = Woo({"products/7/variations/20": [{"price": "110"}, {"price": "110"}]})
        with patch.object(woocommerce_publish, "_remote_target_for_proposal", side_effect=targets):
            result = woocommerce_publish.preview_price_proposal_group_restore(
                Session(rows, self._snapshot(rows, targets)),
                proposal_ids=["v", "pack"],
                settings=settings(),
                client=woo,
            )
        self.assertEqual({row["status"] for row in result["rows"]}, {"DESTINO DUPLICADO"})

    def test_restore_confirmation_requires_exact_token(self):
        with self.assertRaises(CloudAuditError):
            woocommerce_publish.restore_price_proposal_group(
                Session([proposal("p", "product", 10)]),
                proposal_ids=["p"],
                confirm="restaurar",
                settings=settings(),
            )

    def test_blocked_restore_produces_zero_remote_writes(self):
        row = proposal("p", "product", 10)
        woo = Woo({})
        with patch.object(woocommerce_publish, "preview_price_proposal_group_restore", return_value={
            "blocking": True,
            "rows": [{"canonical_key": "product:10", "status": "DESACTUALIZADO", "reason": "changed"}],
        }):
            with self.assertRaises(CloudAuditError):
                woocommerce_publish.restore_price_proposal_group(
                    Session([row]), proposal_ids=["p"], confirm="RESTAURAR", settings=settings(), client=woo
                )
        self.assertEqual(woo.writes, [])

    def _execute_restore(self, rows, targets, woo):
        session = Session(rows)
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_restore", return_value=restore_preview(rows, targets)),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "_ensure_audit_persisted"),
            patch.object(woocommerce_publish, "write_audit_event"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}) as sync,
        ):
            result = woocommerce_publish.restore_price_proposal_group(
                session,
                proposal_ids=[row["id"] for row in rows],
                confirm="RESTAURAR",
                settings=settings(),
                client=woo,
            )
        return session, result, sync

    def test_valid_restore_writes_verifies_and_marks_read_only(self):
        row = proposal("p", "product", 10)
        session, result, sync = self._execute_restore(
            [row],
            [target("product", 10)],
            Woo({"products/10": [{"price": "100", "regular_price": "100"}]}),
        )
        self.assertEqual(len(result["restored"]), 1)
        self.assertEqual(session.tables["price_change_proposals"][0]["status"], "rolled_back")
        sync.assert_called_once()

    def test_product_variation_and_pack_restore_to_correct_targets(self):
        rows = [
            proposal("p", "product", 10),
            proposal("v", "variation", 20, parent_id=7),
            proposal("pack", "pack", 30),
        ]
        targets = [target("product", 10), target("variation", 20, 7), target("pack", 30)]
        woo = Woo({
            "products/10": [{"price": "100"}],
            "products/7/variations/20": [{"price": "100"}],
            "products/30": [{"price": "100"}],
        })
        _session, _result, _sync = self._execute_restore(rows, targets, woo)
        self.assertEqual([write[0] for write in woo.writes], ["product", "variation", "product"])

    def test_restore_history_links_original_publish_operation(self):
        row = proposal("p", "product", 10)
        _session, _result, sync = self._execute_restore(
            [row],
            [target("product", 10)],
            Woo({"products/10": [{"price": "100"}]}),
        )
        self.assertEqual(
            sync.call_args.kwargs["metadata"]["source_publish_operation_id"],
            "WOOBATCH-1",
        )

    def test_second_restore_is_idempotently_blocked(self):
        row = proposal("p", "product", 10, status="rolled_back")
        row["source_row"]["rolled_back"] = True
        result = woocommerce_publish.restore_price_proposal_group(
            Session([row]), proposal_ids=["p"], confirm="RESTAURAR", settings=settings()
        )
        self.assertTrue(result["already_restored"])

    def test_partial_restore_failure_compensates_in_reverse_order(self):
        rows = [proposal("a", "product", 10), proposal("b", "product", 11)]
        targets = [target("product", 10), target("product", 11)]
        woo = FailingWoo({
            "products/10": [{"price": "100"}, {"price": "110"}],
            "products/11": [],
        }, fail_on_write=2)
        with self.assertRaisesRegex(CloudAuditError, "compensado"):
            self._execute_restore(rows, targets, woo)
        self.assertEqual(woo.write_count, 3)

    def test_incomplete_compensation_is_critical(self):
        rows = [proposal("a", "product", 10), proposal("b", "product", 11)]
        targets = [target("product", 10), target("product", 11)]
        woo = FailingWoo({"products/10": [{"price": "100"}], "products/11": []}, fail_on_write=2, fail_compensation=True)
        with self.assertRaisesRegex(CloudAuditError, "ERROR CRITICO"):
            self._execute_restore(rows, targets, woo)

    def test_restore_action_is_visible_only_for_published_admin_snapshot(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn('raw_status == "published"', source)
        self.assertIn('lower() == "admin"', source)
        self.assertIn('proposal_source.get("publish_operation_id")', source)

    def test_restore_dialog_requires_exact_restaura_token(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_restore_preview)
        self.assertIn('if confirmation != "RESTAURAR":', source)

    def test_restore_preview_has_required_columns_and_scrollbars(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_restore_preview)
        for label in (
            "Precio antes de publicar",
            "Precio actual Woo",
            "Precio a restaurar",
            "Estado",
            "Motivo",
        ):
            self.assertIn(label, source)
        self.assertIn("yscroll", source)
        self.assertIn("xscroll", source)

    def test_restored_proposal_stays_visible_and_read_only(self):
        detail = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        raw_status = inspect.getsource(FutonHubErpPrototype._proposal_raw_status)
        self.assertIn("rolled_back", detail)
        self.assertIn("rolled_back", raw_status)
        self.assertIn("button.configure(state=tk.DISABLED)", detail)

    def test_no_new_http_client_or_schema_migration(self):
        source = inspect.getsource(woocommerce_publish)
        self.assertNotIn("requests.", source)
        self.assertNotIn("ALTER TABLE", source)


if __name__ == "__main__":
    unittest.main()

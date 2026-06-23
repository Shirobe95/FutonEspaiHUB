from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.audit import CloudAuditError  # noqa: E402
from futonhub.cloud.services import price_proposals, woocommerce_publish  # noqa: E402
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
    old_price: float = 100,
    new_price: float = 110,
    status: str = "pending",
    snapshot: dict | None = None,
    deleted: bool = False,
) -> dict:
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
            "item_snapshot": snapshot or {},
            "ui_deleted": deleted,
        },
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
    def __init__(self, rows):
        self.tables = {"price_change_proposals": rows}
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
    def __init__(self, reads, fail_on_write: int, fail_rollback: bool = False):
        super().__init__(reads)
        self.fail_on_write = fail_on_write
        self.fail_rollback = fail_rollback
        self.write_count = 0

    def update_product_pricing(self, woo_id, payload):
        self.write_count += 1
        if self.write_count == self.fail_on_write:
            raise RuntimeError("write failed")
        if self.fail_rollback and self.write_count > self.fail_on_write:
            raise RuntimeError("rollback failed")
        return super().update_product_pricing(woo_id, payload)


class PriceProposalPublicationGroupTests(unittest.TestCase):
    def test_product_resolves_product_endpoint(self):
        target = woocommerce_publish._remote_target_for_proposal(
            Session([]), proposal("p", "product", 10, snapshot={"type": "simple"})
        )
        self.assertEqual(target["remote_key"], "product:10")
        self.assertEqual(target["endpoint"], "products/10")

    def test_variation_resolves_parent_and_variation_endpoint(self):
        row = proposal("v", "variation", 20, snapshot={"parent_woo_id": 7})
        with patch.object(woocommerce_publish, "_fetch_cloud_item_for_proposal", return_value={"parent_woo_id": 7}):
            target = woocommerce_publish._remote_target_for_proposal(Session([]), row)
        self.assertEqual(target["remote_key"], "variation:7:20")
        self.assertEqual(target["endpoint"], "products/7/variations/20")

    def test_pack_keeps_kind_and_resolves_product_target(self):
        row = proposal("pack", "pack", 30, snapshot={"woo_item_kind": "product"})
        with patch.object(woocommerce_publish, "_fetch_cloud_item_for_proposal", return_value={}):
            target = woocommerce_publish._remote_target_for_proposal(Session([]), row)
        self.assertEqual(target["canonical_key"], "pack:30")
        self.assertEqual(target["remote_key"], "product:30")

    def test_pack_can_resolve_variation_target(self):
        row = proposal("pack", "pack", 30, snapshot={"woo_item_kind": "variation", "woo_parent_id": 8})
        with patch.object(woocommerce_publish, "_fetch_cloud_item_for_proposal", return_value={}):
            target = woocommerce_publish._remote_target_for_proposal(Session([]), row)
        self.assertEqual(target["remote_key"], "variation:8:30")

    def test_pack_without_parent_for_variation_is_blocked(self):
        row = proposal("pack", "pack", 30, snapshot={"woo_item_kind": "variation"})
        with patch.object(woocommerce_publish, "_fetch_cloud_item_for_proposal", return_value={}):
            with self.assertRaises(CloudAuditError):
                woocommerce_publish._remote_target_for_proposal(Session([]), row)

    def _preview(self, rows, targets, woo_prices):
        woo = Woo({
            target["endpoint"]: [
                {"price": str(price), "regular_price": str(price), "sale_price": ""}
            ]
            for target, price in zip(targets, woo_prices)
        })
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", side_effect=targets),
            patch.object(woocommerce_publish, "_price_safety_preview", return_value={"status": "OK", "messages": []}),
        ):
            return woocommerce_publish.preview_price_proposal_group_publish(
                Session(rows), proposal_ids=[row["id"] for row in rows], settings=settings(), client=woo
            )

    def test_stale_price_blocks_entire_preview(self):
        row = proposal("p", "product", 10, old_price=100)
        result = self._preview(row and [row], [{"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}], [105])
        self.assertEqual(result["rows"][0]["status"], "DESACTUALIZADA")
        self.assertTrue(result["blocking"])

    def test_duplicate_remote_target_blocks_distinct_canonical_lines(self):
        rows = [proposal("v", "variation", 3662), proposal("pack", "pack", 3662)]
        targets = [
            {"remote_key": "variation:9:3662", "endpoint": "a", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "variation:3662"},
            {"remote_key": "variation:9:3662", "endpoint": "a", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "pack:3662"},
        ]
        woo = Woo({"a": [{"price": "100"}, {"price": "100"}]})
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", side_effect=targets),
            patch.object(woocommerce_publish, "_price_safety_preview", return_value={"status": "OK", "messages": []}),
        ):
            result = woocommerce_publish.preview_price_proposal_group_publish(
                Session(rows), proposal_ids=["v", "pack"], settings=settings(), client=woo
            )
        self.assertEqual([row["status"] for row in result["rows"]], ["DESTINO DUPLICADO", "DESTINO DUPLICADO"])

    def test_variation_and_pack_remain_distinct_when_targets_differ(self):
        rows = [proposal("v", "variation", 3662), proposal("pack", "pack", 3662)]
        targets = [
            {"remote_key": "variation:9:3662", "endpoint": "v", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "variation:3662"},
            {"remote_key": "product:3662", "endpoint": "p", "cloud_item": {}, "woo_id": 3662, "remote_kind": "product", "canonical_key": "pack:3662"},
        ]
        result = self._preview(rows, targets, [100, 100])
        self.assertEqual([row["status"] for row in result["rows"]], ["VÁLIDO", "VÁLIDO"])

    def test_zero_new_price_blocks(self):
        row = proposal("p", "product", 10, new_price=0)
        result = self._preview([row], [{"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}], [100])
        self.assertEqual(result["rows"][0]["status"], "ERROR")

    def test_deleted_row_blocks(self):
        row = proposal("p", "product", 10, deleted=True)
        result = self._preview([row], [{"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}], [100])
        self.assertEqual(result["rows"][0]["status"], "ERROR")

    def test_rejected_row_blocks(self):
        row = proposal("p", "product", 10, status="rejected")
        result = self._preview([row], [{"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}], [100])
        self.assertEqual(result["rows"][0]["status"], "ERROR")

    def test_parent_variable_error_becomes_not_publishable(self):
        row = proposal("p", "product", 10)
        target = {"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {"type": "variable", "price": 100}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}
        woo = Woo({"products/10": [{"price": "100"}]})
        with patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=target):
            result = woocommerce_publish.preview_price_proposal_group_publish(
                Session([row]), proposal_ids=["p"], settings=settings(), client=woo
            )
        self.assertEqual(result["rows"][0]["status"], "NO PUBLICABLE")

    def test_confirmation_requires_exact_publicar(self):
        with self.assertRaises(CloudAuditError):
            woocommerce_publish.publish_price_proposal_group(
                Session([proposal("p", "product", 10)]), proposal_ids=["p"], confirm="publicar", settings=settings()
            )

    def test_already_published_is_idempotent(self):
        result = woocommerce_publish.publish_price_proposal_group(
            Session([proposal("p", "product", 10, status="published")]),
            proposal_ids=["p"],
            confirm="PUBLICAR",
            settings=settings(),
        )
        self.assertTrue(result["already_published"])

    def test_blocked_preflight_writes_nothing(self):
        session = Session([proposal("p", "product", 10)])
        with patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={
            "blocking": True,
            "rows": [{"canonical_key": "product:10", "status": "ERROR", "reason": "bad"}],
        }):
            with self.assertRaises(CloudAuditError):
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["p"], confirm="PUBLICAR", settings=settings()
                )
        self.assertEqual(session.updates, [])

    def test_rejection_requires_reason(self):
        with self.assertRaises(CloudAuditError):
            price_proposals.reject_real_price_proposal_group(
                Session([proposal("p", "product", 10)]), ["p"], "", settings()
            )

    def test_rejection_does_not_reference_woocommerce(self):
        source = inspect.getsource(price_proposals.reject_real_price_proposal_group)
        self.assertNotIn("WooCommerceClient", source)
        self.assertNotIn("publish", source.lower().replace("woo_publish", ""))

    def test_rejection_marks_all_members_and_never_calls_woo(self):
        session = Session([
            proposal("a", "product", 10),
            proposal("b", "variation", 20),
        ])
        with (
            patch.object(price_proposals, "write_snapshot"),
            patch.object(price_proposals, "write_audit_event"),
        ):
            result = price_proposals.reject_real_price_proposal_group(
                session,
                ["a", "b"],
                "No aplicar esta subida",
                settings(),
            )
        self.assertEqual(result["rejected_count"], 2)
        self.assertTrue(all(row["status"] == "rejected" for row in session.tables["price_change_proposals"]))
        self.assertTrue(all(
            row["source_row"]["rejection_reason"] == "No aplicar esta subida"
            for row in session.tables["price_change_proposals"]
        ))

    def test_rejected_proposal_becomes_read_only_in_detail(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn('can_review = self._proposal_raw_status(proposal) == "pending"', source)
        self.assertIn("button.configure(state=tk.DISABLED)", source)

    def test_accept_uses_group_preview_not_single_publish(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_publish_preview)
        self.assertIn("preview_price_proposal_group_publish", source)
        self.assertNotIn("publish_woocommerce_price(", source)

    def test_publish_dialog_requires_exact_publicar(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertIn('if confirmation != "PUBLICAR":', source)

    def test_preview_has_required_states_and_columns(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        for label in ("Precio registrado", "Precio Woo", "Precio nuevo", "Estado", "Motivo"):
            self.assertIn(label, source)

    def test_publish_overlay_reports_progress(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertIn("Publicando precios en WooCommerce...", source)
        self.assertIn("{index}/{total}", source)

    def test_published_detail_shows_date_user_and_operation(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn("published_at", source)
        self.assertIn("published_by_email", source)
        self.assertIn("publish_operation_id", source)

    def test_service_uses_existing_pricing_contract(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("_pricing_payload_for_effective_price", source)
        self.assertIn("sync_woocommerce_price_inventory_state", source)

    def test_service_acquires_and_releases_lock(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("acquire_system_lock", source)
        self.assertIn("release_system_lock", source)
        self.assertIn("finally:", source)

    def test_service_snapshots_before_remote_write(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertLess(source.index("_ensure_snapshot_persisted"), source.index("_write_remote_target"))

    def test_service_rolls_back_in_reverse_order(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("for row in reversed(published):", source)
        self.assertIn("admin_publish_price_proposal_group_rollback", source)

    def test_valid_product_batch_publishes_verifies_and_marks_published(self):
        row = proposal("p", "product", 10)
        target = {"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"}
        preflight = {"blocking": False, "rows": [{
            "proposal_id": "p", "canonical_key": "product:10", "target": target,
            "woo_before": {"regular_price": "100", "sale_price": ""},
            "woo_before_full": {"regular_price": "100", "sale_price": ""},
            "woo_current_price": 100.0, "new_price": 110.0,
            "old_price_proposal": 100.0, "proposal": row,
        }]}
        session = Session([row])
        woo = Woo({"products/10": [{"price": "110", "regular_price": "110", "sale_price": ""}]})
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value=preflight),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "_ensure_audit_persisted"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session, proposal_ids=["p"], confirm="PUBLICAR", settings=settings(), client=woo
            )
        self.assertEqual(len(result["published"]), 1)
        self.assertEqual(session.tables["price_change_proposals"][0]["status"], "published")
        self.assertEqual(woo.writes[0][0], "product")

    def test_mixed_product_and_variation_publish_to_correct_endpoints(self):
        product_row = proposal("p", "product", 10)
        variation_row = proposal("v", "variation", 20, snapshot={"parent_woo_id": 7})
        targets = [
            {"remote_key": "product:10", "endpoint": "products/10", "cloud_item": {}, "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10"},
            {"remote_key": "variation:7:20", "endpoint": "products/7/variations/20", "cloud_item": {"parent_woo_id": 7}, "woo_id": 20, "parent_woo_id": 7, "remote_kind": "variation", "canonical_key": "variation:20"},
        ]
        preflight_rows = []
        for row, target in zip((product_row, variation_row), targets):
            preflight_rows.append({
                "proposal_id": row["id"], "canonical_key": target["canonical_key"], "target": target,
                "woo_before": {"regular_price": "100", "sale_price": ""},
                "woo_before_full": {"regular_price": "100", "sale_price": ""},
                "woo_current_price": 100.0, "new_price": 110.0,
                "old_price_proposal": 100.0, "proposal": row,
            })
        woo = Woo({
            "products/10": [{"price": "110"}],
            "products/7/variations/20": [{"price": "110"}],
        })
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={"blocking": False, "rows": preflight_rows}),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "_ensure_audit_persisted"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            woocommerce_publish.publish_price_proposal_group(
                Session([product_row, variation_row]), proposal_ids=["p", "v"], confirm="PUBLICAR", settings=settings(), client=woo
            )
        self.assertEqual([write[0] for write in woo.writes], ["product", "variation"])

    def test_partial_failure_rolls_back_written_lines(self):
        rows = [proposal("a", "product", 10), proposal("b", "product", 11)]
        targets = [
            {"remote_key": f"product:{woo_id}", "endpoint": f"products/{woo_id}", "cloud_item": {}, "woo_id": woo_id, "remote_kind": "product", "canonical_key": f"product:{woo_id}"}
            for woo_id in (10, 11)
        ]
        preflight_rows = [{
            "proposal_id": row["id"], "canonical_key": target["canonical_key"], "target": target,
            "woo_before": {"regular_price": "100", "sale_price": ""},
            "woo_before_full": {"regular_price": "100", "sale_price": ""},
            "woo_current_price": 100.0, "new_price": 110.0,
            "old_price_proposal": 100.0, "proposal": row,
        } for row, target in zip(rows, targets)]
        woo = FailingWoo({
            "products/10": [{"price": "110"}, {"price": "100"}],
            "products/11": [],
        }, fail_on_write=2)
        session = Session(rows)
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={"blocking": False, "rows": preflight_rows}),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "write_audit_event"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            with self.assertRaisesRegex(CloudAuditError, "revertido"):
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["a", "b"], confirm="PUBLICAR", settings=settings(), client=woo
                )
        self.assertTrue(all(row["status"] == "pending" for row in session.tables["price_change_proposals"]))
        self.assertEqual(woo.write_count, 3)

    def test_incomplete_rollback_marks_critical_error(self):
        rows = [proposal("a", "product", 10), proposal("b", "product", 11)]
        targets = [
            {"remote_key": f"product:{woo_id}", "endpoint": f"products/{woo_id}", "cloud_item": {}, "woo_id": woo_id, "remote_kind": "product", "canonical_key": f"product:{woo_id}"}
            for woo_id in (10, 11)
        ]
        preflight_rows = [{
            "proposal_id": row["id"], "canonical_key": target["canonical_key"], "target": target,
            "woo_before": {"regular_price": "100", "sale_price": ""},
            "woo_before_full": {"regular_price": "100", "sale_price": ""},
            "woo_current_price": 100.0, "new_price": 110.0,
            "old_price_proposal": 100.0, "proposal": row,
        } for row, target in zip(rows, targets)]
        woo = FailingWoo({"products/10": [{"price": "110"}], "products/11": []}, fail_on_write=2, fail_rollback=True)
        session = Session(rows)
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={"blocking": False, "rows": preflight_rows}),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "write_audit_event"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            with self.assertRaisesRegex(CloudAuditError, "ERROR CRÍTICO"):
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["a", "b"], confirm="PUBLICAR", settings=settings(), client=woo
                )
        self.assertTrue(all(row["status"] == "error" for row in session.tables["price_change_proposals"]))

    def test_incomplete_rollback_uses_error_status(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn('final_status = "pending" if not rollback_failures else "error"', source)
        self.assertIn("ERROR CRÍTICO", source)

    def test_no_migration_or_new_client_implementation(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("WooCommerceClient", inspect.getsource(woocommerce_publish))
        self.assertNotIn("requests.", source)
        self.assertNotIn("ALTER TABLE", source)


if __name__ == "__main__":
    unittest.main()

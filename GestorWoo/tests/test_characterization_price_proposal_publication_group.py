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
from futonhub.services.combination_proposal_integration import derived_source_row  # noqa: E402
from futonhub.services.price_combination_live_reconciliation import reconcile_live_combination_plan  # noqa: E402
from futonhub.ui.erp import prototype as erp_prototype_module  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import PriceProposal  # noqa: E402


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


def price_text(value) -> str:
    if value == "":
        return ""
    return "" if value is None else f"{float(value):.2f}"


def woo_row(
    woo_id: int,
    price: float,
    *,
    parent_id: int | None = None,
    sku: str | None = None,
    modified: str = "T1",
    regular_price: float | None = None,
    sale_price: float | str | None = None,
) -> dict:
    regular = price if regular_price is None else regular_price
    row = {
        "id": int(woo_id),
        "sku": sku or str(woo_id),
        "price": f"{price:.2f}",
        "regular_price": price_text(regular),
        "sale_price": price_text(sale_price),
        "on_sale": bool(price_text(sale_price)),
        "date_on_sale_from": None,
        "date_on_sale_to": None,
        "date_modified": modified,
        "date_modified_gmt": f"{modified}Z",
        "status": "publish",
    }
    if parent_id is not None:
        row["parent_id"] = int(parent_id)
    return row


def derived_context(
    woo_id: int,
    price: float,
    *,
    parent_id: int | None = None,
    modified: str | None = "T1",
    regular_price: float | None = None,
    sale_price: float | str | None = None,
) -> dict:
    regular = price if regular_price is None else regular_price
    context = {
        "id": int(woo_id),
        "parent_id": int(parent_id) if parent_id is not None else None,
        "price": f"{price:.2f}",
        "regular_price": price_text(regular),
        "sale_price": price_text(sale_price),
        "on_sale": bool(price_text(sale_price)),
        "date_on_sale_from": None,
        "date_on_sale_to": None,
    }
    if modified is not None:
        context["date_modified"] = modified
        context["date_modified_gmt"] = f"{modified}Z"
    return context


def derived_proposal(
    row_id: str,
    kind: str,
    woo_id: int,
    *,
    old_price: float,
    new_price: float,
    parent_id: int | None = None,
    stored_context: dict | None = None,
    stored_payload: dict | None = None,
    stored_strategy: str | None = None,
) -> dict:
    snapshot = {
        "woo_id": int(woo_id),
        "woo_item_kind": kind,
        "price": old_price,
        "regular_price": f"{old_price:.2f}",
        "sale_price": "",
    }
    if parent_id is not None:
        snapshot["woo_parent_id"] = int(parent_id)
        snapshot["parent_woo_id"] = int(parent_id)
    row = proposal(row_id, kind, woo_id, old_price=old_price, new_price=new_price, snapshot=snapshot)
    source = row["source_row"]
    source.update({
        "entry_origin": "DERIVED_COMBINATION",
        "derived_status": "READY",
        "publication_allowed": "YES",
        "blocking_reason": "",
        "component_delta": f"{new_price - old_price:.2f}",
        "woo_price_context_at_creation": dict(
            stored_context if stored_context is not None else derived_context(woo_id, old_price, parent_id=parent_id)
        ),
        "future_pricing_payload": (
            dict(stored_payload) if stored_payload is not None else {"regular_price": f"{new_price:.2f}", "sale_price": ""}
        ),
        "pricing_strategy": stored_strategy if stored_strategy is not None else "regular_price",
    })
    return row


def proposal_from_derived_line(row_id: str, line: dict, *, source_ids: tuple[str, ...] = ("direct",)) -> dict:
    row = proposal(
        row_id,
        "variation",
        int(line["combination_woo_id"]),
        old_price=float(line["effective_current_price"]),
        new_price=float(line["simulated_effective_price"]),
        snapshot={
            "woo_id": int(line["combination_woo_id"]),
            "woo_item_kind": "variation",
            "woo_parent_id": int(line["combination_parent_woo_id"]),
            "parent_woo_id": int(line["combination_parent_woo_id"]),
            "price": float(line["effective_current_price"]),
        },
    )
    row["source_row"].update(
        derived_source_row(
            line,
            proposal_name="Test",
            save_token="token",
            source_proposal_ids=source_ids,
        )
    )
    return row


def combination_row(
    woo_id: int,
    *,
    parent_id: int = 20,
    sku: str | None = None,
    name: str | None = None,
    delta: str = "4.00",
) -> dict:
    return {
        "combination_woo_id": int(woo_id),
        "combination_parent_woo_id": int(parent_id),
        "combination_sku": sku or f"COMBO-{woo_id}",
        "combination_name": name or f"Combinacion {woo_id}",
        "component_delta": delta,
        "proposal_trace_keys": ["direct-key"],
        "modified_components": [{"component_item_id": "1", "component_sku": "A", "quantity": "2"}],
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
        self.mode = "select"

    def select(self, *_args, **_kwargs):
        self.mode = "select"
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

    def insert(self, payload):
        self.payload = dict(payload)
        self.mode = "insert"
        return self

    def update(self, payload):
        self.payload = payload
        self.mode = "update"
        return self

    def execute(self):
        rows = self.session.tables.setdefault(self.table_name, [])
        if self.mode == "select" and self.session.hide_blackbox_direct_reads and self.table_name in {"operation_snapshots", "audit_logs"}:
            return Response([])
        selected = list(rows)
        if self.ids is not None:
            selected = [row for row in selected if str(row.get("id")) in self.ids]
        for column, value in self.equals:
            selected = [row for row in selected if row.get(column) == value]
        if self.mode == "insert":
            row = dict(self.payload or {})
            row.setdefault("id", f"{self.table_name}-{len(rows) + 1}")
            rows.append(row)
            self.session.updates.append((self.table_name, dict(row), []))
            return Response([dict(row)])
        if self.mode == "update" and self.payload is not None:
            for row in selected:
                row.update(self.payload)
            self.session.updates.append((self.table_name, dict(self.payload), list(self.equals)))
        return Response([dict(row) for row in selected])


class RpcQuery:
    def __init__(self, session, name, args):
        self.session = session
        self.name = name
        self.args = dict(args or {})

    def execute(self):
        self.session.rpc_calls.append((self.name, dict(self.args)))
        if self.name == "futonhub_write_operation_snapshot":
            row = {
                "id": f"snapshot-{len(self.session.tables['operation_snapshots']) + 1}",
                "operation_id": self.args.get("p_operation_id"),
                "user_id": self.args.get("p_user_id"),
                "module": self.args.get("p_module"),
                "action": self.args.get("p_action"),
                "entity_type": self.args.get("p_entity_type"),
                "entity_id": self.args.get("p_entity_id"),
                "before_data": self.args.get("p_before_data"),
                "reason": self.args.get("p_reason"),
            }
            self.session.tables["operation_snapshots"].append(row)
            return Response([dict(row)])
        if self.name == "futonhub_write_audit_log":
            row = {
                "id": f"audit-{len(self.session.tables['audit_logs']) + 1}",
                "operation_id": self.args.get("p_operation_id"),
                "user_id": self.args.get("p_user_id"),
                "user_email": self.args.get("p_user_email"),
                "module": self.args.get("p_module"),
                "action": self.args.get("p_action"),
                "status": self.args.get("p_status"),
                "severity": self.args.get("p_severity"),
                "entity_type": self.args.get("p_entity_type"),
                "entity_id": self.args.get("p_entity_id"),
                "before_data": self.args.get("p_before_data"),
                "after_data": self.args.get("p_after_data"),
            }
            self.session.tables["audit_logs"].append(row)
            return Response([dict(row)])
        if self.name == "futonhub_read_operation_snapshots":
            return Response([dict(row) for row in self.session.tables["operation_snapshots"]])
        if self.name == "futonhub_read_audit_logs":
            return Response([dict(row) for row in self.session.tables["audit_logs"]])
        return Response([])


class Session:
    def __init__(self, rows):
        self.tables = {
            "price_change_proposals": rows,
            "operation_snapshots": [],
            "audit_logs": [],
        }
        self.role = "admin"
        self.user_id = "user"
        self.email = "admin@example.invalid"
        self.updates = []
        self.rpc_calls = []
        self.hide_blackbox_direct_reads = False
        self.client = self

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, args):
        return RpcQuery(self, name, args)


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


class StatefulWoo:
    def __init__(self, rows_by_endpoint):
        self.rows_by_endpoint = {
            endpoint: dict(row)
            for endpoint, row in rows_by_endpoint.items()
        }
        self.writes = []

    def get(self, endpoint):
        return SimpleNamespace(json=lambda: dict(self.rows_by_endpoint[endpoint]))

    def _apply(self, endpoint, payload):
        current = self.rows_by_endpoint.setdefault(endpoint, {})
        current.update(dict(payload))
        sale = woocommerce_publish._safe_money(current.get("sale_price"))
        regular = woocommerce_publish._safe_money(current.get("regular_price"))
        effective = sale if sale is not None and sale > 0 else regular
        if effective is not None:
            current["price"] = f"{effective:.2f}"
        return dict(current)

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        return self._apply(f"products/{int(woo_id)}", payload)

    def update_variation_pricing(self, parent_id, woo_id, payload):
        self.writes.append(("variation", int(parent_id), int(woo_id), dict(payload)))
        return self._apply(f"products/{int(parent_id)}/variations/{int(woo_id)}", payload)


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


class ImpactService:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def impact_for_changes(self, _changes):
        return {
            "included_combinations": [dict(row) for row in self.rows],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "counts": {"included_combinations": len(self.rows)},
        }


class FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.command = kwargs.get("command")
        self.exists = True
        self.options = dict(kwargs)

    def title(self, *_args, **_kwargs):
        return None

    def configure(self, **kwargs):
        self.options.update(kwargs)

    config = configure

    def transient(self, *_args, **_kwargs):
        return None

    def resizable(self, *_args, **_kwargs):
        return None

    def rowconfigure(self, *_args, **_kwargs):
        return None

    def columnconfigure(self, *_args, **_kwargs):
        return None

    def winfo_screenwidth(self):
        return 1200

    def winfo_screenheight(self):
        return 800

    def minsize(self, *_args, **_kwargs):
        return None

    def grab_set(self):
        self.options["grabbed"] = True

    def grab_release(self):
        self.options["grabbed"] = False

    def winfo_exists(self):
        return self.exists

    def destroy(self):
        self.exists = False

    def protocol(self, *_args, **_kwargs):
        return None

    def bind(self, *_args, **_kwargs):
        return None

    def grid(self, *_args, **_kwargs):
        return None

    def pack(self, *_args, **_kwargs):
        return None


class FakeTreeview(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(*_args, **kwargs)
        self.items = []

    def heading(self, *_args, **_kwargs):
        return None

    def column(self, *_args, **_kwargs):
        return None

    def insert(self, parent, index, **kwargs):
        item_id = f"item-{len(self.items) + 1}"
        self.items.append((item_id, parent, index, kwargs))
        return item_id

    def yview(self, *_args, **_kwargs):
        return None

    def xview(self, *_args, **_kwargs):
        return None


class FakeScrollbar(FakeWidget):
    def set(self, *_args, **_kwargs):
        return None


class ImmediateThread:
    def __init__(self, *, target, daemon=None):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class PriceProposalPublicationGroupTests(unittest.TestCase):
    def _publish_with_runtime_blackbox(
        self,
        rows,
        woo,
        proposal_ids,
        *,
        hidden_blackbox_reads: bool = False,
    ):
        session = Session(rows)
        session.hide_blackbox_direct_reads = hidden_blackbox_reads
        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            return session, woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=list(proposal_ids),
                settings=settings(),
                client=woo,
            )

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
            target["endpoint"]: [{
                "id": target["woo_id"],
                "parent_id": target.get("parent_woo_id"),
                "price": str(price),
                "regular_price": str(price),
                "sale_price": "",
            }]
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
            {"remote_key": "variation:9:3662", "endpoint": "products/9/variations/3662", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "variation:3662"},
            {"remote_key": "product:3662", "endpoint": "products/3662", "cloud_item": {}, "woo_id": 3662, "remote_kind": "product", "canonical_key": "pack:3662"},
        ]
        result = self._preview(rows, targets, [100, 100])
        self.assertEqual([row["status"] for row in result["rows"]], ["VALIDO", "VALIDO"])

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

    def test_group_publish_does_not_require_text_confirmation(self):
        session = Session([proposal("p", "product", 10)])
        with patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={
            "blocking": True,
            "rows": [{"canonical_key": "product:10", "status": "ERROR", "reason": "bad"}],
        }):
            with self.assertRaisesRegex(CloudAuditError, "bloqueada"):
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["p"], confirm="cualquier-texto", settings=settings()
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

    def test_anonymous_apply_is_blocked_before_any_woo_write(self):
        session = Session([proposal("p", "product", 10)])
        session.user_id = ""
        woo = Woo({})
        with self.assertRaisesRegex(CloudAuditError, "sesion de usuario identificable"):
            woocommerce_publish.publish_price_proposal_group(
                session, proposal_ids=["p"], settings=settings(), client=woo
            )
        self.assertEqual(woo.writes, [])
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

    def test_applied_proposal_becomes_read_only_in_detail(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn('can_apply = self._proposal_raw_status(proposal) == "pending"', source)
        self.assertIn("for button in top_actions.winfo_children()", source)
        self.assertIn("button.configure(state=tk.DISABLED)", source)

    def test_accept_uses_group_preview_not_single_publish(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_publish_preview)
        self.assertIn("preview_price_proposal_group_publish", source)
        self.assertNotIn("publish_woocommerce_price(", source)

    def test_publish_dialog_has_no_text_confirmation(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertNotIn("PUBLICAR", source)
        self.assertNotIn("confirm_var", source)
        self.assertIn("Aplicar {counts.get", source)

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

    def test_any_identified_user_role_can_apply_and_is_audited(self):
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
        session.role = "catalog_operator"
        session.user_id = "catalog-7"
        session.email = "catalog7@example.invalid"
        woo = Woo({"products/10": [{"price": "110", "regular_price": "110.00", "sale_price": ""}]})
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
        source = session.tables["price_change_proposals"][0]["source_row"]
        self.assertEqual(source["workflow_state"], "APPLIED")
        self.assertEqual(source["applied_by_user_id"], "catalog-7")
        self.assertEqual(source["applied_by_user_name"], "catalog7@example.invalid")
        self.assertEqual(woo.writes[0][0], "product")

    def test_live_divergence_refreshes_draft_and_requires_new_review(self):
        row = proposal("p", "product", 10, old_price=100, new_price=110)
        target = {
            "remote_key": "product:10", "endpoint": "products/10", "cloud_item": {},
            "woo_id": 10, "remote_kind": "product", "canonical_key": "product:10",
        }
        woo = Woo({
            "products/10": [
                {"id": 10, "price": "105", "regular_price": "105", "sale_price": ""},
                {"id": 10, "price": "105", "regular_price": "105", "sale_price": ""},
            ],
        })
        session = Session([row])
        with (
            patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=target),
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired) as caught:
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["p"], settings=settings(), client=woo
                )
        self.assertEqual(woo.writes, [])
        self.assertEqual(session.tables["price_change_proposals"][0]["old_price"], 105.0)
        self.assertEqual(session.tables["price_change_proposals"][0]["source_row"]["workflow_state"], "READY")
        self.assertEqual(len(caught.exception.differences), 1)
        self.assertEqual(len(caught.exception.preview["display_rows"]), 1)

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
            "products/10": [{"price": "110", "regular_price": "110.00", "sale_price": ""}],
            "products/7/variations/20": [{"price": "110", "regular_price": "110.00", "sale_price": ""}],
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
            "products/10": [
                {"price": "110", "regular_price": "110.00", "sale_price": ""},
                {"price": "100", "regular_price": "100", "sale_price": ""},
            ],
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
        woo = FailingWoo({
            "products/10": [{"price": "110", "regular_price": "110.00", "sale_price": ""}],
            "products/11": [],
        }, fail_on_write=2, fail_rollback=True)
        session = Session(rows)
        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={"blocking": False, "rows": preflight_rows}),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "_ensure_snapshot_persisted"),
            patch.object(woocommerce_publish, "write_audit_event"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            with self.assertRaisesRegex(CloudAuditError, "ERROR CRITICO"):
                woocommerce_publish.publish_price_proposal_group(
                    session, proposal_ids=["a", "b"], confirm="PUBLICAR", settings=settings(), client=woo
                )
        self.assertTrue(all(row["status"] == "error" for row in session.tables["price_change_proposals"]))

    def test_remote_put_failure_records_attempted_unconfirmed_diagnostic(self):
        row = proposal(
            "p",
            "product",
            10,
            snapshot={"woo_id": 10, "type": "simple", "price": 100},
        )
        target = {
            "remote_key": "product:10",
            "endpoint": "products/10",
            "cloud_item": {},
            "woo_id": 10,
            "remote_kind": "product",
            "canonical_key": "product:10",
        }
        preflight_row = {
            "proposal_id": "p",
            "entry_origin": "DIRECT_ITEM",
            "canonical_key": "product:10",
            "target": target,
            "woo_before": {"regular_price": "100", "sale_price": ""},
            "woo_before_full": {"regular_price": "100", "sale_price": ""},
            "woo_current_price": 100.0,
            "new_price": 110.0,
            "old_price_proposal": 100.0,
            "proposal": row,
        }
        session = Session([row])
        woo = FailingWoo({"products/10": []}, fail_on_write=1)
        with (
            patch.object(
                woocommerce_publish,
                "preview_price_proposal_group_publish",
                return_value={"blocking": False, "rows": [preflight_row]},
            ),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
        ):
            with self.assertRaisesRegex(CloudAuditError, "put_attempted=True"):
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=["p"],
                    settings=settings(),
                    client=woo,
                )
        source = session.tables["price_change_proposals"][0]["source_row"]
        failed_write = source["publish_failed_write"]
        self.assertTrue(failed_write["put_attempted"])
        self.assertFalse(failed_write["put_confirmed"])
        self.assertIn("endpoint=products/10", failed_write["diagnostic"])

    def test_incomplete_rollback_uses_error_status(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn('final_status = "pending" if not rollback_failures else "error"', source)
        self.assertIn("ERROR CRITICO", source)

    def test_no_migration_or_new_client_implementation(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        self.assertIn("WooCommerceClient", inspect.getsource(woocommerce_publish))
        self.assertNotIn("requests.", source)
        self.assertNotIn("ALTER TABLE", source)

    def test_hotfix_publish_uses_blackbox_read_rpc_when_direct_tables_are_not_visible(self):
        row = proposal(
            "p",
            "product",
            10,
            snapshot={"woo_id": 10, "type": "simple", "price": 100},
        )
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })

        session, result = self._publish_with_runtime_blackbox(
            [row],
            woo,
            ["p"],
            hidden_blackbox_reads=True,
        )

        self.assertEqual(woo.writes, [("product", 10, {"regular_price": "110.00", "sale_price": ""})])
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")
        self.assertTrue(result["line_results"][0]["put_attempted"])
        self.assertTrue(result["line_results"][0]["verify_ok"])
        self.assertTrue(session.tables["operation_snapshots"])
        self.assertTrue(session.tables["audit_logs"])
        self.assertIn(("futonhub_read_operation_snapshots", {"p_user_id": "user", "p_limit": 200}), session.rpc_calls)
        self.assertIn(("futonhub_read_audit_logs", {"p_user_id": "user", "p_limit": 200}), session.rpc_calls)

    def test_already_current_direct_target_is_no_action_without_put(self):
        row = proposal(
            "p",
            "product",
            10,
            old_price=110,
            new_price=110,
            snapshot={"woo_id": 10, "type": "simple", "price": 110},
        )
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "110.00", "regular_price": "110.00", "sale_price": ""},
        })

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        self.assertEqual(woo.writes, [])
        self.assertEqual(result["counts"]["woo_writes"], 0)
        self.assertEqual(result["line_results"][0]["result"], "NO_ACTION_ALREADY_CURRENT")
        self.assertFalse(result["line_results"][0]["put_attempted"])
        self.assertTrue(result["line_results"][0]["verify_ok"])

    def test_three_direct_targets_publish_three_puts(self):
        rows = [
            proposal(str(woo_id), "product", woo_id, snapshot={"woo_id": woo_id, "type": "simple", "price": 100})
            for woo_id in (10, 11, 12)
        ]
        woo = StatefulWoo({
            f"products/{woo_id}": {"id": woo_id, "price": "100.00", "regular_price": "100.00", "sale_price": ""}
            for woo_id in (10, 11, 12)
        })

        _session, result = self._publish_with_runtime_blackbox(rows, woo, ["10", "11", "12"])

        self.assertEqual(len(woo.writes), 3)
        self.assertEqual([write[1] for write in woo.writes], [10, 11, 12])
        self.assertEqual(result["counts"]["woo_writes"], 3)

    def test_variation_target_publishes_parent_variation_endpoint(self):
        row = proposal(
            "v",
            "variation",
            20,
            snapshot={"woo_id": 20, "woo_parent_id": 7, "parent_woo_id": 7, "price": 100},
        )
        woo = StatefulWoo({
            "products/7/variations/20": {"id": 20, "parent_id": 7, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["v"])

        self.assertEqual(woo.writes, [("variation", 7, 20, {"regular_price": "110.00", "sale_price": ""})])
        self.assertEqual(result["line_results"][0]["woo_id"], 20)
        self.assertEqual(result["line_results"][0]["parent_woo_id"], 7)

    def test_legacy_direct_product_live_variation_revalidates_then_publishes_variation(self):
        row = proposal(
            "legacy-direct",
            "product",
            12345,
            old_price=137.90,
            new_price=139.90,
            snapshot={
                "woo_id": 12345,
                "woo_item_kind": "product",
                "sku": "0201010",
                "price": 137.90,
            },
        )
        row["source_row"].update({
            "ui_line_code": "0201010",
            "physical_item_id": "201010",
            "physical_sku": "0201010",
            "woo_sku": "0201010",
        })
        live_variation = woo_row(
            12345,
            137.90,
            parent_id=900,
            sku="0201010",
            modified="T-LIVE",
        )
        woo = StatefulWoo({
            "products/12345": live_variation,
            "products/900/variations/12345": live_variation,
        })
        session = Session([row])

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            session,
            proposal_ids=["legacy-direct"],
            settings=settings(),
            client=woo,
        )
        self.assertTrue(preview["blocking"])
        self.assertTrue(preview["revalidation_possible"])
        self.assertEqual(preview["rows"][0]["status"], "REMOTE_IDENTITY_REVALIDATION_REQUIRED")

        with (
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired) as caught:
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=["legacy-direct"],
                    settings=settings(),
                    client=woo,
                )
        self.assertEqual(woo.writes, [])
        self.assertTrue(caught.exception.differences[0]["remote_identity_revalidated"])
        refreshed = session.tables["price_change_proposals"][0]
        self.assertEqual(refreshed["item_kind"], "variation")
        self.assertEqual(refreshed["source_row"]["ui_canonical_item_kind"], "variation")
        self.assertEqual(refreshed["source_row"]["woo_parent_id"], 900)
        self.assertEqual(refreshed["source_row"]["item_snapshot"]["woo_parent_id"], 900)

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(
                woocommerce_publish,
                "sync_woocommerce_price_inventory_state",
                return_value={"ok": True},
            ),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["legacy-direct"],
                settings=settings(),
                client=woo,
            )

        self.assertEqual(
            woo.writes,
            [("variation", 900, 12345, {"regular_price": "139.90", "sale_price": ""})],
        )
        self.assertEqual(result["line_results"][0]["parent_woo_id"], 900)
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")

    def test_warning_direct_target_is_counted_as_woo_write_and_published(self):
        row = proposal(
            "p",
            "product",
            10,
            snapshot={"woo_id": 10, "type": "simple", "price": 100},
        )
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })
        with patch.object(
            woocommerce_publish,
            "_price_safety_preview",
            return_value={"status": "WARNING", "messages": ["warning"]},
        ):
            session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        self.assertEqual(woo.writes, [("product", 10, {"regular_price": "110.00", "sale_price": ""})])
        self.assertEqual(result["counts"]["woo_writes"], 1)
        self.assertEqual(session.tables["price_change_proposals"][0]["status"], "published")

    def test_unselected_target_is_not_published(self):
        rows = [
            proposal("selected", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100}),
            proposal("unselected", "product", 11, snapshot={"woo_id": 11, "type": "simple", "price": 100}),
        ]
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            "products/11": {"id": 11, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })

        _session, result = self._publish_with_runtime_blackbox(rows, woo, ["selected"])

        self.assertEqual(woo.writes, [("product", 10, {"regular_price": "110.00", "sale_price": ""})])
        self.assertEqual(result["counts"]["woo_writes"], 1)

    def test_derived_live_reconciliation_persists_target_date_modified_context(self):
        row = combination_row(201)
        woo = StatefulWoo({
            "products/20/variations/201": woo_row(201, 500, parent_id=20, sku="COMBO-201", modified="T-DERIVED"),
        })

        result = reconcile_live_combination_plan(
            [{"physical_item_id": "1", "physical_sku": "A", "old_price": "100", "new_price": "102"}],
            impact_service=ImpactService([row]),
            woo_client=woo,
            session=None,
        )

        context = result["derived_lines"][0]["woo_price_context"]
        self.assertEqual(context["date_modified"], "T-DERIVED")
        self.assertEqual(context["date_modified_gmt"], "T-DERIVEDZ")
        self.assertEqual(context["woo_date_modified"], "T-DERIVEDZ")

    def test_derived_reconciliation_creates_sale_price_payload_for_persisted_preview(self):
        woo = StatefulWoo({
            "products/20/variations/201": woo_row(
                201,
                717.30,
                parent_id=20,
                sku="COMBO-201",
                regular_price=900.00,
                sale_price=717.30,
            ),
        })

        result = reconcile_live_combination_plan(
            [{"physical_item_id": "1", "physical_sku": "A", "old_price": "137.90", "new_price": "139.90"}],
            impact_service=ImpactService([combination_row(201)]),
            woo_client=woo,
            session=None,
        )
        line = result["derived_lines"][0]

        self.assertEqual(line["simulated_effective_price"], "721.30")
        self.assertEqual(line["future_pricing_payload"], {"sale_price": "721.30"})
        self.assertEqual(line["pricing_strategy"], "sale_price")
        source = derived_source_row(
            line,
            proposal_name="Human smoke",
            save_token="token",
            source_proposal_ids=["direct"],
        )
        self.assertEqual(source["future_pricing_payload"], {"sale_price": "721.30"})
        self.assertEqual(source["pricing_strategy"], "sale_price")

    def test_derived_reconciliation_creates_regular_price_payload_for_persisted_preview(self):
        woo = StatefulWoo({
            "products/20/variations/201": woo_row(201, 500.00, parent_id=20, sku="COMBO-201"),
        })

        result = reconcile_live_combination_plan(
            [{"physical_item_id": "1", "physical_sku": "A", "old_price": "100.00", "new_price": "104.00"}],
            impact_service=ImpactService([combination_row(201)]),
            woo_client=woo,
            session=None,
        )
        line = result["derived_lines"][0]

        self.assertEqual(line["simulated_effective_price"], "504.00")
        self.assertEqual(line["future_pricing_payload"], {"regular_price": "504.00", "sale_price": ""})
        self.assertEqual(line["pricing_strategy"], "regular_price")

    def test_human_smoke_sale_price_derived_payloads_are_ready_after_persistence(self):
        rows = [
            proposal("direct", "product", 10, old_price=137.90, new_price=139.90, snapshot={"woo_id": 10, "type": "simple", "price": 137.90}),
        ]
        combination_rows = [
            combination_row(201, sku="COMBO-201"),
            combination_row(202, sku="COMBO-202"),
            combination_row(203, parent_id=21, sku="COMBO-203"),
        ]
        woo = StatefulWoo({
            "products/10": woo_row(10, 137.90, modified="T-DIRECT"),
            "products/20/variations/201": woo_row(201, 717.30, parent_id=20, sku="COMBO-201", regular_price=900.00, sale_price=717.30, modified="T-A"),
            "products/20/variations/202": woo_row(202, 729.94, parent_id=20, sku="COMBO-202", regular_price=900.00, sale_price=729.94, modified="T-B"),
            "products/21/variations/203": woo_row(203, 741.46, parent_id=21, sku="COMBO-203", regular_price=900.00, sale_price=741.46, modified="T-C"),
        })
        plan = reconcile_live_combination_plan(
            [{"physical_item_id": "1", "physical_sku": "A", "old_price": "137.90", "new_price": "139.90"}],
            impact_service=ImpactService(combination_rows),
            woo_client=woo,
            session=None,
        )
        for index, line in enumerate(plan["derived_lines"], start=1):
            rows.append(proposal_from_derived_line(f"derived-{index}", line))

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            Session(rows),
            proposal_ids=[row["id"] for row in rows],
            settings=settings(),
            client=woo,
        )

        self.assertEqual(preview["rows"][0]["status"], "VALIDO")
        derived_rows = preview["rows"][1:]
        self.assertEqual([row["status"] for row in derived_rows], ["READY", "READY", "READY"])
        self.assertNotIn("BLOCKED_INVALID_PAYLOAD", {row["functional_status"] for row in preview["rows"]})
        self.assertEqual([row["pricing_strategy"] for row in derived_rows], ["sale_price", "sale_price", "sale_price"])
        for row in derived_rows:
            source = row["proposal"]["source_row"]
            self.assertEqual(row["pricing_payload"], source["future_pricing_payload"])

    def test_legacy_empty_payload_revalidates_without_write_then_publishes_after_review(self):
        rows = [
            proposal("direct", "product", 10, old_price=137.90, new_price=139.90, snapshot={"woo_id": 10, "type": "simple", "price": 137.90}),
            derived_proposal(
                "derived-a",
                "variation",
                201,
                old_price=717.30,
                new_price=721.30,
                parent_id=20,
                stored_context=derived_context(201, 717.30, parent_id=20, regular_price=900.00, sale_price=717.30, modified="T-A"),
                stored_payload={},
                stored_strategy="",
            ),
            derived_proposal(
                "derived-b",
                "variation",
                202,
                old_price=729.94,
                new_price=733.94,
                parent_id=20,
                stored_context=derived_context(202, 729.94, parent_id=20, regular_price=900.00, sale_price=729.94, modified="T-B"),
                stored_payload={},
                stored_strategy="",
            ),
            derived_proposal(
                "derived-c",
                "variation",
                203,
                old_price=741.46,
                new_price=745.46,
                parent_id=21,
                stored_context=derived_context(203, 741.46, parent_id=21, regular_price=900.00, sale_price=741.46, modified="T-C"),
                stored_payload={},
                stored_strategy="",
            ),
        ]
        woo = StatefulWoo({
            "products/10": woo_row(10, 137.90, modified="T-DIRECT"),
            "products/20/variations/201": woo_row(201, 717.30, parent_id=20, regular_price=900.00, sale_price=717.30, modified="T-A"),
            "products/20/variations/202": woo_row(202, 729.94, parent_id=20, regular_price=900.00, sale_price=729.94, modified="T-B"),
            "products/21/variations/203": woo_row(203, 741.46, parent_id=21, regular_price=900.00, sale_price=741.46, modified="T-C"),
        })
        session = Session(rows)

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            session,
            proposal_ids=[row["id"] for row in rows],
            settings=settings(),
            client=woo,
        )
        self.assertEqual(preview["rows"][0]["status"], "VALIDO")
        self.assertEqual([row["status"] for row in preview["rows"][1:]], ["BLOCKED_INVALID_PAYLOAD"] * 3)

        with (
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired):
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=[row["id"] for row in rows],
                    settings=settings(),
                    client=woo,
                )

        self.assertEqual(woo.writes, [])
        refreshed_payloads = {
            row["id"]: row["source_row"]["future_pricing_payload"]
            for row in session.tables["price_change_proposals"]
            if row["id"].startswith("derived-")
        }
        self.assertEqual(refreshed_payloads["derived-a"], {"sale_price": "721.30"})
        self.assertEqual(refreshed_payloads["derived-b"], {"sale_price": "733.94"})
        self.assertEqual(refreshed_payloads["derived-c"], {"sale_price": "745.46"})

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=[row["id"] for row in rows],
                settings=settings(),
                client=woo,
            )

        self.assertEqual(len(woo.writes), 4)
        self.assertEqual(result["counts"]["woo_writes"], 4)
        self.assertEqual(len(result["line_results"]), 4)
        self.assertTrue(all(line["verify_ok"] for line in result["line_results"]))

    def test_missing_derived_context_is_revalidation_required_and_second_apply_publishes(self):
        rows = [
            proposal("direct", "product", 10, old_price=100, new_price=102, snapshot={"woo_id": 10, "type": "simple", "price": 100}),
            derived_proposal("derived-a", "variation", 201, old_price=500, new_price=504, parent_id=20, stored_context=derived_context(201, 500, parent_id=20, modified=None)),
            derived_proposal("derived-b", "variation", 202, old_price=600, new_price=604, parent_id=20, stored_context=derived_context(202, 600, parent_id=20, modified=None)),
            derived_proposal("derived-c", "variation", 203, old_price=700, new_price=704, parent_id=21, stored_context=derived_context(203, 700, parent_id=21, modified=None)),
        ]
        woo = StatefulWoo({
            "products/10": woo_row(10, 100, modified="T-DIRECT"),
            "products/20/variations/201": woo_row(201, 500, parent_id=20, modified="T-A"),
            "products/20/variations/202": woo_row(202, 600, parent_id=20, modified="T-B"),
            "products/21/variations/203": woo_row(203, 700, parent_id=21, modified="T-C"),
        })
        session = Session(rows)

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            session,
            proposal_ids=[row["id"] for row in rows],
            settings=settings(),
            client=woo,
        )
        self.assertEqual(preview["rows"][0]["status"], "VALIDO")
        self.assertEqual([row["status"] for row in preview["rows"][1:]], ["BLOCKED_MISSING_PRICE_CONTEXT"] * 3)
        self.assertTrue(preview["blocking"])
        self.assertTrue(preview["revalidation_possible"])

        with (
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired) as caught:
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=[row["id"] for row in rows],
                    settings=settings(),
                    client=woo,
                )

        self.assertEqual(woo.writes, [])
        self.assertIn("contexto Woo", str(caught.exception))
        self.assertEqual(len(caught.exception.differences), 3)
        refreshed_sources = {
            row["id"]: row["source_row"]["woo_price_context_at_creation"]
            for row in session.tables["price_change_proposals"]
            if row["id"].startswith("derived-")
        }
        self.assertEqual(refreshed_sources["derived-a"]["date_modified"], "T-A")
        self.assertEqual(refreshed_sources["derived-b"]["date_modified_gmt"], "T-BZ")
        self.assertEqual(refreshed_sources["derived-c"]["date_modified"], "T-C")

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=[row["id"] for row in rows],
                settings=settings(),
                client=woo,
            )

        self.assertEqual(len(woo.writes), 4)
        self.assertEqual(result["counts"]["woo_writes"], 4)
        self.assertTrue(all(line["verify_ok"] for line in result["line_results"]))

    def test_stale_derived_context_refreshes_without_write(self):
        row = derived_proposal(
            "derived-stale",
            "variation",
            201,
            old_price=500,
            new_price=504,
            parent_id=20,
            stored_context=derived_context(201, 500, parent_id=20, modified="T1"),
        )
        woo = StatefulWoo({
            "products/20/variations/201": woo_row(201, 500, parent_id=20, modified="T2"),
        })
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired):
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=["derived-stale"],
                    settings=settings(),
                    client=woo,
                )

        self.assertEqual(woo.writes, [])
        context = session.tables["price_change_proposals"][0]["source_row"]["woo_price_context_at_creation"]
        self.assertEqual(context["date_modified"], "T2")
        self.assertEqual(context["date_modified_gmt"], "T2Z")

    def test_derived_simple_product_can_publish_with_complete_context(self):
        row = derived_proposal(
            "derived-product",
            "product",
            10,
            old_price=500,
            new_price=504,
            stored_context=derived_context(10, 500, modified="T1"),
        )
        woo = StatefulWoo({"products/10": woo_row(10, 500, modified="T1")})

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["derived-product"])

        self.assertEqual(woo.writes, [("product", 10, {"regular_price": "504.00", "sale_price": ""})])
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")

    def test_derived_variation_can_publish_with_complete_context(self):
        row = derived_proposal(
            "derived-variation",
            "variation",
            201,
            old_price=500,
            new_price=504,
            parent_id=20,
            stored_context=derived_context(201, 500, parent_id=20, modified="T1"),
        )
        woo = StatefulWoo({"products/20/variations/201": woo_row(201, 500, parent_id=20, modified="T1")})

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["derived-variation"])

        self.assertEqual(woo.writes, [("variation", 20, 201, {"regular_price": "504.00", "sale_price": ""})])
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")

    def test_price_publish_preview_does_not_shadow_price_proposal_parameter(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)

        self.assertNotIn('            proposal = row.get("proposal")', source)
        self.assertIn('row_proposal = row.get("proposal")', source)

    def test_revalidation_rerender_keeps_price_proposal_object(self):
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._cloud_session = Session([])
        app._price_publish_in_progress = True
        app._price_bulk_preview_dimensions = lambda *_args: (800, 600, 400, 300)
        app.after = lambda _ms, callback: callback()
        buttons: list[FakeWidget] = []
        windows: list[FakeWidget] = []

        def fake_button(_parent, text, *, primary=False, command=None):
            button = FakeWidget(text=text, primary=primary, command=command)
            buttons.append(button)
            return button

        app._button = fake_button
        proposal_model = PriceProposal("Smoke propuesta", "01/01/2026", 4, 4, 0, 0, "+1.0%", "Ready", tuple())
        first_preview = {
            "counts": {"total": 4, "valid": 1, "warnings": 0, "errors": 0, "stale": 0, "direct": 1, "derived": 3, "excluded": 0, "woo_writes": 4},
            "rows": [
                {"proposal_id": "direct", "entry_origin": "DIRECT_ITEM", "name": "Direct", "code": "D", "status": "VALIDO", "proposal": {"id": "direct"}},
                {
                    "proposal_id": "derived",
                    "entry_origin": "DERIVED_COMBINATION",
                    "name": "Derived",
                    "code": "A",
                    "status": "BLOCKED_INVALID_PAYLOAD",
                    "proposal": {"id": "derived", "source_row": {"source_component_entry_ids": ["direct"]}},
                },
            ],
            "exclusions": [],
            "blocking": False,
        }
        refreshed_preview = {
            "counts": {"total": 1, "valid": 1, "warnings": 0, "errors": 0, "stale": 0, "direct": 0, "derived": 1, "excluded": 0, "woo_writes": 1},
            "display_rows": [
                {
                    "proposal_id": "derived",
                    "entry_origin": "DERIVED_COMBINATION",
                    "name": "Derived refreshed",
                    "code": "A",
                    "status": "READY",
                    "proposal": {"id": "derived", "source_row": {"source_component_entry_ids": ["direct"]}},
                }
            ],
            "exclusions": [],
            "blocking": False,
            "revalidation_required": True,
        }

        def fake_toplevel(*_args, **_kwargs):
            window = FakeWidget()
            windows.append(window)
            return window

        with (
            patch.object(erp_prototype_module.tk, "Toplevel", side_effect=fake_toplevel),
            patch.object(erp_prototype_module.tk, "Frame", FakeWidget),
            patch.object(erp_prototype_module.tk, "Label", FakeWidget),
            patch.object(erp_prototype_module.ttk, "Treeview", FakeTreeview),
            patch.object(erp_prototype_module.ttk, "Scrollbar", FakeScrollbar),
            patch.object(erp_prototype_module, "center_window"),
            patch.object(erp_prototype_module.threading, "Thread", ImmediateThread),
            patch.object(
                erp_prototype_module,
                "publish_price_proposal_group",
                side_effect=erp_prototype_module.PriceProposalRevalidationRequired(
                    "refresh",
                    preview=refreshed_preview,
                    differences=[],
                ),
            ),
            patch.object(erp_prototype_module.messagebox, "showerror") as showerror,
        ):
            FutonHubErpPrototype._render_price_publish_preview(app, proposal_model, ["direct", "derived"], first_preview)
            publish_buttons = [button for button in buttons if button.options.get("primary")]
            self.assertEqual(len(publish_buttons), 1)
            publish_buttons[0].command()

        self.assertGreaterEqual(len(windows), 2)
        self.assertFalse(showerror.called)
        self.assertTrue(hasattr(proposal_model, "name"))


if __name__ == "__main__":
    unittest.main()

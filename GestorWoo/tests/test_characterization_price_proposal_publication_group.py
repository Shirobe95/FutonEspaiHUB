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


def woo_only_price_source_proposal(
    row_id: str,
    sku: str,
    woo_id: int,
    *,
    old_price: float = 71.0,
    new_price: float = 83.78,
    parent_id: int = 3631,
) -> dict:
    item_id = f"93000000{int(woo_id)}"
    row = proposal(
        row_id,
        "variation",
        woo_id,
        old_price=old_price,
        new_price=new_price,
        snapshot={
            "item_id": item_id,
            "item_record_type": "woo_item",
            "hub_item_code": sku,
            "physical_sku": sku,
            "woo_id": woo_id,
            "woo_parent_id": parent_id,
            "parent_woo_id": parent_id,
            "woo_item_kind": "variation",
            "woo_sku": sku,
            "regular_price": f"{old_price:.2f}",
            "sale_price": "",
            "price": f"{old_price:.2f}",
        },
    )
    row["source_row"].update({
        "entry_origin": "DIRECT_ITEM",
        "ui_line_code": sku,
        "ui_line_name": f"Funda {sku}",
        "physical_item_id": item_id,
        "physical_sku": sku,
        "item_record_type": "woo_item",
        "price_source_woo_only": "YES",
        "price_source_mode": "PRICE_SOURCE_WOO_ONLY",
        "publish_target_field": "sale_price",
        "woo_id": woo_id,
        "woo_parent_id": parent_id,
        "parent_woo_id": parent_id,
        "woo_item_kind": "variation",
        "woo_sku": sku,
    })
    return row


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


def placeholder_derived_proposal(
    row_id: str = "placeholder-101",
    *,
    woo_id: int = 4587,
    parent_id: int = 3658,
    old_price: float = 100,
    new_price: float = 101,
    resolved: bool = False,
) -> dict:
    row = derived_proposal(
        row_id,
        "variation",
        woo_id,
        old_price=old_price,
        new_price=new_price,
        parent_id=parent_id,
    )
    source = row["source_row"]
    source.update({
        "publication_allowed": "YES" if resolved else "NO",
        "quarantine_reason": "PENDING_BUSINESS_REVIEW_PLACEHOLDER_011",
        "blocking_reason": "Pending Business Review Placeholder 101",
        "placeholder_relation_id": "101",
        "combination_sku": "0201001|0201001|1249001|1249001|0615011|0615011",
        "component_skus_all": "0201001|0201001|1249001|1249001|0615011|0615011",
        "modified_components": [
            {"component_item_id": "201001", "component_sku": "0201001", "quantity": "2"},
            {"component_item_id": "1249001", "component_sku": "1249001", "quantity": "2"},
        ],
        "relation_edges": [
            {
                "edge_status": "PENDING_BUSINESS_REVIEW_PLACEHOLDER_011",
                "resolution_status": "PLACEHOLDER_UNRESOLVED" if not resolved else "RESOLVED_EXACT_WOO_TARGET",
            }
        ],
    })
    if resolved:
        source["placeholder_relation_resolved"] = "YES"
        source["resolved_remote_key"] = f"variation:{parent_id}:{woo_id}"
        source["resolved_woo_id"] = str(woo_id)
        source["resolved_parent_id"] = str(parent_id)
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
    def __init__(self, rows, *, inventory_rows: list[dict] | None = None):
        self.tables = {
            "price_change_proposals": rows,
            "inventory_items": [dict(row) for row in (inventory_rows or [])],
            "inventory_change_history": [],
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


class LegacyProduct404VariationSkuWoo(StatefulWoo):
    def __init__(self, variation_row: dict):
        parent_id = int(variation_row["parent_id"])
        woo_id = int(variation_row["id"])
        super().__init__({f"products/{parent_id}/variations/{woo_id}": variation_row})
        self.variation_row = dict(variation_row)
        self.read_trace = []

    def get(self, endpoint, params=None):
        self.read_trace.append((endpoint, dict(params or {})))
        if endpoint == f"products/{int(self.variation_row['id'])}":
            raise RuntimeError("woocommerce_rest_invalid_product_id")
        if endpoint == "products" and params:
            sku = str(params.get("sku") or "").strip()
            rows = [dict(self.variation_row)] if sku == str(self.variation_row.get("sku") or "") else []
            return SimpleNamespace(json=lambda: rows)
        return super().get(endpoint)


class ExactSkuSearchWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, search_rows_by_sku):
        super().__init__(rows_by_endpoint)
        self.search_rows_by_sku = {
            str(sku): [dict(row) for row in rows]
            for sku, rows in search_rows_by_sku.items()
        }
        self.read_trace = []

    def get(self, endpoint, params=None):
        self.read_trace.append((endpoint, dict(params or {})))
        if endpoint == "products" and params:
            sku = str(params.get("sku") or "").strip()
            return SimpleNamespace(json=lambda: [dict(row) for row in self.search_rows_by_sku.get(sku, [])])
        return super().get(endpoint)


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


class NonPersistingProductWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, non_persisting_product_id: int):
        super().__init__(rows_by_endpoint)
        self.non_persisting_product_id = int(non_persisting_product_id)

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        if int(woo_id) == self.non_persisting_product_id:
            return {"id": int(woo_id), **dict(payload)}
        return self._apply(f"products/{int(woo_id)}", payload)


class NonPersistingVariationWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, non_persisting_variation_id: int):
        super().__init__(rows_by_endpoint)
        self.non_persisting_variation_id = int(non_persisting_variation_id)

    def update_variation_pricing(self, parent_id, woo_id, payload):
        self.writes.append(("variation", int(parent_id), int(woo_id), dict(payload)))
        if int(woo_id) == self.non_persisting_variation_id:
            return {"id": int(woo_id), **dict(payload)}
        return self._apply(f"products/{int(parent_id)}/variations/{int(woo_id)}", payload)


class EventuallyConsistentProductWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, delayed_product_id: int, stale_gets_after_first_write: int):
        super().__init__(rows_by_endpoint)
        self.delayed_product_id = int(delayed_product_id)
        self.stale_gets_after_first_write = int(stale_gets_after_first_write)
        self._stale_gets_remaining = 0
        self._stale_rows: dict[str, dict] = {}
        self._delay_started = False

    def get(self, endpoint):
        if endpoint == f"products/{self.delayed_product_id}" and self._stale_gets_remaining > 0:
            self._stale_gets_remaining -= 1
            return SimpleNamespace(json=lambda: dict(self._stale_rows[endpoint]))
        return super().get(endpoint)

    def update_product_pricing(self, woo_id, payload):
        endpoint = f"products/{int(woo_id)}"
        self.writes.append(("product", int(woo_id), dict(payload)))
        if int(woo_id) == self.delayed_product_id and not self._delay_started:
            self._stale_rows[endpoint] = dict(self.rows_by_endpoint[endpoint])
            self._stale_gets_remaining = self.stale_gets_after_first_write
            self._delay_started = True
        return self._apply(endpoint, payload)


class RollbackVerificationFailWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, fail_on_publish_product_id: int, rollback_verify_product_id: int):
        super().__init__(rows_by_endpoint)
        self.fail_on_publish_product_id = int(fail_on_publish_product_id)
        self.rollback_verify_product_id = int(rollback_verify_product_id)
        self._rollback_phase = False

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        if int(woo_id) == self.fail_on_publish_product_id and not self._rollback_phase:
            self._rollback_phase = True
            raise RuntimeError("write failed")
        return self._apply(f"products/{int(woo_id)}", payload)

    def get(self, endpoint):
        if self._rollback_phase and endpoint == f"products/{self.rollback_verify_product_id}":
            row = dict(self.rows_by_endpoint[endpoint])
            row.update({"price": "999.00", "regular_price": "999.00", "sale_price": ""})
            return SimpleNamespace(json=lambda: row)
        return super().get(endpoint)


class ResponseLostProductWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, lost_product_ids: set[int]):
        super().__init__(rows_by_endpoint)
        self.lost_product_ids = {int(value) for value in lost_product_ids}
        self._lost_once: set[int] = set()

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        endpoint = f"products/{int(woo_id)}"
        result = self._apply(endpoint, payload)
        if int(woo_id) in self.lost_product_ids and int(woo_id) not in self._lost_once:
            self._lost_once.add(int(woo_id))
            raise TimeoutError("response lost after remote write")
        return result


class ResponseLostAndNonPersistingProductWoo(ResponseLostProductWoo):
    def __init__(self, rows_by_endpoint, *, lost_product_ids: set[int], non_persisting_product_ids: set[int]):
        super().__init__(rows_by_endpoint, lost_product_ids=lost_product_ids)
        self.non_persisting_product_ids = {int(value) for value in non_persisting_product_ids}

    def update_product_pricing(self, woo_id, payload):
        if int(woo_id) in self.non_persisting_product_ids:
            self.writes.append(("product", int(woo_id), dict(payload)))
            return {"id": int(woo_id), **dict(payload)}
        return super().update_product_pricing(woo_id, payload)


class EventuallyConfirmedLostResponseWoo(StatefulWoo):
    def __init__(
        self,
        rows_by_endpoint,
        *,
        lost_product_ids: set[int],
        non_persisting_product_ids: set[int] | None = None,
    ):
        super().__init__(rows_by_endpoint)
        self.lost_product_ids = {int(value) for value in lost_product_ids}
        self.non_persisting_product_ids = {int(value) for value in (non_persisting_product_ids or set())}
        self._lost_once: set[int] = set()
        self._stale_reads: dict[str, dict] = {}

    def get(self, endpoint):
        if endpoint in self._stale_reads:
            stale = self._stale_reads.pop(endpoint)
            return SimpleNamespace(json=lambda: dict(stale))
        return super().get(endpoint)

    def update_product_pricing(self, woo_id, payload):
        woo_id = int(woo_id)
        self.writes.append(("product", woo_id, dict(payload)))
        if woo_id in self.non_persisting_product_ids:
            return {"id": woo_id, **dict(payload)}
        endpoint = f"products/{woo_id}"
        before = dict(self.rows_by_endpoint[endpoint])
        result = self._apply(endpoint, payload)
        if woo_id in self.lost_product_ids and woo_id not in self._lost_once:
            self._lost_once.add(woo_id)
            self._stale_reads[endpoint] = before
            raise TimeoutError("response lost before stale GET catches up")
        return result


class NoApplyThenRetryProductWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, no_apply_once_product_id: int):
        super().__init__(rows_by_endpoint)
        self.no_apply_once_product_id = int(no_apply_once_product_id)
        self._failed_once = False

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        if int(woo_id) == self.no_apply_once_product_id and not self._failed_once:
            self._failed_once = True
            raise TimeoutError("response failed before remote write")
        return self._apply(f"products/{int(woo_id)}", payload)


class UnknownAfterPutExceptionWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, unknown_product_id: int, unknown_price: float):
        super().__init__(rows_by_endpoint)
        self.unknown_product_id = int(unknown_product_id)
        self.unknown_price = float(unknown_price)
        self._failed_once = False

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        endpoint = f"products/{int(woo_id)}"
        if int(woo_id) == self.unknown_product_id and not self._failed_once:
            self._failed_once = True
            self._apply(endpoint, {"regular_price": f"{self.unknown_price:.2f}", "sale_price": ""})
            raise TimeoutError("response failed with unknown remote state")
        return self._apply(endpoint, payload)


class GetFailAfterPutExceptionWoo(StatefulWoo):
    def __init__(self, rows_by_endpoint, *, lost_product_id: int):
        super().__init__(rows_by_endpoint)
        self.lost_product_id = int(lost_product_id)
        self._failed_write = False
        self._failed_get = False

    def update_product_pricing(self, woo_id, payload):
        self.writes.append(("product", int(woo_id), dict(payload)))
        endpoint = f"products/{int(woo_id)}"
        result = self._apply(endpoint, payload)
        if int(woo_id) == self.lost_product_id and not self._failed_write:
            self._failed_write = True
            raise TimeoutError("response lost after remote write")
        return result

    def get(self, endpoint):
        if endpoint == f"products/{self.lost_product_id}" and self._failed_write and not self._failed_get:
            self._failed_get = True
            raise TimeoutError("get failed after ambiguous put")
        return super().get(endpoint)


class MixedTargetOutcomeWoo(StatefulWoo):
    def __init__(
        self,
        rows_by_endpoint,
        *,
        restore_product_ids: set[int] | None = None,
        no_remote_change_product_ids: set[int] | None = None,
    ):
        super().__init__(rows_by_endpoint)
        self.restore_product_ids = {int(value) for value in (restore_product_ids or set())}
        self.no_remote_change_product_ids = {int(value) for value in (no_remote_change_product_ids or set())}
        self._restore_failed_once: set[int] = set()

    def update_product_pricing(self, woo_id, payload):
        woo_id = int(woo_id)
        self.writes.append(("product", woo_id, dict(payload)))
        endpoint = f"products/{woo_id}"
        if woo_id in self.no_remote_change_product_ids:
            return {"id": woo_id, **dict(payload)}
        if woo_id in self.restore_product_ids and woo_id not in self._restore_failed_once:
            self._restore_failed_once.add(woo_id)
            self._apply(endpoint, {"regular_price": "105.00", "sale_price": ""})
            raise TimeoutError("remote changed to unexpected price")
        return self._apply(endpoint, payload)


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
            {"remote_key": "variation:9:3662", "endpoint": "products/9/variations/3662", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "variation:3662"},
            {"remote_key": "variation:9:3662", "endpoint": "products/9/variations/3662", "cloud_item": {}, "woo_id": 3662, "parent_woo_id": 9, "remote_kind": "variation", "canonical_key": "pack:3662"},
        ]
        woo = Woo({"products/9/variations/3662": [{"price": "100"}, {"price": "100"}]})
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
        self.assertIn("phase:", source)

    def test_publish_success_message_uses_verified_target_counts(self):
        source = inspect.getsource(FutonHubErpPrototype._render_price_publish_preview)
        self.assertIn("audit_counts", source)
        self.assertIn("verify_ok_count", source)
        self.assertIn("target_count", source)
        self.assertIn("precios actualizados y verificados en WooCommerce", source)
        self.assertIn("final_status", source)
        self.assertIn("showwarning", source)
        self.assertIn("skipped_no_base_price_count", source)
        self.assertIn("skipped_placeholder_relation_count", source)
        self.assertIn("skipped_unresolved_remote_target_count", source)
        self.assertIn("Omitidos por relacion sin identidad Woo", source)
        self.assertIn("Sin identidad Woo resoluble", source)
        self.assertIn("failed_restored_count", source)

    def test_published_detail_shows_date_user_and_operation(self):
        source = inspect.getsource(FutonHubErpPrototype._render_saved_proposal_detail)
        self.assertIn("published_at", source)
        self.assertIn("published_by_email", source)
        self.assertIn("publish_operation_id", source)

    def test_service_uses_existing_pricing_contract(self):
        source = inspect.getsource(woocommerce_publish.publish_price_proposal_group)
        helper_source = inspect.getsource(woocommerce_publish._sync_verified_price_inventory_state)
        self.assertIn("_pricing_payload_for_effective_price", source)
        self.assertIn("_sync_verified_price_inventory_state", source)
        self.assertIn("sync_woocommerce_price_inventory_state", helper_source)

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
        self.assertIn("rollback_source = rollback_candidates or published", source)
        self.assertIn("for row in reversed(rollback_source):", source)
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
        woo = NonPersistingProductWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            "products/11": {"id": 11, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        }, non_persisting_product_id=11)
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
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "100.00")
        self.assertEqual(woo.rows_by_endpoint["products/11"]["price"], "100.00")

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
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )
        source = session.tables["price_change_proposals"][0]["source_row"]
        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "CRITICAL_PARTIAL_STATE")
        self.assertEqual(target["status"], "FAILED_ROLLBACK_INCOMPLETE")
        self.assertTrue(source["target_rollback"])

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

    def test_target_manifest_counts_match_verified_targets_on_success(self):
        rows = [
            proposal("product-10", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100}),
            proposal("variation-20", "variation", 20, snapshot={"woo_id": 20, "woo_parent_id": 7, "parent_woo_id": 7, "price": 100}),
        ]
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            "products/7/variations/20": {"id": 20, "parent_id": 7, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })

        _session, result = self._publish_with_runtime_blackbox(rows, woo, ["product-10", "variation-20"])

        manifest = result["target_manifest"]
        self.assertEqual(manifest["target_count"], 2)
        self.assertEqual([target["endpoint"] for target in manifest["targets"]], ["products/10", "products/7/variations/20"])
        self.assertEqual([target["woo_type"] for target in manifest["targets"]], ["product", "variation"])
        self.assertEqual(result["audit_counts"]["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 2)
        self.assertEqual(result["audit_counts"]["verify_fail_count"], 0)

    def test_derived_combination_without_inventory_row_is_verified_without_fake_association(self):
        row = derived_proposal(
            "derived-20",
            "variation",
            20,
            old_price=100,
            new_price=101,
            parent_id=7,
        )
        woo = StatefulWoo({
            "products/7/variations/20": woo_row(20, 100, parent_id=7, modified="T1"),
        })
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["derived-20"],
                settings=settings(),
                client=woo,
            )

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["audit_counts"]["target_count"], 1)
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 1)
        self.assertEqual(target["inventory_sync_status"], "NOT_APPLICABLE_DERIVED_COMBINATION")
        self.assertEqual(result["published"][0]["inventory_sync"]["inventory_sync_status"], "NOT_APPLICABLE_DERIVED_COMBINATION")
        self.assertEqual(session.tables["inventory_items"], [])
        self.assertEqual(session.tables["inventory_change_history"], [])
        self.assertFalse(any(table == "inventory_items" for table, _payload, _equals in session.updates))

    def test_direct_item_without_inventory_resolution_fails_closed_and_rolls_back(self):
        row = proposal("direct-10", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["direct-10"],
                settings=settings(),
                client=woo,
            )

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(result["audit_counts"]["failed_restored_count"], 1)
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "100.00")
        self.assertEqual(target["inventory_sync_status"], "FAILED_DIRECT_ITEM")
        self.assertEqual(
            target["rollback_inventory_sync_status"],
            "SKIPPED_DIRECT_ITEM_NO_INVENTORY_ROW_AFTER_ROLLBACK",
        )
        self.assertEqual(target["status"], "FAILED_RESTORED")

    def test_fifty_eight_targets_allow_derived_without_physical_inventory_rows(self):
        direct_rows = [
            proposal(
                f"direct-{woo_id}",
                "product",
                woo_id,
                snapshot={"woo_id": woo_id, "type": "simple", "price": 100},
            )
            for woo_id in range(10, 16)
        ]
        derived_rows = [
            derived_proposal(
                f"derived-{woo_id}",
                "variation",
                woo_id,
                old_price=100,
                new_price=101,
                parent_id=900,
            )
            for woo_id in range(2000, 2052)
        ]
        rows = direct_rows + derived_rows
        inventory_rows = [
            {
                "item_id": woo_id + 1000,
                "name": f"Direct {woo_id}",
                "woo_id": woo_id,
                "woo_price": "100.00",
                "source_row": {},
            }
            for woo_id in range(10, 16)
        ]
        woo = StatefulWoo({
            **{
                f"products/{woo_id}": {
                    "id": woo_id,
                    "price": "100.00",
                    "regular_price": "100.00",
                    "sale_price": "",
                }
                for woo_id in range(10, 16)
            },
            **{
                f"products/900/variations/{woo_id}": woo_row(woo_id, 100, parent_id=900, modified="T1")
                for woo_id in range(2000, 2052)
            },
        })
        session = Session(rows, inventory_rows=inventory_rows)

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=[row["id"] for row in rows],
                settings=settings(),
                client=woo,
            )

        statuses = [target["inventory_sync_status"] for target in result["target_manifest"]["targets"]]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["audit_counts"]["target_count"], 58)
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 58)
        self.assertEqual(statuses.count("SYNCED_DIRECT_ITEM"), 6)
        self.assertEqual(statuses.count("NOT_APPLICABLE_DERIVED_COMBINATION"), 52)
        self.assertEqual(len(session.tables["inventory_change_history"]), 6)

    def test_001d_fifty_eight_mixed_results_are_processed_without_reverting_successes(self):
        ids_applied = list(range(1000, 1052))
        ids_already = [1052, 1053]
        id_skipped = 1054
        ids_restored = [1055, 1056]
        id_no_remote = 1057
        all_ids = ids_applied + ids_already + [id_skipped] + ids_restored + [id_no_remote]
        rows = [
            proposal(
                f"target-{woo_id}",
                "product",
                woo_id,
                old_price=110 if woo_id in ids_already else 100,
                new_price=110,
                snapshot={"woo_id": woo_id, "type": "simple", "price": 100},
            )
            for woo_id in all_ids
        ]
        preflight_rows = []
        for row, woo_id in zip(rows, all_ids):
            status = "NO_CHANGE" if woo_id in ids_already else "SKIPPED_NO_BASE_PRICE" if woo_id == id_skipped else "VALIDO"
            current_price = None if woo_id == id_skipped else 110.0 if woo_id in ids_already else 100.0
            snapshot = (
                {"price": "", "regular_price": "", "sale_price": ""}
                if woo_id == id_skipped
                else {"price": f"{current_price:.2f}", "regular_price": f"{current_price:.2f}", "sale_price": ""}
            )
            target = {
                "remote_key": f"product:{woo_id}",
                "endpoint": f"products/{woo_id}",
                "cloud_item": {},
                "woo_id": woo_id,
                "remote_kind": "product",
                "canonical_key": f"product:{woo_id}",
            }
            preflight_rows.append({
                "proposal_id": row["id"],
                "canonical_key": target["canonical_key"],
                "target": target,
                "woo_before": snapshot,
                "woo_before_full": {"id": woo_id, **snapshot},
                "woo_current_price": current_price,
                "new_price": 110.0,
                "old_price_proposal": current_price,
                "status": status,
                "proposal": row,
            })
        woo = MixedTargetOutcomeWoo(
            {
                f"products/{woo_id}": {
                    "id": woo_id,
                    "price": "110.00" if woo_id in ids_already else "100.00",
                    "regular_price": "110.00" if woo_id in ids_already else "100.00",
                    "sale_price": "",
                }
                for woo_id in all_ids
            },
            restore_product_ids=set(ids_restored),
            no_remote_change_product_ids={id_no_remote},
        )
        session = Session(rows)

        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value={"blocking": False, "rows": preflight_rows, "counts": {"direct": 58, "derived": 0}}),
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

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["target_count"], 58)
        self.assertEqual(audit["processed_count"], 58)
        self.assertEqual(audit["applied_verified_count"], 52)
        self.assertEqual(audit["already_matched_count"], 2)
        self.assertEqual(audit["skipped_no_base_price_count"], 1)
        self.assertEqual(audit["failed_restored_count"], 2)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        self.assertEqual(audit["failed_rollback_incomplete_count"], 0)
        self.assertEqual(woo.rows_by_endpoint["products/1000"]["price"], "110.00")
        self.assertEqual(woo.rows_by_endpoint["products/1055"]["price"], "100.00")
        self.assertEqual(woo.rows_by_endpoint["products/1057"]["price"], "100.00")
        self.assertEqual(result["target_manifest"]["targets"][54]["status"], "SKIPPED_NO_BASE_PRICE")

    def test_001d_target_failure_does_not_stop_following_targets(self):
        rows = [
            proposal(f"target-{woo_id}", "product", woo_id, snapshot={"woo_id": woo_id, "type": "simple", "price": 100})
            for woo_id in range(1, 21)
        ]
        woo = MixedTargetOutcomeWoo(
            {
                f"products/{woo_id}": {"id": woo_id, "price": "100.00", "regular_price": "100.00", "sale_price": ""}
                for woo_id in range(1, 21)
            },
            restore_product_ids={2},
        )

        _session, result = self._publish_with_runtime_blackbox(rows, woo, [row["id"] for row in rows])

        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(result["target_manifest"]["targets"][1]["status"], "FAILED_RESTORED")
        self.assertEqual(woo.rows_by_endpoint["products/2"]["price"], "100.00")
        self.assertEqual(woo.rows_by_endpoint["products/3"]["price"], "110.00")
        self.assertEqual(woo.rows_by_endpoint["products/20"]["price"], "110.00")

    def test_001d_direct_inventory_sync_failure_rolls_back_only_that_target(self):
        rows = [
            proposal(f"direct-{woo_id}", "product", woo_id, snapshot={"woo_id": woo_id, "type": "simple", "price": 100})
            for woo_id in (1, 2, 3)
        ]
        woo = StatefulWoo({
            f"products/{woo_id}": {"id": woo_id, "price": "100.00", "regular_price": "100.00", "sale_price": ""}
            for woo_id in (1, 2, 3)
        })
        session = Session(rows)
        sync_results = [{"ok": True}, RuntimeError("inventory sync failed"), {"ok": True}, {"ok": True}]

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", side_effect=sync_results),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=[row["id"] for row in rows],
                settings=settings(),
                client=woo,
            )

        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(result["target_manifest"]["targets"][0]["status"], "APPLIED_VERIFIED")
        self.assertEqual(result["target_manifest"]["targets"][1]["status"], "FAILED_RESTORED")
        self.assertEqual(result["target_manifest"]["targets"][2]["status"], "APPLIED_VERIFIED")
        self.assertEqual(woo.rows_by_endpoint["products/1"]["price"], "110.00")
        self.assertEqual(woo.rows_by_endpoint["products/2"]["price"], "100.00")
        self.assertEqual(woo.rows_by_endpoint["products/3"]["price"], "110.00")

    def test_001d_no_base_price_skips_without_put_and_continues(self):
        rows = [
            proposal("skip", "product", 10, old_price=0, new_price=110, snapshot={"woo_id": 10, "type": "simple", "price": 0}),
            proposal("apply", "product", 11, snapshot={"woo_id": 11, "type": "simple", "price": 100}),
        ]
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "", "regular_price": "", "sale_price": ""},
            "products/11": {"id": 11, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
        })
        _session, result = self._publish_with_runtime_blackbox(rows, woo, ["skip", "apply"])

        self.assertEqual(result["final_status"], "COMPLETED_WITH_SKIPS")
        self.assertEqual(result["audit_counts"]["skipped_no_base_price_count"], 1)
        self.assertEqual(result["audit_counts"]["applied_verified_count"], 1)
        self.assertEqual([write[1] for write in woo.writes], [11])

    def test_001d_purchasable_false_with_effective_price_remains_price_eligible(self):
        row = proposal("p", "product", 10, old_price=150, new_price=160, snapshot={"woo_id": 10, "type": "simple", "price": 150})
        woo = StatefulWoo({
            "products/10": {
                "id": 10,
                "price": "150.00",
                "regular_price": "150.00",
                "sale_price": "",
                "purchasable": False,
            },
        })
        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["target_manifest"]["targets"][0]["status"], "APPLIED_VERIFIED")
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "160.00")

    def test_001d_descatalogado_with_woo_price_does_not_block_by_status_label(self):
        row = proposal("p", "product", 10, old_price=150, new_price=155, snapshot={"woo_id": 10, "type": "simple", "price": 150})
        row["source_row"]["commercial_status"] = "Descatalogado"
        woo = StatefulWoo({
            "products/10": {
                "id": 10,
                "price": "150.00",
                "regular_price": "150.00",
                "sale_price": "",
                "status": "private",
            },
        })
        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["target_manifest"]["targets"][0]["status"], "APPLIED_VERIFIED")
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "155.00")

    def test_derived_woo_failure_rolls_back_batch_without_inventory_association(self):
        rows = [
            derived_proposal("derived-ok", "variation", 20, old_price=100, new_price=101, parent_id=7),
            derived_proposal("derived-fail", "variation", 21, old_price=100, new_price=101, parent_id=7),
        ]
        woo = NonPersistingVariationWoo(
            {
                "products/7/variations/20": woo_row(20, 100, parent_id=7, modified="T1"),
                "products/7/variations/21": woo_row(21, 100, parent_id=7, modified="T1"),
            },
            non_persisting_variation_id=21,
        )
        session = Session(rows)

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["derived-ok", "derived-fail"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["applied_verified_count"], 1)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        self.assertEqual(woo.rows_by_endpoint["products/7/variations/20"]["price"], "101.00")
        self.assertEqual(woo.rows_by_endpoint["products/7/variations/21"]["price"], "100.00")
        self.assertEqual(session.tables["inventory_items"], [])
        self.assertEqual(session.tables["inventory_change_history"], [])

    def test_nineteen_targets_with_one_unverified_never_reports_success_and_rolls_back_all_written(self):
        rows = [
            proposal(
                f"target-{woo_id}",
                "product",
                woo_id,
                snapshot={"woo_id": woo_id, "type": "simple", "price": 100},
            )
            for woo_id in range(101, 120)
        ]
        woo = NonPersistingProductWoo(
            {
                f"products/{woo_id}": {"id": woo_id, "price": "100.00", "regular_price": "100.00", "sale_price": ""}
                for woo_id in range(101, 120)
            },
            non_persisting_product_id=119,
        )
        session = Session(rows)

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

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["target_count"], 19)
        self.assertEqual(audit["verify_ok_count"], 18)
        self.assertEqual(audit["verify_fail_count"], 1)
        self.assertEqual(audit["applied_verified_count"], 18)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        self.assertEqual(audit["processed_count"], 19)
        self.assertNotEqual(audit["verify_ok_count"], audit["target_count"])
        self.assertEqual(woo.rows_by_endpoint["products/101"]["price"], "110.00")
        self.assertEqual(woo.rows_by_endpoint["products/119"]["price"], "100.00")

    def test_postcheck_old_price_retries_failed_target_and_can_recover(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = EventuallyConsistentProductWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            delayed_product_id=10,
            stale_gets_after_first_write=2,
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["audit_counts"]["retry_count"], 1)
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 1)
        self.assertEqual(result["audit_counts"]["verify_fail_count"], 1)
        self.assertEqual(
            [write for write in woo.writes if write[0] == "product"],
            [
                ("product", 10, {"regular_price": "110.00", "sale_price": ""}),
                ("product", 10, {"regular_price": "110.00", "sale_price": ""}),
            ],
        )

    def test_two_already_matched_targets_count_as_satisfied_without_put(self):
        rows = [
            proposal(
                f"already-{woo_id}",
                "product",
                woo_id,
                old_price=110,
                new_price=110,
                snapshot={"woo_id": woo_id, "type": "simple", "price": 110},
            )
            for woo_id in (10, 11)
        ]
        woo = StatefulWoo({
            f"products/{woo_id}": {"id": woo_id, "price": "110.00", "regular_price": "110.00", "sale_price": ""}
            for woo_id in (10, 11)
        })

        _session, result = self._publish_with_runtime_blackbox(rows, woo, ["already-10", "already-11"])

        self.assertEqual(woo.writes, [])
        self.assertEqual(result["audit_counts"]["target_count"], 2)
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 2)
        self.assertEqual(result["audit_counts"]["already_matched_count"], 2)
        self.assertEqual(result["audit_counts"]["changed_count"], 0)
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")

    def test_response_lost_remote_confirmed_finishes_verified(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = ResponseLostProductWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            lost_product_ids={10},
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(target["status"], "APPLIED_VERIFIED")
        self.assertIn("WRITE_RESPONSE_FAILED_REMOTE_CONFIRMED", target["status_history"])
        self.assertTrue(target["remote_write_confirmed_by_get"])
        self.assertFalse(target["put_response_ok"])
        self.assertEqual(result["audit_counts"]["verify_ok_count"], 1)
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "110.00")

    def test_ambiguous_put_eventually_confirmed_without_second_put_stays_written(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = EventuallyConfirmedLostResponseWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            lost_product_ids={10},
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(target["status"], "APPLIED_VERIFIED")
        self.assertIn("WRITE_RESPONSE_FAILED_REMOTE_OLD", target["status_history"])
        self.assertIn("AMBIGUOUS_WRITE_EVENTUALLY_CONFIRMED", target["status_history"])
        self.assertTrue(target["write_performed"])
        self.assertTrue(target["may_have_written"])
        self.assertTrue(target["operation_may_have_written"])
        self.assertTrue(target["remote_write_confirmed_by_get"])
        self.assertFalse(target["repair_write_performed"])
        self.assertEqual(target["write_outcome"], "AMBIGUOUS_WRITE_EVENTUALLY_CONFIRMED")
        self.assertEqual(
            woo.writes,
            [("product", 10, {"regular_price": "110.00", "sale_price": ""})],
        )

    def test_later_failure_rolls_back_eventually_confirmed_ambiguous_target(self):
        rows = [
            proposal("a", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100}),
            proposal("b", "product", 11, snapshot={"woo_id": 11, "type": "simple", "price": 100}),
        ]
        woo = EventuallyConfirmedLostResponseWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
                "products/11": {"id": 11, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            lost_product_ids={10},
            non_persisting_product_ids={11},
        )
        session = Session(rows)

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["a", "b"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        target_a = next(target for target in result["target_manifest"]["targets"] if target["proposal_id"] == "a")
        target_b = next(target for target in result["target_manifest"]["targets"] if target["proposal_id"] == "b")
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertIn("AMBIGUOUS_WRITE_EVENTUALLY_CONFIRMED", target_a["status_history"])
        self.assertEqual(target_a["status"], "APPLIED_VERIFIED")
        self.assertEqual(target_b["status"], "FAILED_NO_REMOTE_CHANGE")
        self.assertEqual(audit["applied_verified_count"], 1)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "110.00")
        writes_for_a = [write for write in woo.writes if write[1] == 10]
        self.assertEqual(len(writes_for_a), 1)
        self.assertEqual(writes_for_a[0], ("product", 10, {"regular_price": "110.00", "sale_price": ""}))

    def test_response_lost_then_later_failure_rolls_back_confirmed_target(self):
        rows = [
            proposal("a", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100}),
            proposal("b", "product", 11, snapshot={"woo_id": 11, "type": "simple", "price": 100}),
        ]
        woo = ResponseLostAndNonPersistingProductWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
                "products/11": {"id": 11, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            lost_product_ids={10},
            non_persisting_product_ids={11},
        )
        session = Session(rows)

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["a", "b"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["applied_verified_count"], 1)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        target_a = next(target for target in result["target_manifest"]["targets"] if target["proposal_id"] == "a")
        self.assertIn("WRITE_RESPONSE_FAILED_REMOTE_CONFIRMED", target_a["status_history"])
        self.assertNotIn("ROLLBACK_OK", target_a["status_history"])
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "110.00")

    def test_put_exception_get_old_retries_and_can_recover(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = NoApplyThenRetryProductWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            no_apply_once_product_id=10,
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertIn("WRITE_RESPONSE_FAILED_REMOTE_OLD", target["status_history"])
        self.assertEqual(target["status"], "APPLIED_VERIFIED")
        self.assertEqual(result["audit_counts"]["retry_count"], 1)
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "110.00")

    def test_put_exception_get_unknown_restores_current_target_and_rolls_back(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = UnknownAfterPutExceptionWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            unknown_product_id=10,
            unknown_price=105,
        )
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["failed_restored_count"], 1)
        target = result["target_manifest"]["targets"][0]
        self.assertIn("WRITE_RESPONSE_FAILED_REMOTE_UNKNOWN", target["status_history"])
        self.assertEqual(target["status"], "FAILED_RESTORED")
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "100.00")

    def test_put_exception_get_failure_attempts_compensation(self):
        row = proposal("p", "product", 10, snapshot={"woo_id": 10, "type": "simple", "price": 100})
        woo = GetFailAfterPutExceptionWoo(
            {
                "products/10": {"id": 10, "price": "100.00", "regular_price": "100.00", "sale_price": ""},
            },
            lost_product_id=10,
        )
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        self.assertEqual(result["final_status"], "COMPLETED_WITH_ERRORS")
        self.assertEqual(audit["failed_restored_count"], 1)
        target = result["target_manifest"]["targets"][0]
        self.assertIn("WRITE_RESPONSE_FAILED_GET_FAILED", target["status_history"])
        self.assertEqual(target["status"], "FAILED_RESTORED")
        self.assertEqual(woo.rows_by_endpoint["products/10"]["price"], "100.00")

    def test_no_change_live_drift_is_not_reported_success(self):
        row = proposal("p", "product", 10, old_price=110, new_price=110, snapshot={"woo_id": 10, "type": "simple", "price": 110})
        target = {
            "remote_key": "product:10",
            "endpoint": "products/10",
            "cloud_item": {},
            "woo_id": 10,
            "remote_kind": "product",
            "canonical_key": "product:10",
        }
        preflight = {"blocking": False, "rows": [{
            "proposal_id": "p",
            "canonical_key": "product:10",
            "target": target,
            "woo_before": {"price": "110.00", "regular_price": "110.00", "sale_price": ""},
            "woo_before_full": {"id": 10, "price": "110.00", "regular_price": "110.00", "sale_price": ""},
            "woo_current_price": 110.0,
            "new_price": 110.0,
            "old_price_proposal": 110.0,
            "status": "NO_CHANGE",
            "pricing_payload": {},
            "pricing_strategy": "no_change",
            "proposal": row,
        }]}
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "112.00", "regular_price": "112.00", "sale_price": ""},
        })
        session = Session([row])

        with (
            patch.object(woocommerce_publish, "preview_price_proposal_group_publish", return_value=preflight),
            patch.object(woocommerce_publish, "acquire_system_lock"),
            patch.object(woocommerce_publish, "release_system_lock"),
            patch.object(woocommerce_publish, "sync_woocommerce_price_inventory_state", return_value={"ok": True}),
        ):
            result = woocommerce_publish.publish_price_proposal_group(
                session,
                proposal_ids=["p"],
                settings=settings(),
                client=woo,
            )

        audit = result["audit_counts"]
        self.assertEqual(audit["target_count"], 1)
        self.assertEqual(audit["verify_ok_count"], 0)
        self.assertEqual(audit["verify_fail_count"], 1)
        self.assertEqual(audit["failed_no_remote_change_count"], 1)
        self.assertEqual(result["target_manifest"]["targets"][0]["status"], "FAILED_NO_REMOTE_CHANGE")
        self.assertEqual(woo.writes, [])

    def test_no_change_real_uses_live_get_and_zero_put(self):
        row = proposal("p", "product", 10, old_price=110, new_price=110, snapshot={"woo_id": 10, "type": "simple", "price": 110})
        woo = StatefulWoo({
            "products/10": {"id": 10, "price": "110.00", "regular_price": "110.00", "sale_price": ""},
        })

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["p"])

        target = result["target_manifest"]["targets"][0]
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(target["status"], "ALREADY_MATCHED_VERIFIED")
        self.assertEqual(target["verify_attempts"], 1)
        self.assertEqual(woo.writes, [])

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

    def test_woo_only_0619005_empty_sale_above_regular_uses_effective_regular_payload(self):
        row = woo_only_price_source_proposal("woo-only-0619005", "0619005", 9907)
        woo = StatefulWoo({
            "products/3631/variations/9907": woo_row(
                9907,
                71.0,
                parent_id=3631,
                sku="0619005",
                regular_price=71.0,
                sale_price="",
            ),
        })

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["woo-only-0619005"])

        self.assertEqual(
            woo.writes,
            [("variation", 3631, 9907, {"regular_price": "83.78", "sale_price": ""})],
        )
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")
        self.assertEqual(result["line_results"][0]["pricing_payload"], {"regular_price": "83.78", "sale_price": ""})
        self.assertEqual(woo.rows_by_endpoint["products/3631/variations/9907"]["regular_price"], "83.78")
        self.assertEqual(woo.rows_by_endpoint["products/3631/variations/9907"]["sale_price"], "")

    def test_woo_only_0619006_empty_sale_above_regular_has_independent_state(self):
        row = woo_only_price_source_proposal("woo-only-0619006", "0619006", 9908)
        woo = StatefulWoo({
            "products/3631/variations/9908": woo_row(
                9908,
                71.0,
                parent_id=3631,
                sku="0619006",
                regular_price=71.0,
                sale_price="",
            ),
        })

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["woo-only-0619006"])

        self.assertEqual(
            woo.writes,
            [("variation", 3631, 9908, {"regular_price": "83.78", "sale_price": ""})],
        )
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["woo_id"], 9908)
        self.assertEqual(result["line_results"][0]["verify_ok"], True)

    def test_woo_only_sale_price_remains_supported_when_below_regular_price(self):
        row = woo_only_price_source_proposal("woo-only-sale-valid", "0619005", 9907, old_price=71.0, new_price=83.78)
        woo = StatefulWoo({
            "products/3631/variations/9907": woo_row(
                9907,
                90.0,
                parent_id=3631,
                sku="0619005",
                regular_price=90.0,
                sale_price="",
            ),
        })
        row["old_price"] = 90.0
        row["source_row"]["item_snapshot"]["price"] = "90.00"
        row["source_row"]["item_snapshot"]["regular_price"] = "90.00"

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["woo-only-sale-valid"])

        self.assertEqual(
            woo.writes,
            [("variation", 3631, 9907, {"sale_price": "83.78"})],
        )
        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(woo.rows_by_endpoint["products/3631/variations/9907"]["regular_price"], "90.00")
        self.assertEqual(woo.rows_by_endpoint["products/3631/variations/9907"]["sale_price"], "83.78")

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

    def test_legacy_product_endpoint_404_recovers_by_exact_sku_before_any_put(self):
        row = proposal(
            "legacy-direct-404",
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
        woo = LegacyProduct404VariationSkuWoo(live_variation)
        session = Session([row])

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            session,
            proposal_ids=["legacy-direct-404"],
            settings=settings(),
            client=woo,
        )
        self.assertTrue(preview["blocking"])
        self.assertTrue(preview["revalidation_possible"])
        self.assertEqual(preview["rows"][0]["status"], "REMOTE_IDENTITY_REVALIDATION_REQUIRED")
        self.assertIn(("products", {"sku": "0201010", "per_page": 100, "status": "any"}), woo.read_trace)

        with (
            patch.object(woocommerce_publish, "write_snapshot"),
            patch.object(woocommerce_publish, "write_audit_event"),
        ):
            with self.assertRaises(woocommerce_publish.PriceProposalRevalidationRequired):
                woocommerce_publish.publish_price_proposal_group(
                    session,
                    proposal_ids=["legacy-direct-404"],
                    settings=settings(),
                    client=woo,
                )
        self.assertEqual(woo.writes, [])
        refreshed = session.tables["price_change_proposals"][0]
        self.assertEqual(refreshed["item_kind"], "variation")
        self.assertEqual(refreshed["item_woo_id"], 12345)
        self.assertEqual(refreshed["source_row"]["woo_parent_id"], 900)

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
                proposal_ids=["legacy-direct-404"],
                settings=settings(),
                client=woo,
            )

        self.assertEqual(
            woo.writes,
            [("variation", 900, 12345, {"regular_price": "139.90", "sale_price": ""})],
        )
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

    def test_placeholder_101_without_remote_target_is_skipped_individually(self):
        row = placeholder_derived_proposal()
        session = Session([row])
        woo = StatefulWoo({})

        preview = woocommerce_publish.preview_price_proposal_group_publish(
            session,
            proposal_ids=["placeholder-101"],
            settings=settings(),
            client=woo,
        )

        preview_row = preview["rows"][0]
        self.assertFalse(preview["blocking"])
        self.assertEqual(preview_row["status"], "SKIPPED_UNRESOLVED_REMOTE_TARGET")
        self.assertEqual(preview_row["functional_status"], "SKIPPED_UNRESOLVED_REMOTE_TARGET")
        self.assertEqual(preview["counts"]["valid"], 1)
        self.assertEqual(preview["counts"]["woo_writes"], 0)
        self.assertEqual(preview_row["placeholder_relation"]["relation_id"], "101")
        self.assertEqual(woo.writes, [])

    def test_placeholder_between_valid_targets_does_not_abort_group_publish(self):
        valid_ids = list(range(101, 108)) + list(range(109, 121))
        rows = [
            proposal(
                f"target-{woo_id}",
                "product",
                woo_id,
                snapshot={"woo_id": woo_id, "type": "simple", "price": 100},
            )
            for woo_id in valid_ids
        ]
        rows.insert(7, placeholder_derived_proposal("placeholder-101"))
        woo = StatefulWoo({
            f"products/{woo_id}": woo_row(woo_id, 100, modified="T1")
            for woo_id in valid_ids
        })

        _session, result = self._publish_with_runtime_blackbox(
            rows,
            woo,
            [row["id"] for row in rows],
        )

        self.assertEqual(result["final_status"], "COMPLETED_WITH_SKIPS")
        self.assertEqual(result["audit_counts"]["target_count"], 20)
        self.assertEqual(result["audit_counts"]["processed_count"], 20)
        self.assertEqual(result["audit_counts"]["skipped_unresolved_remote_target_count"], 1)
        self.assertEqual(result["counts"]["woo_writes"], 19)
        self.assertEqual(len(woo.writes), 19)
        placeholder_line = next(line for line in result["line_results"] if line["proposal_id"] == "placeholder-101")
        self.assertEqual(placeholder_line["result"], "SKIPPED_UNRESOLVED_REMOTE_TARGET")
        self.assertFalse(placeholder_line["put_attempted"])

    def test_placeholder_real_woo_target_publishes_despite_local_quarantine(self):
        row = placeholder_derived_proposal(
            "resolved-placeholder",
            woo_id=4587,
            parent_id=3658,
            resolved=False,
        )
        woo = StatefulWoo({
            "products/3658/variations/4587": woo_row(4587, 100, parent_id=3658, modified="T1"),
        })

        _session, result = self._publish_with_runtime_blackbox(
            [row],
            woo,
            ["resolved-placeholder"],
        )

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")
        self.assertEqual(
            woo.writes,
            [("variation", 3658, 4587, {"regular_price": "101.00", "sale_price": ""})],
        )
        target = result["target_manifest"]["targets"][0]
        self.assertEqual(target["remote_key"], "variation:3658:4587")
        self.assertNotEqual(target["status"], "SKIPPED_PLACEHOLDER_RELATION")

    def test_placeholder_with_exact_sku_resolves_variation_target(self):
        row = placeholder_derived_proposal(
            "placeholder-sku-110",
            woo_id=999999,
            parent_id=3658,
            old_price=250,
            new_price=251,
        )
        source = row["source_row"]
        source["item_snapshot"].pop("woo_parent_id", None)
        source["item_snapshot"].pop("parent_woo_id", None)
        source["woo_price_context_at_creation"] = derived_context(4587, 250, parent_id=3658, modified="T1")
        source["future_pricing_payload"] = {"regular_price": "251.00", "sale_price": ""}
        live = woo_row(
            4587,
            250,
            parent_id=3658,
            sku="0201001|0201001|1249001|1249001|0615011|0615011",
            modified="T1",
        )
        woo = ExactSkuSearchWoo(
            {"products/3658/variations/4587": live},
            {live["sku"]: [live]},
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["placeholder-sku-110"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")
        self.assertEqual(woo.writes, [("variation", 3658, 4587, {"regular_price": "251.00", "sale_price": ""})])

    def test_placeholder_out_of_stock_with_price_remains_eligible(self):
        row = placeholder_derived_proposal("placeholder-outofstock", old_price=250, new_price=251)
        live = woo_row(4587, 250, parent_id=3658, modified="T1")
        live.update({"stock_status": "outofstock", "stock_quantity": 0})
        woo = StatefulWoo({"products/3658/variations/4587": live})

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["placeholder-outofstock"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")

    def test_placeholder_purchasable_false_with_price_remains_eligible(self):
        row = placeholder_derived_proposal("placeholder-purchasable-false", old_price=250, new_price=251)
        live = woo_row(4587, 250, parent_id=3658, modified="T1")
        live["purchasable"] = False
        woo = StatefulWoo({"products/3658/variations/4587": live})

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["placeholder-purchasable-false"])

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["line_results"][0]["result"], "APPLIED")

    def test_placeholder_real_target_without_price_skips_no_base_price(self):
        row = placeholder_derived_proposal("placeholder-no-price", old_price=250, new_price=251)
        live = woo_row(4587, 250, parent_id=3658, modified="T1")
        live.update({"price": "", "regular_price": "", "sale_price": ""})
        woo = StatefulWoo({"products/3658/variations/4587": live})

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["placeholder-no-price"])

        self.assertEqual(result["final_status"], "COMPLETED_WITH_SKIPS")
        self.assertEqual(result["audit_counts"]["skipped_no_base_price_count"], 1)
        self.assertEqual(result["line_results"][0]["result"], "SKIPPED_NO_BASE_PRICE")
        self.assertEqual(woo.writes, [])

    def test_placeholder_ambiguous_exact_sku_skips_unresolved_remote_target(self):
        row = placeholder_derived_proposal(
            "placeholder-ambiguous-sku",
            woo_id=999999,
            parent_id=3658,
            old_price=250,
            new_price=251,
        )
        source = row["source_row"]
        source["item_snapshot"].pop("woo_parent_id", None)
        source["item_snapshot"].pop("parent_woo_id", None)
        sku = source["combination_sku"]
        woo = ExactSkuSearchWoo(
            {},
            {
                sku: [
                    woo_row(4587, 250, parent_id=3658, sku=sku, modified="T1"),
                    woo_row(4588, 250, parent_id=3658, sku=sku, modified="T1"),
                ]
            },
        )

        _session, result = self._publish_with_runtime_blackbox([row], woo, ["placeholder-ambiguous-sku"])

        self.assertEqual(result["final_status"], "COMPLETED_WITH_SKIPS")
        self.assertEqual(result["audit_counts"]["skipped_unresolved_remote_target_count"], 1)
        self.assertEqual(result["line_results"][0]["result"], "SKIPPED_UNRESOLVED_REMOTE_TARGET")
        self.assertEqual(woo.writes, [])

    def test_tatami_80x200_placeholder_regression_processes_real_targets(self):
        direct = proposal(
            "tatami-0201001",
            "product",
            4548,
            old_price=100,
            new_price=102,
            snapshot={"woo_id": 4548, "type": "simple", "price": 100, "woo_sku": "0201001"},
        )
        real_combo = derived_proposal(
            "combo-3667",
            "variation",
            3667,
            old_price=700,
            new_price=704,
            parent_id=3612,
        )
        placeholder = placeholder_derived_proposal("placeholder-4587", woo_id=4587, parent_id=3658)
        woo = StatefulWoo({
            "products/4548": woo_row(4548, 100, sku="0201001", modified="T1"),
            "products/3612/variations/3667": woo_row(
                3667,
                700,
                parent_id=3612,
                sku="0302018|0201001|0201001",
                modified="T1",
            ),
            "products/3658/variations/4587": woo_row(
                4587,
                100,
                parent_id=3658,
                sku="0201001|0201001|1249001|1249001|0615011|0615011",
                modified="T1",
            ),
        })

        _session, result = self._publish_with_runtime_blackbox(
            [direct, real_combo, placeholder],
            woo,
            ["tatami-0201001", "combo-3667", "placeholder-4587"],
        )

        self.assertEqual(result["final_status"], "SUCCESS_VERIFIED")
        self.assertEqual(result["audit_counts"]["processed_count"], 3)
        self.assertEqual(result["audit_counts"]["applied_verified_count"], 3)
        self.assertEqual(result["audit_counts"]["skipped_placeholder_relation_count"], 0)
        self.assertEqual(result["audit_counts"]["skipped_unresolved_remote_target_count"], 0)
        self.assertEqual([write[0] for write in woo.writes], ["product", "variation", "variation"])
        placeholder_target = next(
            target for target in result["target_manifest"]["targets"] if target["proposal_id"] == "placeholder-4587"
        )
        self.assertEqual(placeholder_target["status"], "APPLIED_VERIFIED")
        self.assertTrue(placeholder_target["put_attempted"])

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

    def test_successful_publish_returns_from_editor_to_saved_proposals(self):
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._cloud_session = Session([])
        app._content = FakeWidget()
        app._current_key = "precios"
        app._price_mode = "edit"
        app._price_publish_in_progress = True
        app._price_edit_lines = [object()]
        app._price_proposal_model = {"direct": object()}
        app._price_proposal_line_sources = {"direct": {}}
        app._price_catalog_generation = 0
        app._price_bulk_preview_dimensions = lambda *_args: (800, 600, 400, 300)
        app.after = lambda _ms, callback: callback()
        app._price_stop_working_overlay = lambda *_args, **_kwargs: None
        app._price_start_working_overlay = lambda *_args, **_kwargs: FakeWidget()
        app._price_record_refresh_diagnostic = lambda *_args, **_kwargs: None
        calls: list[tuple] = []
        app._show_view = lambda key: calls.append(("show_view", key, app._price_mode))
        app._refresh_price_proposals = lambda parent, *, source="automatico": calls.append(("refresh", source, app._price_mode, parent is app._content))
        buttons: list[FakeWidget] = []

        def fake_button(_parent, text, *, primary=False, command=None):
            button = FakeWidget(text=text, primary=primary, command=command)
            buttons.append(button)
            return button

        app._button = fake_button
        proposal_model = PriceProposal(
            "Smoke propuesta",
            "01/01/2026",
            1,
            1,
            0,
            0,
            "+1.0%",
            "Ready",
            tuple(),
        )
        preview = {
            "counts": {"total": 1, "valid": 1, "warnings": 0, "errors": 0, "stale": 0, "direct": 1, "derived": 0, "excluded": 0, "woo_writes": 1},
            "rows": [
                {"proposal_id": "direct", "entry_origin": "DIRECT_ITEM", "name": "Direct", "code": "D", "status": "VALIDO", "proposal": {"id": "direct"}},
            ],
            "exclusions": [],
            "blocking": False,
        }

        with (
            patch.object(erp_prototype_module.tk, "Toplevel", return_value=FakeWidget()),
            patch.object(erp_prototype_module.tk, "Frame", FakeWidget),
            patch.object(erp_prototype_module.tk, "Label", FakeWidget),
            patch.object(erp_prototype_module.ttk, "Treeview", FakeTreeview),
            patch.object(erp_prototype_module.ttk, "Scrollbar", FakeScrollbar),
            patch.object(erp_prototype_module, "center_window"),
            patch.object(erp_prototype_module.threading, "Thread", ImmediateThread),
            patch.object(erp_prototype_module, "load_settings", return_value=settings()),
            patch.object(
                erp_prototype_module,
                "publish_price_proposal_group",
                return_value={"operation_id": "OP-OK", "published": [], "line_results": [], "counts": {"woo_writes": 1}},
            ),
            patch.object(erp_prototype_module.messagebox, "showinfo") as showinfo,
        ):
            FutonHubErpPrototype._render_price_publish_preview(app, proposal_model, ["direct"], preview)
            publish_buttons = [button for button in buttons if button.options.get("primary")]
            self.assertEqual(len(publish_buttons), 1)
            publish_buttons[0].command()

        self.assertTrue(showinfo.called)
        self.assertFalse(app._price_publish_in_progress)
        self.assertEqual(app._price_mode, "saved")
        self.assertEqual(app._price_edit_lines, [])
        self.assertIn(("show_view", "precios", "saved"), calls)
        self.assertIn(("refresh", "automatico", "saved", True), calls)


if __name__ == "__main__":
    unittest.main()

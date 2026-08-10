"""Read-only Woo catalogue index and exact physical identity reconciliation.

The price workspace builds this index once per explicit session refresh.  It
uses the official ``WooCommerceClient`` iterators only, preserves literal SKUs
(including leading zeroes and suffixes), and never writes Woo or Supabase.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from futonhub.cloud.services.woocommerce_publish import _effective_woo_price
from futonhub.services.combination_price_impact import effective_edge_status, effective_resolution_status


ProgressCallback = Callable[[dict[str, Any]], None]

SESSION_USABLE_STATUSES = frozenset({
    # Backward-compatible terminal value emitted by the pre-8.3 direct GET
    # service. New reconciliation uses the more specific statuses below.
    "READY",
    "LOCAL_LINK_VERIFIED",
    "APPROVED_EDGE_VERIFIED",
    "RECOVERED_BY_EXACT_PRODUCT_SKU",
    "RECOVERED_BY_EXACT_VARIATION_SKU",
})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "si"}


def _money_text(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return ""


def _physical_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    source = dict(row.get("source") or {})
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
    item_id = _text(row.get("physical_item_id") or source.get("physical_item_id") or source.get("item_id") or row.get("item_id") or snapshot.get("item_id"))
    sku = _text(row.get("physical_sku") or source.get("physical_sku") or row.get("hub_item_code") or row.get("heca_reference") or snapshot.get("hub_item_code") or snapshot.get("heca_reference"))
    return item_id, sku


def _row_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(row.get("source") or {})
    snapshot = source.get("item_snapshot")
    return dict(snapshot) if isinstance(snapshot, Mapping) else dict(row)


@dataclass(frozen=True)
class WooReadOnlyIndex:
    products_by_id: dict[str, dict[str, Any]]
    products_by_exact_sku: dict[str, tuple[dict[str, Any], ...]]
    variations_by_id: dict[str, dict[str, Any]]
    variations_by_exact_sku: dict[str, tuple[dict[str, Any], ...]]
    variations_by_parent: dict[str, tuple[dict[str, Any], ...]]
    woo_entities_by_exact_literal_sku: dict[str, tuple[dict[str, Any], ...]]
    counts: dict[str, int]

    def entity(self, *, kind: str, woo_id: Any, parent_woo_id: Any = "") -> dict[str, Any] | None:
        key = _text(woo_id)
        if kind == "product":
            return self.products_by_id.get(key)
        if kind == "variation":
            candidate = self.variations_by_id.get(key)
            if candidate is None:
                return None
            if _text(candidate.get("parent_woo_id")) != _text(parent_woo_id):
                return None
            return candidate
        return None


def _entity(raw: Mapping[str, Any], *, kind: str, parent: Mapping[str, Any] | None = None) -> dict[str, Any]:
    item = dict(raw)
    parent_id = _text(item.get("parent_id") or (parent or {}).get("id")) if kind == "variation" else ""
    return {
        "woo_id": _text(item.get("id")),
        "parent_woo_id": parent_id,
        "woo_item_kind": kind,
        "woo_sku": _text(item.get("sku")),
        "name": _text(item.get("name")),
        "status": _text(item.get("status")),
        "regular_price": _text(item.get("regular_price")),
        "sale_price": _text(item.get("sale_price")),
        "effective_price": _money_text(_effective_woo_price(item)),
        "date_modified": item.get("date_modified_gmt") or item.get("date_modified") or "",
        "endpoint": f"products/{_text(item.get('id'))}" if kind == "product" else f"products/{parent_id}/variations/{_text(item.get('id'))}",
        "raw": item,
    }


def build_woo_read_only_index(woo_client: Any, *, progress_callback: ProgressCallback | None = None) -> WooReadOnlyIndex:
    """Page Woo products and their variations through the official GET client."""
    products: dict[str, dict[str, Any]] = {}
    variations: dict[str, dict[str, Any]] = {}
    variations_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def emit(phase: str, **event: Any) -> None:
        if progress_callback is not None:
            progress_callback({"phase": phase, "products": len(products), "variations": len(variations), **event})

    variable_products: list[dict[str, Any]] = []
    emit("BUILDING_WOO_INDEX")
    for raw_product in woo_client.iter_products():
        product = _entity(raw_product, kind="product")
        if product["woo_id"]:
            products[product["woo_id"]] = product
        if _text(raw_product.get("type")) in {"variable", "variable-subscription"} and product["woo_id"]:
            variable_products.append(dict(raw_product))
        emit("INDEXING_PRODUCTS", current_woo_id=product["woo_id"], current_sku=product["woo_sku"])

    for parent in variable_products:
        parent_id = _text(parent.get("id"))
        for raw_variation in woo_client.iter_product_variations(int(parent_id)):
            variation = _entity(raw_variation, kind="variation", parent=parent)
            if variation["woo_id"]:
                variations[variation["woo_id"]] = variation
                variations_by_parent[variation["parent_woo_id"]].append(variation)
            emit("INDEXING_VARIATIONS", current_woo_id=variation["woo_id"], current_sku=variation["woo_sku"])

    products_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    variations_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in products.values():
        if entity["woo_sku"]:
            products_by_sku[entity["woo_sku"]].append(entity)
            all_by_sku[entity["woo_sku"]].append(entity)
    for entity in variations.values():
        if entity["woo_sku"]:
            variations_by_sku[entity["woo_sku"]].append(entity)
            all_by_sku[entity["woo_sku"]].append(entity)
    emit("WOO_INDEX_READY")
    return WooReadOnlyIndex(
        products_by_id=products,
        products_by_exact_sku={key: tuple(value) for key, value in products_by_sku.items()},
        variations_by_id=variations,
        variations_by_exact_sku={key: tuple(value) for key, value in variations_by_sku.items()},
        variations_by_parent={key: tuple(value) for key, value in variations_by_parent.items()},
        woo_entities_by_exact_literal_sku={key: tuple(value) for key, value in all_by_sku.items()},
        counts={
            "products": len(products),
            "variations": len(variations),
            "exact_literal_skus": len(all_by_sku),
            "duplicate_exact_literal_skus": sum(1 for value in all_by_sku.values() if len(value) > 1),
        },
    )


def load_approved_woo_edges(path: Path) -> dict[str, dict[str, Any]]:
    """Load only approved, exact physical-to-Woo nodes from WOO-MAP-001A.3."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    nodes = {str(row.get("node_id") or ""): dict(row) for row in payload.get("woo_nodes") or []}
    clean_edges = [dict(row) for row in payload.get("composition_edges") or []]
    evidence_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in clean_edges:
        item_id = _text(edge.get("physical_item_id") or edge.get("component_item_id"))
        if item_id:
            evidence_by_item[item_id].append(edge)

    result: dict[str, dict[str, Any]] = {}
    for raw in payload.get("physical_nodes") or []:
        node = dict(raw)
        item_id = _text(node.get("canonical_item_id") or node.get("item_id"))
        woo_node = nodes.get(_text(node.get("woo_node_id")))
        if not item_id or woo_node is None:
            continue
        related = evidence_by_item.get(item_id, [])
        approved = [edge for edge in related if effective_edge_status(edge) == "EXACT"]
        if _text(node.get("map_status")) != "MAPPED_EXACT" or _text(node.get("human_decision_required")).upper() == "YES":
            continue
        result[item_id] = {
            "woo_id": _text(woo_node.get("woo_id")),
            "woo_parent_id": _text(woo_node.get("parent_woo_id")),
            "woo_item_kind": _text(woo_node.get("item_kind")),
            "woo_sku": _text(woo_node.get("sku")),
            "effective_edge_status": "EXACT" if approved or _text(node.get("map_status")) == "MAPPED_EXACT" else "",
            "effective_resolution_status": (
                effective_resolution_status(approved[0]) if approved else "MAPPED_EXACT_NODE"
            ),
            "resolution_confidence": _text(node.get("resolution_confidence")) or "HIGH",
        }
    return result


def _context_from_entity(
    *,
    item_id: str,
    physical_sku: str,
    entity: Mapping[str, Any],
    resolution_source: str,
    resolution_status: str,
    session_only: bool = False,
) -> dict[str, Any]:
    effective = _text(entity.get("effective_price"))
    if not effective:
        return _terminal_context(item_id, physical_sku, "ERROR_SYNC", "Woo no devolvió un precio efectivo calculable.")
    return {
        "physical_item_id": item_id,
        "physical_sku": physical_sku,
        "woo_id": _text(entity.get("woo_id")),
        "woo_parent_id": _text(entity.get("parent_woo_id")),
        "woo_item_kind": _text(entity.get("woo_item_kind")),
        "woo_sku": _text(entity.get("woo_sku")),
        "woo_name": _text(entity.get("name")),
        "regular_price": _text(entity.get("regular_price")),
        "sale_price": _text(entity.get("sale_price")),
        "effective_price": effective,
        "price": effective,
        "status": _text(entity.get("status")),
        "woo_date_modified": entity.get("date_modified") or "",
        "woo_endpoint": _text(entity.get("endpoint")),
        "price_source": "WOO_LIVE",
        "price_read_at": datetime.now(timezone.utc).isoformat(),
        "sync_status": resolution_status,
        "terminal_status": resolution_status,
        "resolution_status": resolution_status,
        "resolution_source": resolution_source,
        "resolution_confidence": "EXACT",
        "session_only": "YES" if session_only else "NO",
        "session_usable": "YES",
        "is_terminal": True,
        "error": "",
    }


def _terminal_context(item_id: str, sku: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "physical_item_id": item_id,
        "physical_sku": sku,
        "woo_id": "",
        "woo_parent_id": "",
        "woo_item_kind": "",
        "woo_sku": "",
        "woo_name": "",
        "regular_price": "",
        "sale_price": "",
        "effective_price": "",
        "price": "",
        "status": "",
        "woo_date_modified": "",
        "woo_endpoint": "",
        "price_source": "WOO_LIVE_UNAVAILABLE",
        "price_read_at": "",
        "sync_status": status,
        "terminal_status": status,
        "resolution_status": status,
        "resolution_source": "",
        "resolution_confidence": "",
        "session_only": "YES",
        "session_usable": "NO",
        "is_terminal": True,
        "error": reason,
    }


def resolve_physical_woo_identity(
    row: Mapping[str, Any],
    *,
    woo_index: WooReadOnlyIndex,
    approved_edges_by_item_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve a canonical physical item through only exact, literal paths."""
    item_id, sku = _physical_identity(row)
    snapshot = _row_snapshot(row)
    record_type = _text(snapshot.get("item_record_type") or row.get("item_record_type")).lower()
    if _text(row.get("catalog_live_status")) == "CANONICAL_NOT_LIVE":
        return _terminal_context(item_id, sku, "CANONICAL_NOT_LIVE", _text(row.get("catalogue_reason")) or "El canónico no está live.")
    if _bool(snapshot.get("is_pack") or row.get("is_pack")):
        return _terminal_context(item_id, sku, "PACK_ONLY", "Los packs no son operables en la propuesta de precio directa.")
    if record_type == "component_placeholder":
        return _terminal_context(item_id, sku, "COMPONENT_ONLY", "El registro es solo un componente placeholder.")
    if record_type == "alias":
        return _terminal_context(item_id, sku, "NOT_PRICE_OPERABLE", "Los aliases no son artículos físicos operables.")
    if row.get("price_operable") is not None and not _bool(row.get("price_operable")):
        return _terminal_context(item_id, sku, "NOT_PRICE_OPERABLE", "El artículo no está operable para precio directo.")
    if not item_id or not sku:
        return _terminal_context(item_id, sku, "NOT_PRICE_OPERABLE", "Falta identidad física exacta.")

    source = dict(row.get("source") or {})
    local_kind = _text(source.get("woo_item_kind") or row.get("woo_item_kind")).lower()
    local_id = _text(source.get("woo_id") or row.get("woo_id"))
    local_parent = _text(source.get("woo_parent_id") or row.get("woo_parent_id"))
    local_error = ""
    if local_kind in {"product", "variation"} and local_id:
        local = woo_index.entity(kind=local_kind, woo_id=local_id, parent_woo_id=local_parent)
        if local is not None and _text(local.get("woo_sku")) == sku:
            return _context_from_entity(
                item_id=item_id, physical_sku=sku, entity=local,
                resolution_source="LOCAL_LINK_WOO_INDEX_VERIFIED", resolution_status="LOCAL_LINK_VERIFIED",
            )
        local_error = "El enlace Woo local no coincide con el objeto o SKU literal live."

    approved = dict((approved_edges_by_item_id or {}).get(item_id) or {})
    if approved:
        candidate = woo_index.entity(
            kind=_text(approved.get("woo_item_kind")), woo_id=approved.get("woo_id"), parent_woo_id=approved.get("woo_parent_id"),
        )
        if candidate is not None and _text(candidate.get("woo_sku")) == sku:
            context = _context_from_entity(
                item_id=item_id, physical_sku=sku, entity=candidate,
                resolution_source="WOO_MAP_001A_APPROVED_EDGE", resolution_status="APPROVED_EDGE_VERIFIED", session_only=True,
            )
            context["approved_effective_edge_status"] = approved.get("effective_edge_status")
            context["approved_effective_resolution_status"] = approved.get("effective_resolution_status")
            return context

    candidates = list(woo_index.woo_entities_by_exact_literal_sku.get(sku) or ())
    if len(candidates) == 1:
        entity = candidates[0]
        kind = _text(entity.get("woo_item_kind"))
        return _context_from_entity(
            item_id=item_id, physical_sku=sku, entity=entity,
            resolution_source="WOO_EXACT_LITERAL_SKU_INDEX",
            resolution_status=("RECOVERED_BY_EXACT_PRODUCT_SKU" if kind == "product" else "RECOVERED_BY_EXACT_VARIATION_SKU"),
            session_only=True,
        )
    if len(candidates) > 1:
        return _terminal_context(item_id, sku, "AMBIGUOUS_WOO_LINK", f"El SKU literal {sku} tiene {len(candidates)} destinos Woo exactos.")
    if local_error:
        return _terminal_context(item_id, sku, "LINK_RECOVERY_REQUIRED", local_error)
    return _terminal_context(item_id, sku, "WOO_NOT_FOUND", f"No existe ningún producto ni variación Woo con SKU literal {sku}.")


def reconcile_woo_contexts(
    rows: Iterable[Mapping[str, Any]],
    *,
    woo_index: WooReadOnlyIndex,
    approved_edges_by_item_id: Mapping[str, Mapping[str, Any]] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    contexts: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    materialized = [dict(row) for row in rows]
    for position, row in enumerate(materialized, start=1):
        item_id, sku = _physical_identity(row)
        context = resolve_physical_woo_identity(row, woo_index=woo_index, approved_edges_by_item_id=approved_edges_by_item_id)
        contexts[item_id] = context
        outcomes.append({"row": row, "context": context})
        if progress_callback is not None:
            progress_callback({"phase": "RECONCILING_IDENTITIES", "current": position, "total": len(materialized), "current_sku": sku, "counts": counter_context_statuses(contexts.values())})
    return {
        "live_price_context_by_physical_item": contexts,
        "row_outcomes": outcomes,
        "counts": counter_context_statuses(contexts.values()),
        "writes": {"woo": 0, "supabase": 0, "sql": 0},
    }


def terminal_reconciliation_error(rows: Iterable[Mapping[str, Any]], error: str) -> dict[str, Any]:
    """Terminalize a failed Woo-index worker without reusing cached prices."""
    contexts: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        item_id, sku = _physical_identity(row)
        snapshot = _row_snapshot(row)
        record_type = _text(snapshot.get("item_record_type") or row.get("item_record_type")).lower()
        if _text(row.get("catalog_live_status")) == "CANONICAL_NOT_LIVE":
            context = _terminal_context(item_id, sku, "CANONICAL_NOT_LIVE", _text(row.get("catalogue_reason")) or error)
        elif _bool(snapshot.get("is_pack") or row.get("is_pack")):
            context = _terminal_context(item_id, sku, "PACK_ONLY", "Los packs no son operables en la propuesta de precio directa.")
        elif record_type == "component_placeholder":
            context = _terminal_context(item_id, sku, "COMPONENT_ONLY", "El registro es solo un componente placeholder.")
        elif record_type == "alias" or (row.get("price_operable") is not None and not _bool(row.get("price_operable"))):
            context = _terminal_context(item_id, sku, "NOT_PRICE_OPERABLE", "El registro no es operable para precio directo.")
        else:
            context = _terminal_context(item_id, sku, "ERROR_SYNC", error)
        contexts[item_id] = context
        outcomes.append({"row": row, "context": context})
    error_physical_item_ids = sorted(
        item_id
        for item_id, context in contexts.items()
        if _text(context.get("sync_status")) == "ERROR_SYNC"
    )
    return {
        "live_price_context_by_physical_item": contexts,
        "row_outcomes": outcomes,
        "counts": counter_context_statuses(contexts.values()),
        "error_physical_item_ids": error_physical_item_ids,
        "writes": {"woo": 0, "supabase": 0, "sql": 0},
    }


def counter_context_statuses(contexts: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(contexts)
    statuses = Counter(_text(context.get("sync_status")) or "PENDING" for context in values)
    return {
        "visible": len(values),
        "ready": sum(statuses[value] for value in SESSION_USABLE_STATUSES),
        "recovered_by_sku": statuses["RECOVERED_BY_EXACT_PRODUCT_SKU"] + statuses["RECOVERED_BY_EXACT_VARIATION_SKU"],
        "no_link": statuses["WOO_NOT_FOUND"] + statuses["LINK_RECOVERY_REQUIRED"],
        "component_only": statuses["COMPONENT_ONLY"],
        "excluded": statuses["PACK_ONLY"] + statuses["NOT_PRICE_OPERABLE"] + statuses["CANONICAL_NOT_LIVE"],
        "ambiguous": statuses["AMBIGUOUS_WOO_LINK"],
        "errors": statuses["ERROR_SYNC"],
        "pending_after_completion": statuses["PENDING"],
        "by_status": dict(sorted(statuses.items())),
    }

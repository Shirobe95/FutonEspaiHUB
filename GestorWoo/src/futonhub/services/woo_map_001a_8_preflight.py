"""Read-only persistence preflight for the frozen WOO-MAP-001A SAFE baseline.

The module deliberately owns no mutation path.  It evaluates a frozen master
against a live Woo GET index and rows previously read from ``inventory_items``.
Any actual relation persistence must be introduced in a separately approved
daytime cut with an explicit revalidation immediately before its first write.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol

from futonhub.services.woo_map_001a_7_reconciliation import _entity_fingerprint, _physical_fingerprint


SAFE_STATUSES = frozenset({"ACTIVE_DIRECT_WOO_VERIFIED", "ACTIVE_DIRECT_WOO_SAFE_PLAN"})
MAPPING_COLUMN_CANDIDATES = (
    "woo_item_kind",
    "woo_id",
    "woo_parent_id",
    "woo_sku",
    "woo_name",
    "woo_link_status",
    "woo_link_notes",
)
PHYSICAL_SELECT_COLUMNS = (
    "item_id",
    "hub_item_code",
    "heca_reference",
    "name",
    "family",
    "filter_family",
    "brand",
    "filter_group",
    "size",
    "filter_size",
    "catalog_range",
    "filter_gama",
    "item_record_type",
    "is_pack",
)


class WooIndexProtocol(Protocol):
    products_by_id: Mapping[str, Mapping[str, Any]]

    def entity(self, *, kind: str, woo_id: Any, parent_woo_id: Any = "") -> Mapping[str, Any] | None:
        """Return an entity only when its kind and parent match exactly."""


@dataclass(frozen=True)
class PreflightResult:
    rows: tuple[dict[str, str], ...]
    counts: dict[str, int]


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def safe_master_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Select the immutable 177-row SAFE baseline without inferred identities."""
    selected = [dict(row) for row in rows if text(row.get("woo_resolution_status")) in SAFE_STATUSES]
    selected.sort(key=lambda row: (text(row.get("physical_item_id")), text(row.get("physical_sku"))))
    if len(selected) != 177:
        raise ValueError(f"Expected 177 frozen SAFE rows, received {len(selected)}.")
    if len({text(row.get("physical_item_id")) for row in selected}) != 177:
        raise ValueError("SAFE baseline has duplicate physical_item_id values.")
    return [{key: text(value) for key, value in row.items()} for row in selected]


def live_physical_hash(row: Mapping[str, Any]) -> str:
    """Hash live identity through the same fields as the original canonical map."""
    normalized = {
        "item_id": text(row.get("item_id")),
        "hub_item_code": text(row.get("hub_item_code")),
        "heca_reference": text(row.get("heca_reference")),
        "name": text(row.get("name")),
        "family": text(row.get("family")),
        "filter_family": text(row.get("filter_family")),
        "brand": text(row.get("brand")),
        "filter_group": text(row.get("filter_group")),
        "size": text(row.get("size")),
        "filter_size": text(row.get("filter_size")),
        "catalog_range": text(row.get("catalog_range")),
        "filter_gama": text(row.get("filter_gama")),
    }
    return _physical_fingerprint(normalized)


def physical_identity_matches(plan: Mapping[str, Any], live: Mapping[str, Any]) -> bool:
    """Verify the literal physical code; leading zeroes and suffixes are significant."""
    expected = text(plan.get("physical_sku"))
    live_codes = {text(live.get("hub_item_code")), text(live.get("heca_reference"))} - {""}
    return expected in live_codes


def _current_mapping(row: Mapping[str, Any], mapping_columns: Iterable[str]) -> dict[str, str]:
    available = set(mapping_columns)
    return {column: text(row.get(column)) if column in available else "" for column in MAPPING_COLUMN_CANDIDATES}


def _mapping_state(
    plan: Mapping[str, Any],
    current: Mapping[str, str],
    mapping_columns: Iterable[str],
) -> tuple[str, str, str]:
    """Classify a current mapping without assuming missing optional schema fields."""
    available = set(mapping_columns)
    if "woo_id" not in available:
        return "READ_ERROR", "BLOCK_FUTURE_APPLY", "inventory_items.woo_id is not available through read-only schema discovery."

    expected = {
        "woo_id": text(plan.get("woo_id")),
        "woo_parent_id": text(plan.get("woo_parent_id")),
        "woo_item_kind": text(plan.get("woo_kind")),
        "woo_sku": text(plan.get("woo_sku")),
        "woo_name": text(plan.get("woo_name")),
    }
    exact_fields = [field for field in expected if field in available]
    populated = {field: value for field, value in current.items() if value}
    if all(current[field] == expected[field] for field in exact_fields):
        return "ALREADY_PERSISTED_EXACT", "NO_ACTION", ""
    if not populated:
        return "NEEDS_INSERT_OR_LINK", "SET_WOO_RELATION", ""
    if current["woo_id"] in {"", expected["woo_id"]}:
        return "NEEDS_SAFE_UPDATE", "COMPLETE_WOO_RELATION", "Current relation is empty or partial; preserve its snapshot before a future write."
    return "CONFLICT_EXISTING_MAPPING", "BLOCK_FUTURE_APPLY", f"Current woo_id={current['woo_id']} differs from frozen woo_id={expected['woo_id']}."


def evaluate_preflight(
    master_rows: Iterable[Mapping[str, Any]],
    live_inventory_rows: Iterable[Mapping[str, Any]],
    *,
    woo_index: WooIndexProtocol,
    mapping_columns: Iterable[str],
) -> PreflightResult:
    """Evaluate all SAFE rows; this function performs no network or persistence work."""
    safe_rows = safe_master_rows(master_rows)
    inventory_by_id = {text(row.get("item_id")): dict(row) for row in live_inventory_rows if text(row.get("item_id"))}
    discovered = tuple(mapping_columns)
    results: list[dict[str, str]] = []

    for plan in safe_rows:
        item_id = text(plan.get("physical_item_id"))
        current_live = inventory_by_id.get(item_id)
        current_mapping = _current_mapping(current_live or {}, discovered)
        result = {
            "physical_item_id": item_id,
            "physical_sku": text(plan.get("physical_sku")),
            "current_mapping_state": "",
            "woo_id": text(plan.get("woo_id")),
            "woo_parent_id": text(plan.get("woo_parent_id")),
            "woo_kind": text(plan.get("woo_kind")),
            "woo_sku": text(plan.get("woo_sku")),
            "woo_name": text(plan.get("woo_name")),
            "woo_status": text(plan.get("woo_status")),
            "current_supabase_woo_id": current_mapping["woo_id"],
            "current_supabase_parent_id": current_mapping["woo_parent_id"],
            "current_supabase_woo_kind": current_mapping["woo_item_kind"],
            "current_supabase_woo_sku": current_mapping["woo_sku"],
            "current_supabase_woo_name": current_mapping["woo_name"],
            "current_supabase_woo_link_status": current_mapping["woo_link_status"],
            "planned_action": "",
            "physical_hash": text(plan.get("physical_identity_sha256")),
            "live_physical_hash": "",
            "woo_hash": text(plan.get("woo_identity_sha256")),
            "live_woo_hash": "",
            "precondition_ok": "NO",
            "safe_to_apply": "NO",
            "blocking_reason": "",
        }

        if current_live is None:
            result.update(
                current_mapping_state="MISSING_PHYSICAL_ROW",
                planned_action="BLOCK_FUTURE_APPLY",
                blocking_reason="physical_item_id is absent from the read-only inventory_items result.",
            )
            results.append(result)
            continue

        result["live_physical_hash"] = live_physical_hash(current_live)
        if not physical_identity_matches(plan, current_live):
            result.update(
                current_mapping_state="READ_ERROR",
                planned_action="BLOCK_FUTURE_APPLY",
                blocking_reason="Live physical code does not match the literal frozen physical_sku.",
            )
            results.append(result)
            continue

        entity = woo_index.entity(
            kind=text(plan.get("woo_kind")),
            woo_id=text(plan.get("woo_id")),
            parent_woo_id=text(plan.get("woo_parent_id")),
        )
        parent_id = text(plan.get("woo_parent_id"))
        parent_exists = not parent_id or parent_id in woo_index.products_by_id
        if entity is None or not parent_exists:
            result.update(
                current_mapping_state="WOO_CHANGED_SINCE_PLAN",
                planned_action="BLOCK_FUTURE_APPLY",
                blocking_reason="Frozen Woo entity or required parent was not found in the live GET index.",
            )
            results.append(result)
            continue

        result["live_woo_hash"] = _entity_fingerprint(entity)
        if result["live_woo_hash"] != result["woo_hash"]:
            result.update(
                current_mapping_state="WOO_CHANGED_SINCE_PLAN",
                planned_action="BLOCK_FUTURE_APPLY",
                blocking_reason="Live Woo fingerprint differs from the frozen plan; re-review is required.",
            )
            results.append(result)
            continue

        state, action, note = _mapping_state(plan, current_mapping, discovered)
        result["current_mapping_state"] = state
        result["planned_action"] = action
        result["blocking_reason"] = note
        if state in {"NEEDS_INSERT_OR_LINK", "NEEDS_SAFE_UPDATE", "ALREADY_PERSISTED_EXACT"}:
            result["precondition_ok"] = "YES"
        if state in {"NEEDS_INSERT_OR_LINK", "NEEDS_SAFE_UPDATE"}:
            result["safe_to_apply"] = "YES_PREVIEW_ONLY"
        results.append(result)

    counts = dict(sorted(Counter(row["current_mapping_state"] for row in results).items()))
    if len(results) != 177:
        raise RuntimeError("Preflight did not preserve the 177-row SAFE scope.")
    return PreflightResult(rows=tuple(results), counts=counts)


def rollback_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Produce a local restore plan from read-only values, never a product snapshot."""
    result: list[dict[str, str]] = []
    for row in rows:
        result.append({
            "physical_item_id": text(row.get("physical_item_id")),
            "physical_sku": text(row.get("physical_sku")),
            "current_mapping_state": text(row.get("current_mapping_state")),
            "previous_woo_id": text(row.get("current_supabase_woo_id")),
            "previous_woo_parent_id": text(row.get("current_supabase_parent_id")),
            "previous_woo_item_kind": text(row.get("current_supabase_woo_kind")),
            "previous_woo_sku": text(row.get("current_supabase_woo_sku")),
            "previous_woo_name": text(row.get("current_supabase_woo_name")),
            "previous_woo_link_status": text(row.get("current_supabase_woo_link_status")),
            "future_restore_action": "RESTORE_PRE_APPLY_SNAPSHOT_BY_ITEM_ID",
        })
    return result

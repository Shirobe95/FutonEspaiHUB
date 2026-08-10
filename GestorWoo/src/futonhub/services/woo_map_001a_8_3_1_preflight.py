"""Pure 178-row planning rules for WOO-MAP-001A.8.3.1.

This module receives only frozen SAFE master rows plus read-only live evidence.
It does not know about client objects and cannot persist a Woo relation.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from futonhub.services.woo_link_status_compat import (
    LINKED,
    NO_DIRECT_WOO,
    TEST_TECHNICAL,
    UNKNOWN,
    UNLINKED,
    canonical_woo_link_status,
)


CORE_FIELDS = (
    ("woo_id", "woo_id", "write_woo_id"),
    ("woo_parent_id", "woo_parent_id", "write_woo_parent_id"),
    ("woo_kind", "woo_item_kind", "write_woo_kind"),
    ("woo_sku", "woo_sku", "write_woo_sku"),
)
PRE_APPLY_REQUIREMENTS = "CREATE_SNAPSHOT | REVALIDATE_WOO | REVALIDATE_SUPABASE"


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def integer(value: Any) -> int:
    try:
        return int(text(value) or "0")
    except ValueError:
        return 0


def link_status_transition(current_status: Any, *, direct_relation_verified: bool) -> dict[str, str]:
    """Plan a compatible status transition without changing the current value."""
    current = text(current_status)
    canonical = canonical_woo_link_status(current)
    if canonical == LINKED:
        return {
            "canonical_current_status": canonical,
            "relation_transition": "RELATION_ALREADY_LINKED_PRESERVE",
            "target_link_status": current,
            "write_link_status": "NO",
            "reason": "Existing linked/manual status is preserved exactly.",
            "requires_review": "NO",
        }
    if canonical == UNLINKED and direct_relation_verified:
        return {
            "canonical_current_status": canonical,
            "relation_transition": "UNLINKED_TO_LINKED_AFTER_EXACT_DIRECT_RELATION",
            "target_link_status": "Enlazado",
            "write_link_status": "YES",
            "reason": "A verified direct Woo relation replaces the known unlinked legacy state.",
            "requires_review": "NO",
        }
    if canonical == NO_DIRECT_WOO and direct_relation_verified:
        return {
            "canonical_current_status": canonical,
            "relation_transition": "NO_DIRECT_TO_LINKED_AFTER_EXACT_DIRECT_RELATION",
            "target_link_status": "Enlazado",
            "write_link_status": "YES",
            "reason": "The exact direct Woo entity is verified by the current live preflight.",
            "requires_review": "NO",
        }
    if canonical == TEST_TECHNICAL:
        return {
            "canonical_current_status": canonical,
            "relation_transition": "TEST_TECHNICAL_PRESERVE_REVIEW_REQUIRED",
            "target_link_status": current,
            "write_link_status": "NO",
            "reason": "TEST_NO_WOO is a technical marker and is never changed automatically.",
            "requires_review": "YES",
        }
    if canonical == UNKNOWN:
        return {
            "canonical_current_status": canonical,
            "relation_transition": "UNKNOWN_STATUS_PRESERVE_REVIEW_REQUIRED",
            "target_link_status": current,
            "write_link_status": "NO",
            "reason": "Unknown legacy link status requires a user rule before an automatic relation change.",
            "requires_review": "YES",
        }
    return {
        "canonical_current_status": canonical,
        "relation_transition": "NO_DIRECT_RELATION_EVIDENCE",
        "target_link_status": current,
        "write_link_status": "NO",
        "reason": "No verified direct Woo relation is available for a transition.",
        "requires_review": "YES",
    }


def build_preflight_rows(
    safe_master_rows: Iterable[Mapping[str, Any]],
    live_rows_by_id: Mapping[str, Mapping[str, Any]],
    validations_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Build one preflight state per SAFE physical record from live evidence."""
    safe_rows = [{key: text(value) for key, value in row.items()} for row in safe_master_rows]
    if len(safe_rows) != 178:
        raise ValueError(f"Expected 178 SAFE master rows, received {len(safe_rows)}.")
    if len({row.get('physical_item_id') for row in safe_rows}) != 178:
        raise ValueError("SAFE master rows contain duplicate physical_item_id values.")

    planned: list[dict[str, str]] = []
    for source in safe_rows:
        item_id = source["physical_item_id"]
        live = {key: text(value) for key, value in dict(live_rows_by_id.get(item_id) or {}).items()}
        validation = {key: text(value) for key, value in dict(validations_by_id.get(item_id) or {}).items()}
        current_status = live.get("woo_link_status", "")
        result = {
            "physical_item_id": item_id,
            "physical_sku": source.get("physical_sku", ""),
            "woo_resolution_status": source.get("woo_resolution_status", ""),
            "woo_status": source.get("woo_status", ""),
            "price_change_eligible": source.get("price_change_eligible", ""),
            "physical_hash": source.get("physical_identity_sha256", ""),
            "live_physical_hash": validation.get("live_physical_hash", ""),
            "woo_hash": source.get("woo_identity_sha256", ""),
            "live_woo_hash": validation.get("live_woo_hash", ""),
            "physical_identity_verified": validation.get("physical_identity_verified", "NO"),
            "woo_relation_verified": validation.get("woo_relation_verified", "NO"),
            "current_woo_id": live.get("woo_id", ""),
            "target_woo_id": source.get("woo_id", ""),
            "current_woo_parent_id": live.get("woo_parent_id", ""),
            "target_woo_parent_id": source.get("woo_parent_id", ""),
            "current_woo_kind": live.get("woo_item_kind", ""),
            "target_woo_kind": source.get("woo_kind", ""),
            "current_woo_sku": live.get("woo_sku", ""),
            "target_woo_sku": source.get("woo_sku", ""),
            "current_woo_name": live.get("woo_name", ""),
            "target_woo_name": source.get("woo_name", ""),
            "current_link_status": current_status,
            "canonical_current_status": "",
            "relation_transition": "",
            "link_status_reason": "",
            "target_link_status": current_status,
            "write_woo_id": "NO",
            "write_woo_parent_id": "NO",
            "write_woo_kind": "NO",
            "write_woo_sku": "NO",
            "write_woo_name": "NO",
            "write_link_status": "NO",
            "fields_to_write": "",
            "field_write_count": "0",
            "plan_status": "",
            "pre_apply_requirement": "",
            "blocking_reason": "",
        }
        physical_ok = result["physical_identity_verified"] == "YES"
        woo_ok = result["woo_relation_verified"] == "YES"
        if not physical_ok or not woo_ok:
            missing = []
            if not physical_ok:
                missing.append("physical identity/fingerprint")
            if not woo_ok:
                missing.append("Woo relation/fingerprint")
            result.update(
                plan_status="BLOCKED",
                pre_apply_requirement="REVALIDATE_WOO | REVALIDATE_SUPABASE",
                blocking_reason="Live validation failed: " + ", ".join(missing) + ".",
            )
            planned.append(result)
            continue

        changed: list[str] = []
        for target_field, current_field, write_field in CORE_FIELDS:
            target = source.get(target_field, "")
            if target and live.get(current_field, "") != target:
                result[write_field] = "YES"
                changed.append(target_field)
        if source.get("woo_name") and not live.get("woo_name"):
            result["write_woo_name"] = "YES"
            changed.append("woo_name")

        direct_after_apply = bool(source.get("woo_id"))
        transition = link_status_transition(current_status, direct_relation_verified=direct_after_apply)
        # A link-status transition is a consequence of this future mapping
        # write, never an automatic cleanup of an existing no-action row.
        result.update({
            key: text(value)
            for key, value in transition.items()
            if key not in {"requires_review", "write_link_status"}
        })
        result["link_status_reason"] = transition["reason"]
        if changed and transition["requires_review"] == "YES":
            result.update(
                plan_status="BLOCKED",
                pre_apply_requirement="RESOLVE_LINK_STATUS_REVIEW_THEN_REVALIDATE",
                blocking_reason=transition["reason"],
            )
        else:
            if changed and transition["write_link_status"] == "YES":
                result["write_link_status"] = "YES"
                changed.append("woo_link_status")
            if changed:
                result.update(plan_status="READY_FOR_APPLY", pre_apply_requirement=PRE_APPLY_REQUIREMENTS)
            else:
                result.update(plan_status="NO_ACTION_REQUIRED", blocking_reason="")
        result["fields_to_write"] = " | ".join(changed)
        result["field_write_count"] = str(len(changed))
        planned.append(result)
    planned.sort(key=lambda row: (integer(row.get("physical_item_id")), row.get("physical_sku", "")))
    return planned


def apply_ready_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Project only actual future field changes from READY rows."""
    projected: list[dict[str, str]] = []
    for source in rows:
        row = {key: text(value) for key, value in source.items()}
        if row.get("plan_status") != "READY_FOR_APPLY" or integer(row.get("field_write_count")) == 0:
            continue
        item = {
            "physical_item_id": row.get("physical_item_id", ""),
            "physical_sku": row.get("physical_sku", ""),
            "pre_apply_requirement": row.get("pre_apply_requirement", ""),
            "field_write_count": row.get("field_write_count", "0"),
            "fields_to_write": row.get("fields_to_write", ""),
            "physical_hash": row.get("physical_hash", ""),
            "woo_hash": row.get("woo_hash", ""),
        }
        for field in ("woo_id", "woo_parent_id", "woo_kind", "woo_sku", "woo_name", "link_status"):
            flag = f"write_{field}"
            if row.get(flag) == "YES":
                item[f"current_{field}"] = row.get(f"current_{field}", "")
                item[f"target_{field}"] = row.get(f"target_{field}", "")
        projected.append(item)
    return projected


def preflight_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    states = Counter(text(row.get("plan_status")) for row in values)
    writes = {
        "woo_id": sum(text(row.get("write_woo_id")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
        "woo_parent_id": sum(text(row.get("write_woo_parent_id")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
        "woo_kind": sum(text(row.get("write_woo_kind")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
        "woo_sku": sum(text(row.get("write_woo_sku")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
        "woo_name": sum(text(row.get("write_woo_name")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
        "woo_link_status": sum(text(row.get("write_link_status")) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values),
    }
    return {
        "safe_master_count": len(values),
        "rows_no_action": states["NO_ACTION_REQUIRED"],
        "rows_ready": states["READY_FOR_APPLY"],
        "rows_blocked": states["BLOCKED"],
        "total_field_writes": sum(writes.values()),
        "writes_by_field": writes,
    }

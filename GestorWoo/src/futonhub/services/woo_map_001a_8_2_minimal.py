"""Pure read-only planning rules for WOO-MAP-001A.8.2.

The module deliberately contains no persistence client.  A future approved
apply can consume its rows, but must repeat the live GET/SELECT preconditions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


CORE_FIELDS = (
    ("woo_id", "current_supabase_woo_id", "write_woo_id"),
    ("woo_parent_id", "current_supabase_parent_id", "write_parent"),
    ("woo_kind", "current_supabase_woo_kind", "write_kind"),
    ("woo_sku", "current_supabase_woo_sku", "write_sku"),
)


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def minimal_apply_rows(preflight_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Plan only fields that are empty or literally different from target.

    ``woo_name`` is a display cache/legacy fallback.  It is never a standalone
    write reason; an empty display cache can be filled while another relation
    field is being completed. ``woo_link_status`` remains deliberately pending
    because its semantic target has not been approved.
    """
    planned: list[dict[str, str]] = []
    for source in preflight_rows:
        row = {key: text(value) for key, value in source.items()}
        output = {
            "physical_item_id": row.get("physical_item_id", ""),
            "physical_sku": row.get("physical_sku", ""),
            "woo_id_current": row.get("current_supabase_woo_id", ""),
            "woo_id_target": row.get("woo_id", ""),
            "write_woo_id": "NO",
            "parent_current": row.get("current_supabase_parent_id", ""),
            "parent_target": row.get("woo_parent_id", ""),
            "write_parent": "NO",
            "kind_current": row.get("current_supabase_woo_kind", ""),
            "kind_target": row.get("woo_kind", ""),
            "write_kind": "NO",
            "sku_current": row.get("current_supabase_woo_sku", ""),
            "sku_target": row.get("woo_sku", ""),
            "write_sku": "NO",
            "name_current": row.get("current_supabase_woo_name", ""),
            "name_target": row.get("woo_name", ""),
            "write_name": "NO",
            "link_status_current": row.get("current_supabase_woo_link_status", ""),
            "link_status_target": "",
            "write_link_status": "NO",
            "name_policy": "",
            "link_status_policy": "PRESERVE_CURRENT_PENDING_USER_RULE",
            "difference_class": "",
            "field_write_count": "0",
            "safe_to_apply": "NO",
            "blocking_reason": row.get("blocking_reason", ""),
        }
        core_differences: set[str] = set()
        for target_key, current_key, write_key in CORE_FIELDS:
            target = row.get(target_key, "")
            current = row.get(current_key, "")
            if current != target:
                output[write_key] = "YES"
                core_differences.add(target_key)

        name_changed = output["name_current"] != output["name_target"]
        if not name_changed:
            output["name_policy"] = "ALREADY_MATCHED"
        elif output["name_current"]:
            output["name_policy"] = "PRESERVE_DESCRIPTIVE_CURRENT_VALUE"
        elif output["name_target"]:
            output["write_name"] = "YES"
            output["name_policy"] = "FILL_EMPTY_DISPLAY_CACHE"
        else:
            output["name_policy"] = "NO_TARGET_VALUE"

        if not core_differences and name_changed:
            output["difference_class"] = "NAME_ONLY_DIFFERENCE"
        elif core_differences == {"woo_sku"} and name_changed:
            output["difference_class"] = "SKU_AND_NAME_DIFFERENCE"
        elif set(CORE_FIELDS[i][0] for i in range(len(CORE_FIELDS))).issubset(core_differences) and name_changed:
            output["difference_class"] = "FULL_MAPPING_AND_NAME_DIFFERENCE"
        elif not core_differences:
            output["difference_class"] = "ALREADY_PERSISTED_EXACT"
        else:
            output["difference_class"] = "OTHER_FIELD_DIFFERENCE"

        writes = sum(output[field] == "YES" for field in (
            "write_woo_id", "write_parent", "write_kind", "write_sku", "write_name", "write_link_status",
        ))
        output["field_write_count"] = str(writes)
        preconditions_ok = row.get("precondition_ok") == "YES" and row.get("safe_to_apply", "").startswith("YES")
        output["safe_to_apply"] = "YES_PREVIEW_ONLY" if preconditions_ok else "NO"
        if not preconditions_ok and not output["blocking_reason"]:
            output["blocking_reason"] = "The frozen preflight is not currently safe for a future apply."
        planned.append(output)
    return planned


def minimal_apply_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    values = list(rows)
    classes = Counter(text(row.get("difference_class")) for row in values)
    return {
        "rows_total": len(values),
        "rows_no_write_needed": sum(text(row.get("field_write_count")) == "0" for row in values),
        "rows_name_only_difference": classes["NAME_ONLY_DIFFERENCE"],
        "rows_sku_missing": classes["SKU_AND_NAME_DIFFERENCE"],
        "rows_full_mapping_missing": classes["FULL_MAPPING_AND_NAME_DIFFERENCE"],
        "rows_with_future_fields": sum(int(text(row.get("field_write_count")) or "0") > 0 for row in values),
        "total_fields_future_write": sum(int(text(row.get("field_write_count")) or "0") for row in values),
        "woo_name_future_writes": sum(text(row.get("write_name")) == "YES" for row in values),
    }

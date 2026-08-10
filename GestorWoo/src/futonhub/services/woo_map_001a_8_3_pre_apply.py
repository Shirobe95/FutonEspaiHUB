"""Pure pre-apply semantics for WOO-MAP-001A.8.3.

The functions in this module consume frozen local evidence only.  They do not
import clients, perform network calls or contain any persistence path.  A
separate, explicitly approved apply would still need to recreate snapshots and
repeat its Woo/Supabase validations immediately before a mutation.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping


WRITE_FIELDS = (
    ("woo_id", "woo_id_current", "woo_id_target", "write_woo_id"),
    ("woo_parent_id", "parent_current", "parent_target", "write_parent"),
    ("woo_kind", "kind_current", "kind_target", "write_kind"),
    ("woo_sku", "sku_current", "sku_target", "write_sku"),
    ("woo_name", "name_current", "name_target", "write_name"),
    ("woo_link_status", "link_status_current", "link_status_target", "write_link_status"),
)
PRE_APPLY_REQUIREMENTS = "CREATE_SNAPSHOT | REVALIDATE_WOO | REVALIDATE_SUPABASE"


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def integer(value: Any) -> int:
    try:
        return int(text(value) or "0")
    except ValueError:
        return 0


def normalize_preflight_rows(
    minimal_rows: Iterable[Mapping[str, Any]],
    frozen_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Normalize the minimal preflight without mistaking prerequisites for blocks."""
    frozen_by_id = {text(row.get("physical_item_id")): dict(row) for row in frozen_rows}
    normalized: list[dict[str, str]] = []
    for source in minimal_rows:
        row = {key: text(value) for key, value in source.items()}
        frozen = frozen_by_id.get(row.get("physical_item_id", ""), {})
        field_write_count = integer(row.get("field_write_count"))
        precondition_ok = text(frozen.get("precondition_ok")) == "YES"
        source_safe = text(frozen.get("safe_to_apply")).startswith("YES")
        source_state = text(frozen.get("current_mapping_state"))
        source_reason = text(frozen.get("blocking_reason"))

        if field_write_count == 0:
            plan_status = "NO_ACTION_REQUIRED"
            blocking_reason = ""
            requirement = ""
        elif precondition_ok and source_safe:
            plan_status = "READY_FOR_APPLY"
            blocking_reason = ""
            requirement = PRE_APPLY_REQUIREMENTS
        else:
            plan_status = "BLOCKED"
            blocking_reason = source_reason or (
                f"Frozen preflight state {source_state or 'UNKNOWN'} does not pass the required live checks."
            )
            requirement = "RESOLVE_BLOCKER_THEN_REVALIDATE"

        normalized.append({
            **row,
            "frozen_preflight_state": source_state,
            "frozen_precondition_ok": "YES" if precondition_ok else "NO",
            "plan_status": plan_status,
            "pre_apply_requirement": requirement,
            "blocking_reason": blocking_reason,
            "physical_identity_sha256": text(frozen.get("physical_hash")),
            "woo_identity_sha256": text(frozen.get("woo_hash")),
        })
    normalized.sort(key=lambda row: (integer(row.get("physical_item_id")), row.get("physical_sku", "")))
    return normalized


def apply_ready_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Return only rows with actual relation-field changes for a future apply."""
    ready: list[dict[str, str]] = []
    for source in rows:
        row = {key: text(value) for key, value in source.items()}
        if row.get("plan_status") != "READY_FOR_APPLY" or integer(row.get("field_write_count")) <= 0:
            continue
        output = {
            "physical_item_id": row.get("physical_item_id", ""),
            "physical_sku": row.get("physical_sku", ""),
            "plan_status": row.get("plan_status", ""),
            "pre_apply_requirement": row.get("pre_apply_requirement", ""),
            "field_write_count": row.get("field_write_count", "0"),
            "fields_to_write": "",
            "physical_identity_sha256": row.get("physical_identity_sha256", ""),
            "woo_identity_sha256": row.get("woo_identity_sha256", ""),
        }
        changed: list[str] = []
        for field, current_key, target_key, flag_key in WRITE_FIELDS:
            if row.get(flag_key) != "YES":
                continue
            changed.append(field)
            output[f"{field}_current"] = row.get(current_key, "")
            output[f"{field}_target"] = row.get(target_key, "")
        output["fields_to_write"] = " | ".join(changed)
        if changed:
            ready.append(output)
    return ready


def preflight_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    values = list(rows)
    states = Counter(text(row.get("plan_status")) for row in values)
    writes_by_field = {
        field: sum(text(row.get(flag_key)) == "YES" and text(row.get("plan_status")) == "READY_FOR_APPLY" for row in values)
        for field, _current_key, _target_key, flag_key in WRITE_FIELDS
    }
    return {
        "rows_total": len(values),
        "no_action_required": states["NO_ACTION_REQUIRED"],
        "ready_for_apply": states["READY_FOR_APPLY"],
        "blocked": states["BLOCKED"],
        "field_writes_total": sum(writes_by_field.values()),
        "writes_by_field": writes_by_field,
    }


def build_master_pre_apply_rows(
    master_rows: Iterable[Mapping[str, Any]],
    private_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Preserve the 254 physical records while applying approved business rules."""
    private_by_sku = {text(row.get("physical_sku")): {key: text(value) for key, value in row.items()} for row in private_rows}
    result: list[dict[str, str]] = []
    for source in master_rows:
        row = {key: text(value) for key, value in source.items()}
        sku = row.get("physical_sku", "")
        if sku == "0902005":
            row.update(
                woo_resolution_status="SAFE_TECHNICAL_APPROVED_EQUIVALENCE",
                direct_entity="YES",
                safe_to_persist="YES",
                requires_user_review="NO",
                price_change_eligible="YES_IF_OTHER_PRICE_GATES_PASS",
                resolution_reason="Approved only for Natural = Crudo, sin barniz in the compatible untreated-wood context; persistence remains outside this cut.",
            )
        elif sku in private_by_sku:
            private = private_by_sku[sku]
            row.update(
                woo_resolution_status="ACTIVE_DIRECT_WOO_VERIFIED_PRIVATE",
                woo_status="private",
                direct_entity="YES",
                requires_user_review="NO",
                price_change_eligible="NO",
                resolution_reason=private.get("reason") or "Exact private Woo identity is retained for traceability and blocked from price changes.",
            )
        elif sku == "0402014":
            row.update(
                woo_resolution_status="DISTINCT_BASE_TATAMI_NO_WOO_RELATION",
                direct_entity="NO",
                safe_to_persist="NO",
                requires_user_review="YES",
                price_change_eligible="NO",
                resolution_reason="Approved as a distinct Base para Tatamis identity. No Woo relation is approved; do not reuse 0302009 or Woo 3661.",
            )
        result.append(row)
    if len(result) != 254:
        raise ValueError(f"Expected 254 physical rows in the master, received {len(result)}.")
    if len({row.get("physical_item_id", "") for row in result}) != 254:
        raise ValueError("The master contains duplicate physical_item_id values.")
    return result


def missing_direct_policy_rows(
    grouped_rows: Iterable[Mapping[str, Any]],
    master_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Classify the 64 missing direct entities without proposing a Woo relation."""
    master_by_id = {text(row.get("physical_item_id")): dict(row) for row in master_rows}
    result: list[dict[str, str]] = []
    for source in grouped_rows:
        row = {key: text(value) for key, value in source.items()}
        evidence = row.get("strict_gate_evidence", "")
        cause = row.get("possible_cause", "")
        if "HISTORICAL" in evidence or cause == "LIKELY_LEGACY_PRODUCT":
            classification = "LEGACY_OR_DISCONTINUED_CANDIDATE"
            reason = "Historical Woo evidence exists but no exact current direct entity passed the strict gates."
        elif evidence == "NO_COMPATIBLE_DIRECT_ENTITY_AFTER_FAMILY_OR_MODEL_GATE":
            classification = "WOOCOMMERCE_CATALOG_GAP"
            reason = "No compatible direct entity exists after the family/model gate; decide the commercial Woo catalog policy by group."
        else:
            classification = "BUSINESS_REVIEW_REQUIRED"
            reason = "A possible direct entity failed the size or variant gate, so no relation or creation is proposed."
        master = master_by_id.get(row.get("physical_item_id", ""), {})
        result.append({
            **row,
            "current_woo_resolution_status": text(master.get("woo_resolution_status")),
            "current_component_only": text(master.get("component_only")),
            "policy_classification": classification,
            "policy_reason": reason,
            "relation_action": "DO_NOT_CREATE_OR_ASSIGN_WOO",
            "user_decision_required": "YES",
        })
    if len(result) != 64:
        raise ValueError(f"Expected 64 direct-Woo-missing rows, received {len(result)}.")
    return result

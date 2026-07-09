from __future__ import annotations

from typing import Any


def _truthy_pack_flag(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes", "si", "s\u00ed"}


def normalize_inventory_numeric_code(value: Any) -> str:
    """Return the canonical lookup form without changing alphanumeric codes."""
    text = str(value or "").strip()
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text


def is_inventory_pack_row(row: dict[str, Any] | None) -> bool:
    """Identify pack inventory rows from the shared persisted signals."""
    if not isinstance(row, dict):
        return False
    source = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}

    def value(key: str) -> Any:
        candidate = row.get(key)
        return candidate if candidate not in (None, "") else source.get(key)

    record_type = str(value("hub_search_record_type") or value("item_record_type") or "").strip().lower()
    if record_type in {"woo_pack", "manual_pack"}:
        return True
    for key in ("item_id", "hub_search_code", "hub_item_code"):
        if str(value(key) or "").strip().upper().startswith("WOO-PACK-"):
            return True
    if "|" in str(value("woo_sku") or ""):
        return True
    if bool(
        value("hub_pack_components")
        or value("hub_pack_components_text")
        or value("hub_pack_components_multiline")
    ):
        return True
    is_pack = value("is_pack")
    if _truthy_pack_flag(is_pack):
        item_id = str(value("item_id") or "").strip()
        base_item_code = str(value("base_item_code") or "").strip()
        if record_type in {"", "simple"} and item_id.isdigit() and not base_item_code:
            return False
        return True
    return False


def is_supplier_order_eligible_inventory_row(row: dict[str, Any] | None) -> bool:
    """Return True only for base inventory rows suitable for purchasing."""
    eligible, _reason = supplier_order_eligibility_reason(row)
    return eligible


def supplier_order_eligibility_reason(row: dict[str, Any] | None) -> tuple[bool, str]:
    """Return supplier-order eligibility plus the exact rejection reason."""
    if not isinstance(row, dict):
        return False, "rejected:not_dict"
    source = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}

    def value(key: str) -> Any:
        candidate = row.get(key)
        return candidate if candidate not in (None, "") else source.get(key)

    record_type = str(value("hub_search_record_type") or value("item_record_type") or "").strip().lower()
    if record_type in {"woo_pack", "manual_pack"}:
        return False, f"rejected:item_record_type={record_type}"
    for key in ("item_id", "hub_search_code", "hub_item_code"):
        if str(value(key) or "").strip().upper().startswith("WOO-PACK-"):
            return False, "rejected:woo_pack_code"
    if "|" in str(value("woo_sku") or ""):
        return False, "rejected:woo_sku_composite"
    if any(
        value(key)
        for key in (
            "hub_pack_components",
            "hub_pack_components_text",
            "hub_pack_components_multiline",
        )
    ):
        return False, "rejected:pack_components"

    item_id = str(value("item_id") or "").strip()
    if not item_id or not item_id.isdigit():
        return False, "rejected:item_id_invalid"

    ineligible_record_types = {
        "alias",
        "component",
        "pack_alias",
        "pack_component",
        "search_alias",
        "search_projection",
        "synthetic",
        "woo_item",
        "woo_product",
        "woo_variation",
    }
    if record_type in ineligible_record_types:
        return False, f"rejected:item_record_type={record_type}"
    if record_type not in {"", "simple"}:
        return False, f"rejected:item_record_type={record_type}"

    hub_code = str(value("hub_search_code") or value("hub_item_code") or "").strip().upper()
    if hub_code.startswith(("WOO-ITEM-", "WOO-VAR-", "WOO-ALIAS-", "SEARCH-", "ALIAS-")):
        return False, "rejected:hub_search_record_type=derived"

    base_item_code = str(value("base_item_code") or "").strip()
    if base_item_code:
        return False, f"rejected:base_item_code={base_item_code}"

    relation_type = str(
        value("hub_search_relation_type")
        or value("relation_type")
        or value("token_type")
        or ""
    ).strip().lower()
    if relation_type in {"alias", "component", "pack_component", "search", "search_alias"}:
        return False, f"rejected:relation_type={relation_type}"

    for key in (
        "component_item_code",
        "parent_item_code",
        "related_item_code",
        "hub_search_related_code",
    ):
        related_value = value(key)
        if related_value not in (None, "", [], {}):
            return False, f"rejected:{key}={related_value}"

    is_pack = value("is_pack")
    if _truthy_pack_flag(is_pack):
        return True, "eligible:commercial_pack_or_simple"

    return True, "eligible"

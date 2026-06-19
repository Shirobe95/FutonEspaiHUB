from __future__ import annotations

from typing import Any


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
    is_pack = value("is_pack")
    if is_pack is True or str(is_pack or "").strip().lower() in {"1", "true", "yes", "si", "sí"}:
        return True
    for key in ("item_id", "hub_search_code", "hub_item_code"):
        if str(value(key) or "").strip().upper().startswith("WOO-PACK-"):
            return True
    if "|" in str(value("woo_sku") or ""):
        return True
    return bool(
        value("hub_pack_components")
        or value("hub_pack_components_text")
        or value("hub_pack_components_multiline")
    )


def is_supplier_order_eligible_inventory_row(row: dict[str, Any] | None) -> bool:
    """Return True only for base inventory rows suitable for purchasing."""
    if not isinstance(row, dict) or is_inventory_pack_row(row):
        return False
    source = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}

    def value(key: str) -> Any:
        candidate = row.get(key)
        return candidate if candidate not in (None, "") else source.get(key)

    item_id = str(value("item_id") or "").strip()
    if not item_id or not item_id.isdigit():
        return False

    record_type = str(value("hub_search_record_type") or value("item_record_type") or "").strip().lower()
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
        return False
    if record_type not in {"", "simple"}:
        return False

    hub_code = str(value("hub_search_code") or value("hub_item_code") or "").strip().upper()
    if hub_code.startswith(("WOO-ITEM-", "WOO-VAR-", "WOO-ALIAS-", "SEARCH-", "ALIAS-")):
        return False

    if str(value("base_item_code") or "").strip():
        return False

    relation_type = str(
        value("hub_search_relation_type")
        or value("relation_type")
        or value("token_type")
        or ""
    ).strip().lower()
    if relation_type in {"alias", "component", "pack_component", "search", "search_alias"}:
        return False

    if any(
        value(key) not in (None, "", [], {})
        for key in (
            "component_item_code",
            "parent_item_code",
            "related_item_code",
            "hub_search_related_code",
        )
    ):
        return False

    return True

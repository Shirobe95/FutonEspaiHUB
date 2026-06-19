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

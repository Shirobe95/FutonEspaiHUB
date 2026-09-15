"""Approved Woo-only price sources for Cambio de Precios.

These rows are Woo mirror identities, not physical inventory items.  They are
admitted only as explicit price proposal sources when the live Woo identity
matches the approved literal SKU and variation contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

@dataclass(frozen=True)
class WooOnlyPriceSourceDefinition:
    sku: str
    item_id: str
    woo_id: str
    parent_woo_id: str
    name: str
    filter_family: str
    filter_group: str
    filter_size: str
    filter_gama: str
    publish_target_field: str = "sale_price"


PRICE_SOURCE_WOO_ONLY_DEFINITIONS: dict[str, WooOnlyPriceSourceDefinition] = {
    "0619005": WooOnlyPriceSourceDefinition(
        sku="0619005",
        item_id="930000009907",
        woo_id="9907",
        parent_woo_id="3631",
        name="Funda 140x200x8 Crudo",
        filter_family="Fundas",
        filter_group="Funda Futón",
        filter_size="140x200x8",
        filter_gama="Crudo",
    ),
    "0619006": WooOnlyPriceSourceDefinition(
        sku="0619006",
        item_id="930000009908",
        woo_id="9908",
        parent_woo_id="3631",
        name="Funda 140x200x8 Negro",
        filter_family="Fundas",
        filter_group="Funda Futón",
        filter_size="140x200x8",
        filter_gama="Negro",
    ),
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return value is True or _text(value).casefold() in {"1", "true", "yes", "si"}


def _money_positive(value: Any) -> bool:
    try:
        return Decimal(str(value).replace(",", ".")) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _safe_money(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _effective_woo_price(data: Mapping[str, Any]) -> Decimal | None:
    sale = _safe_money(data.get("sale_price"))
    if sale is not None and sale > 0:
        return sale
    regular = _safe_money(data.get("regular_price"))
    if regular is not None and regular > 0:
        return regular
    return _safe_money(data.get("price"))


def _identity_values(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    snapshot = row.get("item_snapshot") if isinstance(row.get("item_snapshot"), Mapping) else {}
    sku = _text(
        row.get("physical_sku")
        or row.get("hub_item_code")
        or row.get("woo_sku")
        or row.get("sku")
        or snapshot.get("physical_sku")
        or snapshot.get("hub_item_code")
        or snapshot.get("woo_sku")
        or snapshot.get("sku")
    )
    item_id = _text(
        row.get("physical_item_id")
        or row.get("item_id")
        or snapshot.get("physical_item_id")
        or snapshot.get("item_id")
    )
    woo_id = _text(row.get("woo_id") or snapshot.get("woo_id"))
    parent_id = _text(
        row.get("woo_parent_id")
        or row.get("parent_woo_id")
        or snapshot.get("woo_parent_id")
        or snapshot.get("parent_woo_id")
    )
    kind = _text(row.get("woo_item_kind") or row.get("item_kind") or snapshot.get("woo_item_kind")).lower()
    return item_id, sku, woo_id, parent_id, kind


def woo_only_definition_for_sku(sku: Any) -> WooOnlyPriceSourceDefinition | None:
    return PRICE_SOURCE_WOO_ONLY_DEFINITIONS.get(_text(sku))


def approved_woo_only_price_source_woo_ids() -> tuple[int, ...]:
    return tuple(int(definition.woo_id) for definition in PRICE_SOURCE_WOO_ONLY_DEFINITIONS.values())


def is_approved_woo_only_price_source_row(row: Mapping[str, Any] | None) -> bool:
    if not isinstance(row, Mapping):
        return False
    snapshot = row.get("item_snapshot") if isinstance(row.get("item_snapshot"), Mapping) else {}
    record_type = _text(
        row.get("item_record_type")
        or row.get("hub_search_record_type")
        or snapshot.get("item_record_type")
        or snapshot.get("hub_search_record_type")
    ).lower()
    if record_type != "woo_item":
        return False
    item_id, sku, woo_id, parent_id, kind = _identity_values(row)
    definition = woo_only_definition_for_sku(sku)
    if definition is None:
        return False
    for candidate in (row, snapshot):
        for key in ("physical_sku", "hub_item_code", "woo_sku", "sku", "heca_reference"):
            value = _text(candidate.get(key))
            if value and value != definition.sku:
                return False
        for key in ("physical_item_id", "item_id"):
            value = _text(candidate.get(key))
            if value and value != definition.item_id:
                return False
        for key in ("woo_id",):
            value = _text(candidate.get(key))
            if value and value != definition.woo_id:
                return False
        for key in ("woo_parent_id", "parent_woo_id"):
            value = _text(candidate.get(key))
            if value and value != definition.parent_woo_id:
                return False
        value = _text(candidate.get("woo_item_kind") or candidate.get("item_kind")).lower()
        if value and value != "variation":
            return False
    if item_id and item_id != definition.item_id:
        return False
    if woo_id and woo_id != definition.woo_id:
        return False
    if parent_id and parent_id != definition.parent_woo_id:
        return False
    if kind and kind != "variation":
        return False
    return True


def _approved_row_from_live_variation(row: Mapping[str, Any]) -> dict[str, Any] | None:
    sku = _text(row.get("woo_sku") or row.get("sku"))
    definition = woo_only_definition_for_sku(sku)
    if definition is None:
        return None
    woo_id = _text(row.get("woo_id") or row.get("id"))
    parent_id = _text(row.get("woo_parent_id") or row.get("parent_woo_id") or row.get("parent_id"))
    kind = _text(row.get("woo_item_kind") or row.get("type")).lower()
    if woo_id != definition.woo_id or parent_id != definition.parent_woo_id:
        return None
    if kind and kind != "variation":
        return None
    if _text(row.get("status")).lower() != "publish":
        return None
    effective = _effective_woo_price(row)
    if effective is None or effective <= 0:
        return None
    result = dict(row)
    result.update({
        "item_id": definition.item_id,
        "physical_item_id": definition.item_id,
        "physical_sku": definition.sku,
        "display_code": definition.sku,
        "hub_item_code": definition.sku,
        "heca_reference": "",
        "base_item_code": "",
        "name": definition.name,
        "family": definition.filter_family,
        "filter_family": definition.filter_family,
        "filter_group": definition.filter_group,
        "filter_size": definition.filter_size,
        "filter_gama": definition.filter_gama,
        "item_record_type": "woo_item",
        "is_pack": False,
        "commercial_status": result.get("commercial_status") or "Activo",
        "price_operable": True,
        "sale_item": "YES",
        "inventory_visible": "NO",
        "physical_inventory_visible": "NO",
        "price_source_woo_only": "YES",
        "price_source_mode": "PRICE_SOURCE_WOO_ONLY",
        "price_source_evidence": "PRODUCT_VARIATIONS_EXACT_ID",
        "publish_target_field": definition.publish_target_field,
        "woo_id": int(definition.woo_id),
        "woo_parent_id": int(definition.parent_woo_id),
        "parent_woo_id": int(definition.parent_woo_id),
        "woo_item_kind": "variation",
        "woo_sku": definition.sku,
        "woo_link_status": "Enlazado",
        "woo_name": result.get("woo_name") or result.get("name") or definition.name,
        "woo_price": str(effective),
        "price": result.get("price") or str(effective),
    })
    return result


def _dedupe_exact_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in candidates:
        key = _identity_values(row)
        unique.setdefault(key, row)
    return list(unique.values())


def build_approved_woo_only_price_source_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    variation_rows: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return explicit Woo-only rows that may appear in the price selector."""
    candidates_by_sku: dict[str, list[dict[str, Any]]] = {sku: [] for sku in PRICE_SOURCE_WOO_ONLY_DEFINITIONS}
    for raw in rows:
        row = dict(raw)
        if not is_approved_woo_only_price_source_row(row):
            continue
        _item_id, sku, _woo_id, _parent, _kind = _identity_values(row)
        candidates_by_sku.setdefault(sku, []).append(row)
    for raw in variation_rows:
        row = _approved_row_from_live_variation(raw)
        if row is None or not is_approved_woo_only_price_source_row(row):
            continue
        _item_id, sku, _woo_id, _parent, _kind = _identity_values(row)
        candidates_by_sku.setdefault(sku, []).append(row)

    result: list[dict[str, Any]] = []
    for sku, definition in PRICE_SOURCE_WOO_ONLY_DEFINITIONS.items():
        candidates = _dedupe_exact_candidates(candidates_by_sku.get(sku) or [])
        if len(candidates) != 1:
            continue
        row = dict(candidates[0])
        row.update({
            "item_id": definition.item_id,
            "physical_item_id": definition.item_id,
            "physical_sku": definition.sku,
            "display_code": definition.sku,
            "hub_item_code": definition.sku,
            "heca_reference": "",
            "base_item_code": "",
            "name": definition.name,
            "family": definition.filter_family,
            "filter_family": definition.filter_family,
            "filter_group": definition.filter_group,
            "filter_size": definition.filter_size,
            "filter_gama": definition.filter_gama,
            "item_record_type": "woo_item",
            "is_pack": False,
            "commercial_status": row.get("commercial_status") or "Activo",
            "price_operable": True,
            "sale_item": "YES",
            "inventory_visible": "NO",
            "physical_inventory_visible": "NO",
            "price_source_woo_only": "YES",
            "price_source_mode": "PRICE_SOURCE_WOO_ONLY",
            "publish_target_field": definition.publish_target_field,
            "woo_id": int(definition.woo_id),
            "woo_parent_id": int(definition.parent_woo_id),
            "parent_woo_id": int(definition.parent_woo_id),
            "woo_item_kind": "variation",
            "woo_sku": definition.sku,
            "woo_link_status": "Enlazado",
        })
        result.append(row)
    return result


def validate_woo_only_price_source_entity(
    row: Mapping[str, Any],
    entity: Mapping[str, Any],
    *,
    require_commercial_flags: bool = True,
) -> tuple[bool, str]:
    if not is_approved_woo_only_price_source_row(row):
        return False, "Woo mirror is not an approved price source."
    item_id, sku, _woo_id, _parent_id, _kind = _identity_values(row)
    definition = woo_only_definition_for_sku(sku)
    if definition is None:
        return False, "SKU is not approved as Woo-only price source."

    live_id = _text(entity.get("woo_id") or entity.get("id"))
    live_parent = _text(entity.get("parent_woo_id") or entity.get("parent_id"))
    live_sku = _text(entity.get("woo_sku") or entity.get("sku"))
    live_kind = _text(entity.get("woo_item_kind") or entity.get("type")).lower()
    if live_kind != "variation":
        return False, "Woo target is not a variation."
    if item_id != definition.item_id:
        return False, "Mirror item_id does not match the approved source."
    if live_id != definition.woo_id:
        return False, "Woo variation id does not match the approved source."
    if live_parent != definition.parent_woo_id:
        return False, "Woo parent id does not match the approved source."
    if live_sku != definition.sku:
        return False, "Woo SKU does not match the approved literal SKU."
    if _text(entity.get("status")).lower() != "publish":
        return False, "Woo variation is not published."
    effective = entity.get("effective_price")
    if not _text(effective):
        try:
            effective = _effective_woo_price(dict(entity))
        except Exception:
            effective = None
    if not _money_positive(effective):
        return False, "Woo variation has no positive effective price."
    if require_commercial_flags:
        if "purchasable" in entity and not _bool(entity.get("purchasable")):
            return False, "Woo variation is not purchasable."
        if _text(entity.get("stock_status")) and _text(entity.get("stock_status")).lower() != "instock":
            return False, "Woo variation is not instock."
        if "manage_stock" in entity and _bool(entity.get("manage_stock")):
            return False, "Woo variation has managed stock enabled unexpectedly."
    return True, ""


def woo_only_filter_metadata(row: Mapping[str, Any]) -> dict[str, str] | None:
    if not is_approved_woo_only_price_source_row(row):
        return None
    _item_id, sku, _woo_id, _parent_id, _kind = _identity_values(row)
    definition = woo_only_definition_for_sku(sku)
    if definition is None:
        return None
    return {
        "item_id": definition.item_id,
        "hub_item_code": definition.sku,
        "heca_reference": "",
        "base_item_code": "",
        "name": definition.name,
        "filter_family": definition.filter_family,
        "filter_group": definition.filter_group,
        "filter_size": definition.filter_size,
        "filter_gama": definition.filter_gama,
    }


def woo_only_publish_target_field(source: Mapping[str, Any] | None) -> str:
    if not isinstance(source, Mapping):
        return ""
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
    for candidate in (source, snapshot):
        field = _text(candidate.get("publish_target_field"))
        if field:
            return field
    if is_approved_woo_only_price_source_row(source) or is_approved_woo_only_price_source_row(snapshot):
        return "sale_price"
    return ""

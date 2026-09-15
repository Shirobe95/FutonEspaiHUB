"""Canonical catalogue reconciliation for the price workspace.

The approved physical snapshot defines visibility and filter taxonomy.  A live
Supabase row enriches that canonical item, but it never decides whether the
item exists in the price catalogue.  This keeps missing or Woo-unlinked items
visible and explicitly blocked instead of silently removing them from the UI.

This module has no network or persistence client.  Callers provide already
read live rows and session-only Woo contexts.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from futonhub.core.catalog_policy import (
    is_discontinued_commercial_status,
    is_operationally_active,
    operational_inactive_reason,
)
from futonhub.ui.erp.catalog_filters import (
    FILTER_FIELDS,
    PhysicalCatalogSnapshot,
    natural_catalog_sort_key,
)
from futonhub.services.price_woo_only_sources import (
    is_approved_woo_only_price_source_row,
)


CATALOG_DIFF_COLUMNS = (
    "canonical_item_id", "physical_sku", "canonical_name",
    "canonical_filter_family", "canonical_filter_group", "canonical_filter_size", "canonical_filter_gama",
    "present_in_live_supabase", "present_in_price_catalogue", "present_in_filter_metadata",
    "woo_resolution_status", "reason",
)

FILTER_COVERAGE_COLUMNS = (
    "physical_item_id", "physical_sku", "name",
    "expected_filter_family", "expected_filter_group", "expected_filter_size", "expected_filter_gama",
    "live_filter_family", "live_filter_group", "live_filter_size", "live_filter_gama",
    "visible_in_family", "visible_in_group", "visible_in_size", "visible_in_gama", "status", "reason",
)

PRICE_PROPOSAL_IMPACT_ONLY_ITEM_IDS = frozenset({"208001", "216001"})
PRICE_PROPOSAL_HUMAN_CONFIRMED_NON_SELECTABLE_REASONS = {
    "608010": "OUT_OF_USE_CONFIRMED_NOT_PRICE_SOURCE",
    "608012": "OUT_OF_USE_CONFIRMED_NOT_PRICE_SOURCE",
    "616008": "OUT_OF_USE_CONFIRMED_NOT_PRICE_SOURCE",
    "616010": "OUT_OF_USE_CONFIRMED_NOT_PRICE_SOURCE",
    "616012": "OUT_OF_USE_CONFIRMED_NOT_PRICE_SOURCE",
    "608019": "COMBINATION_COMPONENT_ONLY_NOT_PRICE_SOURCE",
    "616019": "COMBINATION_COMPONENT_ONLY_NOT_PRICE_SOURCE",
}
PRICE_PROPOSAL_HUMAN_CONFIRMED_MISSING_WOO_SOURCE_CODES = frozenset({
    "0758087",
    "0780002",
    "0780007",
})
PRICE_PROPOSAL_NON_SELECTABLE_ITEM_IDS = (
    PRICE_PROPOSAL_IMPACT_ONLY_ITEM_IDS
    | frozenset(PRICE_PROPOSAL_HUMAN_CONFIRMED_NON_SELECTABLE_REASONS)
)
PRICE_PROPOSAL_SELECTABLE_AUDIT_CATEGORIES = (
    "ACTIVE_DIRECT_WOO",
    "ACTIVE_MISSING_WOO",
    "DESCATALOGADO",
    "OUT_OF_USE_CONFIRMED",
    "COMBINATION_COMPONENT_ONLY",
    "DERIVED_ONLY_NOT_PRICE_SOURCE",
    "WOO_MIRROR_NOT_PRICE_SOURCE",
    "STALE_WOO_LINK",
    "AMBIGUOUS_IDENTITY",
    "UNKNOWN",
)
PRICE_PROPOSAL_SAFE_HIDE_AUDIT_CATEGORIES = frozenset({
    "DESCATALOGADO",
    "OUT_OF_USE_CONFIRMED",
    "COMBINATION_COMPONENT_ONLY",
    "DERIVED_ONLY_NOT_PRICE_SOURCE",
    "WOO_MIRROR_NOT_PRICE_SOURCE",
})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _apply_runtime_price_policy(row: dict[str, Any], override: Mapping[str, Any]) -> None:
    price_policy = _text(override.get("price_policy_override")).upper()
    if price_policy:
        row["price_policy_override"] = price_policy
    if price_policy == "NO":
        row["price_operable"] = False
        row["sale_item"] = "NO"
        if _text(override.get("business_usage")):
            row["business_usage"] = _text(override.get("business_usage"))
        if _text(override.get("visibility_reason")):
            row["inventory_visibility_reason"] = _text(override.get("visibility_reason"))


def _apply_live_commercial_status(row: dict[str, Any]) -> None:
    if not is_discontinued_commercial_status(row.get("commercial_status")):
        return
    row["catalog_commercial_status"] = "DESCATALOGADO_NO_WOO_REQUIRED"
    row["woo_mapping_required"] = "NO"
    row["price_operable"] = False
    row["sale_item"] = "NO"
    if _text(row.get("operational_status")) in {"", "OPERATIONAL_BASELINE"}:
        row["operational_status"] = "HISTORICAL_OR_DISCONTINUED"
    row["quarantine_group"] = _text(row.get("quarantine_group")) or "DESCATALOGADO"
    row["quarantine_reason"] = _text(row.get("quarantine_reason")) or "DESCATALOGADO_NO_WOO_REQUIRED"


def physical_sku(row: Mapping[str, Any]) -> str:
    return _text(row.get("physical_sku") or row.get("hub_item_code") or row.get("heca_reference"))


def _has_direct_woo_identity(row: Mapping[str, Any]) -> bool:
    return bool(_text(row.get("woo_id") or row.get("woo_parent_id") or row.get("woo_sku")))


def _is_human_confirmed_missing_woo_price_source(row: Mapping[str, Any]) -> bool:
    return (
        physical_sku(row) in PRICE_PROPOSAL_HUMAN_CONFIRMED_MISSING_WOO_SOURCE_CODES
        and not _has_direct_woo_identity(row)
    )


def reconcile_canonical_catalogue(
    snapshot: PhysicalCatalogSnapshot,
    live_rows: Iterable[Mapping[str, Any]],
    *,
    visibility_overrides: Any | None = None,
) -> dict[str, Any]:
    """Return exactly one visible row for every approved canonical item.

    Supabase duplication and absence are retained as explicit diagnostics.  The
    first live row is only used to provide display data; the item remains
    blocked whenever that live identity is not unique.
    """
    live = [dict(row) for row in live_rows]
    by_item_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in live:
        item_id = _text(row.get("item_id"))
        if item_id:
            by_item_id[item_id].append(row)

    canonical_rows: list[dict[str, Any]] = []
    missing_live_ids: list[str] = []
    duplicate_live_ids: list[str] = []
    for item_id, canonical in snapshot.rows_by_item_id.items():
        candidates = by_item_id.get(item_id, [])
        if not candidates:
            merged = dict(canonical)
            merged.update({
                "item_id": item_id,
                "physical_item_id": item_id,
                "physical_sku": physical_sku(canonical),
                "catalog_live_status": "CANONICAL_NOT_LIVE",
                "catalogue_reason": "El articulo canónico no se recibió desde inventory_items live.",
                "price_operable": False,
                "operational_status": "CANONICAL_NOT_LIVE",
                "woo_id": "",
                "woo_parent_id": "",
                "woo_item_kind": "",
                "woo_sku": "",
            })
            missing_live_ids.append(item_id)
        else:
            live_row = dict(candidates[0])
            merged = {**dict(canonical), **live_row}
            merged.update({
                "item_id": item_id,
                "physical_item_id": item_id,
                "physical_sku": physical_sku(canonical),
                "catalog_live_status": "LIVE_DUPLICATE" if len(candidates) > 1 else "LIVE",
                "catalogue_reason": (
                    "inventory_items devolvió múltiples filas para el mismo item_id canónico."
                    if len(candidates) > 1 else ""
                ),
            })
            # Snapshot taxonomy is the approved commercial hierarchy.  Live
            # values are preserved separately for the audit but cannot hide a
            # physical item due to drift.
            for field in FILTER_FIELDS:
                merged[f"live_{field}"] = _text(live_row.get(field))
                merged[field] = _text(canonical.get(field))
            if len(candidates) > 1:
                duplicate_live_ids.append(item_id)
        # Keep the approved snapshot fields alongside the display/live data.
        # A live name or hierarchy drift is audit evidence, never a replacement
        # for the canonical reference exported by this reconciliation.
        merged["canonical_name"] = _text(canonical.get("name"))
        for field in FILTER_FIELDS:
            merged[f"canonical_{field}"] = _text(canonical.get(field))
        if visibility_overrides is not None:
            _apply_runtime_price_policy(merged, visibility_overrides.metadata_for_item_id(item_id))
        _apply_live_commercial_status(merged)
        canonical_rows.append(merged)

    canonical_ids = set(snapshot.rows_by_item_id)
    live_not_canonical = [row for row in live if _text(row.get("item_id")) not in canonical_ids]
    return {
        "canonical_rows": sorted(canonical_rows, key=lambda row: natural_catalog_sort_key(row.get("name") or row.get("item_id"))),
        "live_rows": live,
        "missing_live_ids": sorted(missing_live_ids, key=natural_catalog_sort_key),
        "duplicate_live_ids": sorted(duplicate_live_ids, key=natural_catalog_sort_key),
        "live_not_canonical_rows": live_not_canonical,
        "counts": {
            "canonical_expected": len(snapshot.rows_by_item_id),
            "live_received": len(live),
            "canonical_present_live": len(snapshot.rows_by_item_id) - len(missing_live_ids),
            "canonical_missing_live": len(missing_live_ids),
            "canonical_live_duplicates": len(duplicate_live_ids),
            "live_not_canonical": len(live_not_canonical),
            "price_catalogue_visible": len(canonical_rows),
        },
    }


def canonical_live_catalog_diff_rows(
    reconciliation: Mapping[str, Any],
    *,
    filter_metadata_by_item_id: Mapping[str, Mapping[str, Any]] | None = None,
    woo_context_by_item_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    metadata = filter_metadata_by_item_id or {}
    contexts = woo_context_by_item_id or {}
    result: list[dict[str, str]] = []
    for row in reconciliation.get("canonical_rows") or []:
        item = dict(row)
        item_id = _text(item.get("item_id"))
        live_status = _text(item.get("catalog_live_status"))
        context = dict(contexts.get(item_id) or {})
        reason = _text(item.get("catalogue_reason")) or _text(context.get("error"))
        result.append({
            "canonical_item_id": item_id,
            "physical_sku": physical_sku(item),
            "canonical_name": _text(item.get("canonical_name") or item.get("name")),
            "canonical_filter_family": _text(item.get("canonical_filter_family") or item.get("filter_family")),
            "canonical_filter_group": _text(item.get("canonical_filter_group") or item.get("filter_group")),
            "canonical_filter_size": _text(item.get("canonical_filter_size") or item.get("filter_size")),
            "canonical_filter_gama": _text(item.get("canonical_filter_gama") or item.get("filter_gama")),
            "present_in_live_supabase": "YES" if live_status == "LIVE" else "NO" if live_status == "CANONICAL_NOT_LIVE" else "DUPLICATE",
            "present_in_price_catalogue": "YES",
            "present_in_filter_metadata": "YES" if item_id in metadata else "NO",
            "woo_resolution_status": _text(context.get("sync_status")) or "PENDING",
            "reason": reason,
        })
    return result


def filter_coverage_audit_rows(
    reconciliation: Mapping[str, Any],
    *,
    filter_metadata_by_item_id: Mapping[str, Mapping[str, Any]],
    visible_item_ids: Iterable[Any],
    woo_context_by_item_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, str]]:
    metadata = filter_metadata_by_item_id
    visible = {_text(value) for value in visible_item_ids if _text(value)}
    contexts = woo_context_by_item_id or {}
    rows: list[dict[str, str]] = []
    for raw in reconciliation.get("canonical_rows") or []:
        item = dict(raw)
        item_id = _text(item.get("item_id"))
        expected = {field: _text(item.get(field)) for field in FILTER_FIELDS}
        live = {field: _text(item.get(f"live_{field}") or item.get(field)) for field in FILTER_FIELDS}
        cached = dict(metadata.get(item_id) or {})
        context = dict(contexts.get(item_id) or {})
        present_metadata = bool(cached)
        visible_once = item_id in visible
        if _text(item.get("catalog_live_status")) == "CANONICAL_NOT_LIVE":
            status = "CANONICAL_NOT_LIVE"
            reason = _text(item.get("catalogue_reason"))
        elif not present_metadata:
            status = "MISSING_FILTER_METADATA"
            reason = "No se construyó metadata de filtros para el artículo canónico."
        elif not visible_once:
            status = "FILTER_CACHE_EXCLUSION"
            reason = "El artículo canónico no está presente en la colección visible."
        elif any(_text(cached.get(field)) != expected[field] for field in FILTER_FIELDS):
            status = "FILTER_VALUE_MISMATCH"
            reason = "La metadata de filtros no coincide con la ruta canónica aprobada."
        else:
            status = "MATCH"
            reason = ""
        if status == "MATCH" and _text(context.get("sync_status")) in {"ERROR_SYNC", "WOO_NOT_FOUND", "AMBIGUOUS_WOO_LINK"}:
            # Woo status cannot remove the catalogue row. It is included only
            # as diagnostic evidence in the reason.
            reason = f"Visible pese a estado Woo {context.get('sync_status')}."
        rows.append({
            "physical_item_id": item_id,
            "physical_sku": physical_sku(item),
            "name": _text(item.get("name")),
            "expected_filter_family": expected["filter_family"],
            "expected_filter_group": expected["filter_group"],
            "expected_filter_size": expected["filter_size"],
            "expected_filter_gama": expected["filter_gama"],
            "live_filter_family": live["filter_family"],
            "live_filter_group": live["filter_group"],
            "live_filter_size": live["filter_size"],
            "live_filter_gama": live["filter_gama"],
            "visible_in_family": "YES" if visible_once and present_metadata else "NO",
            "visible_in_group": "YES" if visible_once and present_metadata else "NO",
            "visible_in_size": "YES" if visible_once and present_metadata else "NO",
            "visible_in_gama": "YES" if visible_once and present_metadata else "NO",
            "status": status,
            "reason": reason,
        })
    return rows


def operational_price_catalogue_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return operational rows allowed to enter the price module context."""
    return [dict(row) for row in rows if is_operationally_active(row)]


def is_price_proposal_selectable_catalogue_row(row: Mapping[str, Any]) -> bool:
    """Return whether a row may be selected as a main proposal item."""
    return price_proposal_non_selectable_reason(row) == ""


def price_proposal_non_selectable_reason(row: Mapping[str, Any]) -> str:
    """Return why a row cannot start a price proposal, or an empty string.

    Missing Woo metadata is intentionally not a reason here. Active catalogue
    rows without a direct Woo link remain selectable for recovery/review unless
    another canonical business signal marks them as non-operational.
    """
    if not is_operationally_active(row):
        return operational_inactive_reason(row)
    record_type = _text(row.get("item_record_type") or row.get("hub_search_record_type")).lower()
    if record_type == "woo_item" and not is_approved_woo_only_price_source_row(row):
        return "WOO_MIRROR_NOT_PRICE_SOURCE"
    item_id = _text(row.get("physical_item_id") or row.get("item_id"))
    if item_id in PRICE_PROPOSAL_IMPACT_ONLY_ITEM_IDS:
        return "IMPACT_TARGET_ONLY_NOT_PRICE_SOURCE"
    if item_id in PRICE_PROPOSAL_HUMAN_CONFIRMED_NON_SELECTABLE_REASONS:
        return PRICE_PROPOSAL_HUMAN_CONFIRMED_NON_SELECTABLE_REASONS[item_id]
    if _is_human_confirmed_missing_woo_price_source(row):
        return "ACTIVE_MISSING_WOO_CONFIRMED_NOT_PRICE_SOURCE"
    price_policy = _text(row.get("price_policy_override")).upper()
    if price_policy == "NO":
        return "NON_OPERATIONAL_PRICE_POLICY"
    if _text(row.get("sale_item")).upper() == "NO" and _text(row.get("price_operable")).casefold() == "false":
        return "NON_OPERATIONAL_PRICE_POLICY"
    operational_status = _text(row.get("operational_status")).upper()
    if operational_status in {"HISTORICAL_OR_DISCONTINUED", "OUT_OF_USE", "NON_OPERATIONAL"}:
        return operational_status
    quarantine_reason = _text(row.get("quarantine_reason")).upper()
    if quarantine_reason in {"SUPPLIER_COMPONENT_NOT_FOR_SALE", "COMBINATION_COMPONENT_ONLY"}:
        return "COMBINATION_COMPONENT_ONLY"
    return ""


def price_proposal_selectable_catalogue_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Exclude impact-only rows from the New Proposal selectable catalogue."""
    return [dict(row) for row in rows if is_price_proposal_selectable_catalogue_row(row)]


def classify_price_proposal_catalogue_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """Classify one price-catalogue row without mutating selection policy."""
    item_id = _text(row.get("physical_item_id") or row.get("item_id"))
    record_type = _text(row.get("item_record_type") or row.get("hub_search_record_type")).lower()
    if record_type == "woo_item":
        if is_approved_woo_only_price_source_row(row):
            return "ACTIVE_DIRECT_WOO", "Woo-only price source aprobado para Cambio de Precios."
        return "WOO_MIRROR_NOT_PRICE_SOURCE", "Mirror Woo no aprobado como fuente de Cambio de Precios."
    if item_id in PRICE_PROPOSAL_IMPACT_ONLY_ITEM_IDS:
        return "DERIVED_ONLY_NOT_PRICE_SOURCE", "Impact target aprobado; no debe iniciar propuestas."
    if _is_human_confirmed_missing_woo_price_source(row):
        return "ACTIVE_MISSING_WOO", "Artículo activo sin mapping Woo directo; no seleccionable por decisión humana."
    confirmed_reason = PRICE_PROPOSAL_HUMAN_CONFIRMED_NON_SELECTABLE_REASONS.get(item_id)
    if confirmed_reason:
        if confirmed_reason.startswith("COMBINATION_COMPONENT_ONLY"):
            return "COMBINATION_COMPONENT_ONLY", confirmed_reason
        return "OUT_OF_USE_CONFIRMED", confirmed_reason
    if is_discontinued_commercial_status(row.get("commercial_status")):
        return "DESCATALOGADO", "commercial_status descatalogado."
    live_status = _text(row.get("catalog_live_status")).upper()
    if live_status == "LIVE_DUPLICATE":
        return "AMBIGUOUS_IDENTITY", "inventory_items devolvió identidad duplicada."
    reason = price_proposal_non_selectable_reason(row)
    if reason:
        normalized_reason = reason.upper()
        if "DESCATALOG" in normalized_reason:
            return "DESCATALOGADO", reason
        if "COMPONENT" in normalized_reason:
            return "COMBINATION_COMPONENT_ONLY", reason
        if normalized_reason in {"IMPACT_TARGET_ONLY_NOT_PRICE_SOURCE"}:
            return "DERIVED_ONLY_NOT_PRICE_SOURCE", reason
        if normalized_reason in {"AMBIGUOUS_IDENTITY", "DUPLICATE_SUPABASE_CODE"}:
            return "AMBIGUOUS_IDENTITY", reason
        return "OUT_OF_USE_CONFIRMED", reason
    woo_link_status = _text(row.get("woo_link_status")).casefold()
    woo_live_status = _text(row.get("woo_live_status") or row.get("price_sync_status")).upper()
    if any(token in woo_link_status for token in ("stale", "roto", "caduc", "recuperar")) or woo_live_status in {
        "WOO_NOT_FOUND",
        "STALE_WOO_LINK",
        "BROKEN_WOO_LINK",
    }:
        return "STALE_WOO_LINK", "Mapping Woo requiere revisión."
    if record_type in {"component_placeholder"}:
        return "COMBINATION_COMPONENT_ONLY", "Registro componente/placeholder."
    if record_type in {"alias"}:
        return "AMBIGUOUS_IDENTITY", "Alias no resuelto como identidad física principal."
    if _has_direct_woo_identity(row):
        return "ACTIVE_DIRECT_WOO", "Artículo activo con mapping Woo."
    return "ACTIVE_MISSING_WOO", "Artículo activo sin mapping Woo directo; se mantiene revisable."


def audit_price_proposal_selectable_catalogue(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a read-only catalogue-selection audit for the price proposal picker."""
    audit_rows: list[dict[str, str]] = []
    counts = {category: 0 for category in PRICE_PROPOSAL_SELECTABLE_AUDIT_CATEGORIES}
    safe_hide_candidates: list[dict[str, str]] = []
    for raw in rows:
        row = dict(raw)
        classification, reason = classify_price_proposal_catalogue_row(row)
        counts[classification] = counts.get(classification, 0) + 1
        item_id = _text(row.get("physical_item_id") or row.get("item_id"))
        code = physical_sku(row)
        recommended_selectable = (
            "NO"
            if classification in PRICE_PROPOSAL_SAFE_HIDE_AUDIT_CATEGORIES
            or price_proposal_non_selectable_reason(row)
            else "YES"
        )
        audit_row = {
            "item_id": item_id,
            "code": code,
            "name": _text(row.get("name") or row.get("canonical_name")),
            "family": _text(row.get("family") or row.get("filter_family")),
            "group": _text(row.get("filter_group")),
            "commercial_status": _text(row.get("commercial_status")),
            "item_record_type": _text(row.get("item_record_type") or row.get("hub_search_record_type")),
            "operational_status": _text(row.get("operational_status")),
            "woo_id": _text(row.get("woo_id")),
            "woo_parent_id": _text(row.get("woo_parent_id")),
            "woo_sku": _text(row.get("woo_sku")),
            "woo_link_status": _text(row.get("woo_link_status")),
            "classification": classification,
            "reason": reason,
            "recommended_selectable": recommended_selectable,
            "impact_target_needed": "YES" if classification == "DERIVED_ONLY_NOT_PRICE_SOURCE" else "NO",
        }
        audit_rows.append(audit_row)
        if recommended_selectable == "NO":
            safe_hide_candidates.append(audit_row)
    return {
        "rows": audit_rows,
        "counts": counts,
        "total": len(audit_rows),
        "safe_hide_candidates": safe_hide_candidates,
        "selectable_counts": dict(sorted(Counter(
            audit_row["classification"]
            for audit_row in audit_rows
            if audit_row["recommended_selectable"] == "YES"
        ).items())),
        "total_selectable": sum(1 for audit_row in audit_rows if audit_row["recommended_selectable"] == "YES"),
    }


def write_csv(path: Path, columns: tuple[str, ...], rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _text(row.get(column)) for column in columns})
    return path


def counter_by(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(_text(row.get(field)) or "UNSPECIFIED" for row in rows).items()))

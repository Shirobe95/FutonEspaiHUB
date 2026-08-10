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

from futonhub.ui.erp.catalog_filters import FILTER_FIELDS, PhysicalCatalogSnapshot, natural_catalog_sort_key


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


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def physical_sku(row: Mapping[str, Any]) -> str:
    return _text(row.get("physical_sku") or row.get("hub_item_code") or row.get("heca_reference"))


def reconcile_canonical_catalogue(
    snapshot: PhysicalCatalogSnapshot,
    live_rows: Iterable[Mapping[str, Any]],
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

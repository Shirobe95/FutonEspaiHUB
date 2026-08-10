"""Local diagnostics for the read-only price catalogue session.

The helpers in this module only serialize facts already obtained by the
catalogue loader and the read-only Woo synchronizer.  They deliberately do not
create network clients or persistence clients.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


CATALOG_AUDIT_COLUMNS = (
    "physical_item_id",
    "physical_sku",
    "name",
    "record_type",
    "operational_status",
    "quarantine_group",
    "woo_id",
    "woo_parent_id",
    "woo_item_kind",
    "catalog_visible",
    "sync_eligible",
    "deduplicated_woo_key",
    "sync_status",
    "terminal_status",
    "exclusion_reason",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_catalog_audit_rows(sync_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    """Project every synchronized visible row into the stable 8.2 CSV shape."""
    rows: list[dict[str, str]] = []
    for outcome in sync_payload.get("row_outcomes") or []:
        raw = dict(outcome.get("row") or {})
        source = dict(raw.get("source") or {})
        snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
        identity = dict(outcome.get("identity") or {})
        terminal_status = _text(outcome.get("terminal_status"))
        rows.append({
            "physical_item_id": _text(identity.get("physical_item_id") or source.get("physical_item_id") or source.get("item_id")),
            "physical_sku": _text(identity.get("physical_sku") or source.get("physical_sku") or source.get("hub_item_code") or raw.get("code")),
            "name": _text(raw.get("name")),
            "record_type": _text(identity.get("record_type") or snapshot.get("item_record_type") or snapshot.get("hub_search_record_type")),
            "operational_status": _text(identity.get("operational_status") or source.get("operational_status")),
            "quarantine_group": _text(identity.get("quarantine_group") or source.get("quarantine_group")),
            "woo_id": _text(identity.get("woo_id") or source.get("woo_id")),
            "woo_parent_id": _text(identity.get("woo_parent_id") or source.get("woo_parent_id")),
            "woo_item_kind": _text(identity.get("woo_item_kind") or source.get("woo_item_kind") or source.get("item_kind")),
            "catalog_visible": "YES",
            "sync_eligible": "YES" if _text(outcome.get("deduplicated_woo_key")) else "NO",
            "deduplicated_woo_key": _text(outcome.get("deduplicated_woo_key")),
            "sync_status": _text(outcome.get("sync_status")),
            "terminal_status": terminal_status,
            "exclusion_reason": _text(outcome.get("exclusion_reason")),
        })
    return rows


def write_catalog_count_audit(
    sync_payload: Mapping[str, Any],
    *,
    stage_counts: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write the exhaustive catalogue audit once the read-only worker ends."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "PRICE_COMB_001B_8_2_CATALOG_COUNT_AUDIT.csv"
    summary_path = output / "PRICE_COMB_001B_8_2_COUNT_SUMMARY.md"
    rows = build_catalog_audit_rows(sync_payload)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    counts = {key: value for key, value in dict(sync_payload.get("counts") or {}).items()}
    stages = {key: value for key, value in dict(stage_counts).items()}
    summary_path.write_text(
        "# PRICE-COMB-001B.8.2 · Auditoría de conteo del catálogo\n\n"
        f"Generado: {datetime.now(timezone.utc).isoformat()}\n\n"
        "## Etapas\n\n"
        f"- Filas `list_all_cloud_inventory_items`: {stages.get('raw_inventory_rows', 0)}\n"
        f"- Tras `enrich_rows`: {stages.get('enriched_rows', 0)}\n"
        f"- Tras `_price_unified_search_rows`: {stages.get('unified_rows', 0)}\n"
        f"- Filas visibles en Cambio de Precios: {counts.get('visible', 0)}\n"
        f"- Identidades físicas candidatas: {counts.get('catalog_physical', 0)}\n"
        f"- Elegibles para GET Woo exacto: {counts.get('eligible', 0)}\n"
        f"- Destinos Woo únicos: {counts.get('total', 0)}\n"
        f"- Productos Woo: {counts.get('destinations_product', 0)}\n"
        f"- Variaciones Woo: {counts.get('destinations_variation', 0)}\n"
        f"- Duplicados ahorrados por fan-out: {counts.get('deduplicated', 0)}\n"
        f"- Contextos READY: {counts.get('ready', 0)}\n"
        f"- Estados terminales no READY: {counts.get('terminal_non_ready', 0)}\n"
        f"- Sin enlace Woo: {counts.get('no_link', 0)}\n"
        f"- Excluidos locales: {counts.get('excluded', 0)}\n"
        f"- Errores GET Woo: {counts.get('errors', 0)}\n"
        f"- `SYNC_PENDING` tras completar: {counts.get('pending_after_completion', 0)}\n\n"
        "## Interpretación\n\n"
        "`catalog_items`, `sync_eligible_items` y `unique_woo_destinations` no deben coincidir: "
        "el catálogo mantiene visibles exclusiones, las filas sin enlace no generan GET y varios artículos físicos "
        "pueden compartir un único destino Woo exacto. La auditoría conserva todas las filas para que la diferencia "
        "sea explicable, no para ajustar artificialmente los conteos.\n",
        encoding="utf-8",
    )
    return {"csv": csv_path, "summary": summary_path}


def write_filter_performance(
    measurements: Mapping[str, Any], *, output_dir: str | Path) -> Path:
    """Persist only local timing measurements from the session metadata cache."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "PRICE_COMB_001B_8_2_FILTER_PERFORMANCE.json"
    payload = {"cut": "PRICE-COMB-001B.8.2", "mode": "LOCAL_SESSION_CACHE", **dict(measurements)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path

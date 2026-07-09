from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from futonhub.cloud.audit import AuditEvent, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or text.upper() in {"#N/A", "NO ESTA", "NO ESTA", "NONE", "NULL", "NAN"}:
        return None
    try:
        return float(text.replace(",", "."))
    except Exception:
        return None


def _safe_int_or_none(value: Any) -> int | None:
    number = _safe_float_or_none(value)
    if number is None:
        return None
    return int(number)


def _clean_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text if text else None


def _resolve_csv_path(path: str | Path) -> Path:
    """Resuelve rutas CSV al ejecutar desde raiz o desde GestorWoo.

    Casos soportados:
    - docs/imports/file.csv desde raiz del proyecto.
    - docs/imports/file.csv desde GestorWoo.
    - ../docs/imports/file.csv desde GestorWoo.
    - ruta absoluta.
    """
    raw = Path(path)
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        cwd = Path.cwd()
        candidates.extend(
            [
                cwd / raw,
                cwd.parent / raw,
                cwd / "GestorWoo" / raw,
                cwd.parent / "GestorWoo" / raw,
            ]
        )
        # Si el usuario pasa docs/imports desde GestorWoo y el archivo solo
        # existe en la raiz, cwd.parent/raw lo encuentra. Si lo pasa desde raiz
        # y solo existe dentro de GestorWoo, cwd/GestorWoo/raw lo encuentra.

    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Devolvemos el primer candidato para que el FileNotFoundError sea claro.
    return candidates[0] if candidates else raw


def read_inventory_items_csv(path: str | Path) -> list[dict[str, Any]]:
    path = _resolve_csv_path(path)
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            try:
                item_id = int(str(raw.get("item_id") or "").strip())
            except Exception:
                continue
            name = _clean_text(raw.get("name"))
            if not name:
                continue
            row = {
                "item_id": item_id,
                "name": name,
                "cubic_meters": _safe_float_or_none(raw.get("cubic_meters")),
                "rotation_c": _safe_float_or_none(raw.get("rotation_c")),
                "packages": _safe_int_or_none(raw.get("packages")) or 1,
                "primary_supplier_price": _safe_float_or_none(raw.get("primary_supplier_price")),
                "pascal_price": _safe_float_or_none(raw.get("pascal_price")),
                "family": _clean_text(raw.get("family")),
                "subgroup": _clean_text(raw.get("subgroup")),
                "size": _clean_text(raw.get("size")),
                "materials": _clean_text(raw.get("materials")),
                "commercial_status": _clean_text(raw.get("commercial_status")) or "Normal",
                "heca_reference": _clean_text(raw.get("heca_reference")),
                "woo_sku": _clean_text(raw.get("woo_sku")),
                "notes": _clean_text(raw.get("notes")),
                "source": "import_excel_E-2026-03",
            }
            rows.append(row)
    return rows


def _existing_inventory_ids(session, item_ids: list[int]) -> set[int]:
    existing: set[int] = set()
    for i in range(0, len(item_ids), 100):
        batch = item_ids[i : i + 100]
        try:
            response = session.client.table("inventory_items").select("item_id").in_("item_id", batch).execute()
            for row in getattr(response, "data", None) or []:
                try:
                    existing.add(int(row.get("item_id")))
                except Exception:
                    pass
        except Exception:
            pass
    return existing


def preview_inventory_items_csv_import(session, csv_path: str | Path) -> dict[str, Any]:
    csv_path = _resolve_csv_path(csv_path)
    rows = read_inventory_items_csv(csv_path)
    item_ids = [int(row["item_id"]) for row in rows]
    existing = _existing_inventory_ids(session, item_ids)
    to_insert = [row for row in rows if int(row["item_id"]) not in existing]
    skipped = [row for row in rows if int(row["item_id"]) in existing]
    return {
        "csv_path": str(csv_path),
        "total_rows": len(rows),
        "existing_count": len(skipped),
        "missing_count": len(to_insert),
        "missing_sample": to_insert[:20],
        "existing_sample": skipped[:20],
    }


def import_inventory_items_csv(
    session,
    csv_path: str | Path,
    *,
    execute: bool = False,
    confirm: str = "",
) -> dict[str, Any]:
    csv_path = _resolve_csv_path(csv_path)
    preview = preview_inventory_items_csv_import(session, csv_path)
    if not execute:
        return {"mode": "preview", **preview}
    if confirm != "IMPORTAR_ITEMS":
        raise ValueError("Para ejecutar usa --confirm IMPORTAR_ITEMS")

    rows = read_inventory_items_csv(csv_path)
    existing = _existing_inventory_ids(session, [int(row["item_id"]) for row in rows])
    to_insert = [row for row in rows if int(row["item_id"]) not in existing]
    operation_id = new_operation_id("inventory_items_excel_import")
    now = _now_iso()
    payload: list[dict[str, Any]] = []
    for row in to_insert:
        clean = {k: v for k, v in row.items() if v not in (None, "")}
        clean["created_at"] = now
        clean["updated_at"] = now
        clean["source_row"] = {
            "operation_id": operation_id,
            "source_csv": str(csv_path),
            "created_from": "UI ERP import missing inventory items",
            "created_by_email": session.email,
        }
        payload.append(clean)

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Inventario",
                action="import_inventory_items_csv",
                entity_table="inventory_items",
                entity_id="bulk",
                before_data={"existing_count": preview.get("existing_count")},
                after_data={"insert_count": len(payload), "sample": payload[:20]},
                metadata={"csv_path": str(csv_path)},
            ),
        )
    except Exception:
        pass

    inserted = 0
    errors: list[str] = []
    for i in range(0, len(payload), 80):
        chunk = payload[i : i + 80]
        try:
            session.client.table("inventory_items").insert(chunk).execute()
            inserted += len(chunk)
        except Exception as exc:
            # Fallback schema-safe: remove optional source_row if schema cache complains.
            message = str(exc)
            if "source_row" in message:
                try:
                    chunk2 = [dict(row) for row in chunk]
                    for row in chunk2:
                        row.pop("source_row", None)
                    session.client.table("inventory_items").insert(chunk2).execute()
                    inserted += len(chunk2)
                    continue
                except Exception as exc2:
                    errors.append(str(exc2))
                    break
            errors.append(message)
            break

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Inventario",
                action="import_inventory_items_csv",
                entity_table="inventory_items",
                entity_id="bulk",
                status="success" if not errors else "error",
                message=f"Import inventory_items desde CSV: {inserted}/{len(payload)} insertados",
                metadata={"csv_path": str(csv_path), "errors": errors[:5]},
            ),
        )
    except Exception:
        pass

    return {
        "mode": "execute",
        "operation_id": operation_id,
        "total_rows": len(rows),
        "existing_count": len(existing),
        "insert_target": len(payload),
        "inserted": inserted,
        "errors": errors,
    }


def upsert_inventory_items_csv(
    session,
    csv_path: str | Path,
    *,
    execute: bool = False,
    confirm: str = "",
) -> dict[str, Any]:
    """Inserta o actualiza items desde CSV.

    Uso pensado para imports controlados como los 12 items faltantes E-2026-03.
    Actualiza campos de ficha de calculo: M3, rotacion, bultos y precios proveedor.
    No toca WooCommerce ni stock.
    """
    csv_path = _resolve_csv_path(csv_path)
    rows = read_inventory_items_csv(csv_path)
    preview = {
        "csv_path": str(csv_path),
        "total_rows": len(rows),
        "sample": rows[:20],
    }
    if not execute:
        return {"mode": "preview_upsert", **preview}
    if confirm != "IMPORTAR_ITEMS":
        raise ValueError("Para ejecutar usa --confirm IMPORTAR_ITEMS")

    operation_id = new_operation_id("inventory_items_excel_upsert")
    now = _now_iso()
    payload: list[dict[str, Any]] = []
    for row in rows:
        clean = {k: v for k, v in row.items() if v not in (None, "")}
        clean["updated_at"] = now
        clean.setdefault("created_at", now)
        clean["source_row"] = {
            "operation_id": operation_id,
            "source_csv": str(csv_path),
            "created_from": "UI ERP upsert inventory items",
            "created_by_email": session.email,
        }
        payload.append(clean)

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Inventario",
                action="upsert_inventory_items_csv",
                entity_table="inventory_items",
                entity_id="bulk",
                before_data={"mode": "upsert"},
                after_data={"upsert_count": len(payload), "sample": payload[:20]},
                metadata={"csv_path": str(csv_path)},
            ),
        )
    except Exception:
        pass

    upserted = 0
    errors: list[str] = []
    for i in range(0, len(payload), 80):
        chunk = payload[i : i + 80]
        try:
            session.client.table("inventory_items").upsert(chunk, on_conflict="item_id").execute()
            upserted += len(chunk)
        except Exception as exc:
            message = str(exc)
            # Fallback schema-safe: remove optional source_row / created_at if schema cache complains.
            chunk2 = [dict(row) for row in chunk]
            changed = False
            for optional in ("source_row", "created_at"):
                if optional in message:
                    for row in chunk2:
                        row.pop(optional, None)
                    changed = True
            if changed:
                try:
                    session.client.table("inventory_items").upsert(chunk2, on_conflict="item_id").execute()
                    upserted += len(chunk2)
                    continue
                except Exception as exc2:
                    errors.append(str(exc2))
                    break
            errors.append(message)
            break

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Inventario",
                action="upsert_inventory_items_csv",
                entity_table="inventory_items",
                entity_id="bulk",
                status="success" if not errors else "error",
                message=f"Upsert inventory_items desde CSV: {upserted}/{len(payload)} procesados",
                metadata={"csv_path": str(csv_path), "errors": errors[:5]},
            ),
        )
    except Exception:
        pass

    return {
        "mode": "execute_upsert",
        "operation_id": operation_id,
        "csv_path": str(csv_path),
        "total_rows": len(rows),
        "upserted": upserted,
        "errors": errors,
    }

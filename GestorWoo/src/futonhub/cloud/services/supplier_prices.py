from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from futonhub.cloud.audit import AuditEvent, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from futonhub.core.codes import (
    normalize_inventory_numeric_code,
    supplier_order_eligibility_reason,
)
from gestorwoo.config import Settings, load_settings


INVENTORY_PRICE_COLUMNS = "item_id,name,primary_supplier_price,pascal_price,updated_at,source_row"


@dataclass(frozen=True)
class LocalSupplierPrice:
    item_id: int
    supplier: str
    price: float
    currency: str
    source: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        text = str(value).strip().replace("\u20ac", "").replace("\u00e2\u201a\u00ac", "").replace("$", "").replace("%", "")
        text = text.replace(".", "").replace(",", ".") if "," in text else text
        return float(text)
    except Exception:
        return default


def _row_value(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if value not in (None, ""):
        return value
    source_row = row.get("source_row")
    if isinstance(source_row, dict):
        return source_row.get(key)
    return value


def _norm_supplier(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {
        "hemei": "Hemei",
        "heimei": "Hemei",
        "ekomat": "Ekomat",
        "pascal": "Pascal",
        "cipta": "Cipta",
    }
    return aliases.get(text.lower(), text or "Sin proveedor")


def resolve_supplier_order_effective_price(row: dict[str, Any], supplier: str) -> dict[str, Any]:
    """Select a valid supplier price without mutating inventory data."""
    provider = _norm_supplier(supplier)
    requested_provider = provider.lower()
    primary_price = _safe_float(_row_value(row, "primary_supplier_price"), 0.0)
    pascal_price = _safe_float(_row_value(row, "pascal_price"), 0.0)
    if requested_provider == "pascal":
        if pascal_price > 0:
            return {
                "price": pascal_price,
                "source": "pascal",
                "source_label": "Pascal",
                "column": "pascal_price",
                "requested_provider": "pascal",
                "fallback_used": False,
                "warning": "",
            }
        if primary_price > 0:
            primary_display = f"{primary_price:.2f}".replace(".", ",")
            return {
                "price": primary_price,
                "source": "primary_fallback_for_pascal",
                "source_label": "Principal fallback Pascal",
                "column": "primary_supplier_price",
                "requested_provider": "pascal",
                "fallback_used": True,
                "warning": (
                    "Precio Pascal no disponible. "
                    f"Se usa precio principal: {primary_display} EUR"
                ),
            }
        return {
            "price": 0.0,
            "source": "pascal",
            "source_label": "Pascal",
            "column": "pascal_price",
            "requested_provider": "pascal",
            "fallback_used": False,
            "warning": "",
        }
    return {
        "price": primary_price,
        "source": "primary",
        "source_label": "Principal",
        "column": "primary_supplier_price",
        "requested_provider": requested_provider,
        "fallback_used": False,
        "warning": "",
    }


def read_local_supplier_prices(settings: Settings | None = None) -> list[LocalSupplierPrice]:
    settings = settings or load_settings()
    db_path = Path(settings.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base local: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT item_id, supplier, price, currency, source, updated_at FROM supplier_prices"
        ).fetchall()
    finally:
        conn.close()

    result: list[LocalSupplierPrice] = []
    for row in rows:
        try:
            item_id = int(row["item_id"])
        except Exception:
            continue
        supplier = _norm_supplier(row["supplier"])
        price = _safe_float(row["price"])
        if item_id <= 0 or not supplier or price <= 0:
            continue
        result.append(
            LocalSupplierPrice(
                item_id=item_id,
                supplier=supplier,
                price=price,
                currency=str(row["currency"] or "EUR").strip() or "EUR",
                source=str(row["source"] or "SQLite supplier_prices").strip(),
                updated_at=str(row["updated_at"] or "").strip() or _now_iso(),
            )
        )
    return result


def _build_inventory_price_updates(local_rows: list[LocalSupplierPrice]) -> dict[int, dict[str, Any]]:
    """Map SQLite supplier_prices to Supabase inventory_items price columns.

    Supabase model confirmed by UI ERP work:
    - inventory_items.primary_supplier_price: main provider price.
    - inventory_items.pascal_price: Pascal alternative price when present.

    Local supplier_prices has one row per supplier. Pascal goes to pascal_price.
    Every non-Pascal provider goes to primary_supplier_price. If more than one
    non-Pascal price exists for the same item, the latest row overwrites the
    previous one and the conflict is recorded in source_row.
    """
    updates: dict[int, dict[str, Any]] = {}
    for row in local_rows:
        entry = updates.setdefault(
            row.item_id,
            {
                "item_id": row.item_id,
                "primary_supplier_price": None,
                "pascal_price": None,
                "source_row": {
                    "supplier_price_migration": {
                        "sources": [],
                        "conflicts": [],
                    }
                },
            },
        )
        migration = entry["source_row"]["supplier_price_migration"]
        migration["sources"].append(row.__dict__)
        if row.supplier.lower() == "pascal":
            if entry.get("pascal_price") not in (None, "") and float(entry["pascal_price"]) != row.price:
                migration["conflicts"].append(
                    {
                        "column": "pascal_price",
                        "old": entry["pascal_price"],
                        "new": row.price,
                        "supplier": row.supplier,
                    }
                )
            entry["pascal_price"] = row.price
        else:
            if entry.get("primary_supplier_price") not in (None, "") and float(entry["primary_supplier_price"]) != row.price:
                migration["conflicts"].append(
                    {
                        "column": "primary_supplier_price",
                        "old": entry["primary_supplier_price"],
                        "new": row.price,
                        "supplier": row.supplier,
                    }
                )
            entry["primary_supplier_price"] = row.price
            entry["source_row"]["primary_supplier"] = row.supplier
    return updates


def preview_supplier_prices_migration(session, settings: Settings | None = None) -> dict[str, Any]:
    local_rows = read_local_supplier_prices(settings)
    updates = _build_inventory_price_updates(local_rows)
    by_supplier: dict[str, int] = {}
    for row in local_rows:
        by_supplier[row.supplier] = by_supplier.get(row.supplier, 0) + 1
    conflicts = [
        {"item_id": item_id, "conflicts": data["source_row"]["supplier_price_migration"].get("conflicts", [])}
        for item_id, data in updates.items()
        if data["source_row"]["supplier_price_migration"].get("conflicts")
    ]

    cloud_count = 0
    try:
        response = session.client.table("inventory_items").select("item_id", count="exact").limit(1).execute()
        cloud_count = int(getattr(response, "count", 0) or 0)
    except Exception:
        cloud_count = -1

    missing_item_ids: list[int] = []
    try:
        item_ids = list(updates.keys())
        existing_ids: set[int] = set()
        for i in range(0, len(item_ids), 100):
            batch = item_ids[i : i + 100]
            response = (
                session.client.table("inventory_items")
                .select("item_id")
                .in_("item_id", batch)
                .execute()
            )
            for row in getattr(response, "data", None) or []:
                try:
                    existing_ids.add(int(row.get("item_id")))
                except Exception:
                    pass
        missing_item_ids = [int(item_id) for item_id in item_ids if int(item_id) not in existing_ids]
    except Exception:
        missing_item_ids = []

    return {
        "local_supplier_price_rows": len(local_rows),
        "inventory_items_to_update": len(updates),
        "cloud_inventory_items": cloud_count,
        "by_supplier": by_supplier,
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:10],
        "missing_inventory_items_count": len(missing_item_ids),
        "missing_inventory_items_sample": missing_item_ids[:30],
        "sample_updates": list(updates.values())[:10],
    }


def migrate_supplier_prices_to_supabase(
    session,
    *,
    settings: Settings | None = None,
    execute: bool = False,
    chunk_size: int = 80,
) -> dict[str, Any]:
    local_rows = read_local_supplier_prices(settings)
    updates = _build_inventory_price_updates(local_rows)
    preview = preview_supplier_prices_migration(session, settings)
    if not execute:
        return {
            "mode": "preview",
            **preview,
            "message": "Preview listo. Ejecuta con --confirm MIGRAR_PRECIOS_PROVEEDOR para actualizar inventory_items.",
        }

    operation_id = new_operation_id("supplier_price_columns_migration")
    now = _now_iso()
    payload_rows: list[dict[str, Any]] = []
    for item_id, data in updates.items():
        row: dict[str, Any] = {
            "item_id": item_id,
            "updated_at": now,
        }
        if data.get("primary_supplier_price") is not None:
            row["primary_supplier_price"] = data.get("primary_supplier_price")
        if data.get("pascal_price") is not None:
            row["pascal_price"] = data.get("pascal_price")
        row["source_row"] = data.get("source_row", {})
        payload_rows.append(row)

    migrated = 0
    errors: list[str] = []
    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Pedidos",
                action="migrate_supplier_prices_to_inventory_items",
                entity_table="inventory_items",
                entity_id="bulk",
                before_data={"cloud_inventory_items": preview.get("cloud_inventory_items")},
                after_data={
                    "local_supplier_price_rows": len(local_rows),
                    "inventory_items_to_update": len(updates),
                    "by_supplier": preview.get("by_supplier"),
                    "conflict_count": preview.get("conflict_count"),
                },
                metadata={"source": "GestorWoo/data/gestorwoo.sqlite3 supplier_prices"},
            ),
        )
    except Exception:
        pass

    skipped_missing: list[int] = []
    # Importante: NO usamos upsert aqui.
    # Si un item_id local no existe en inventory_items de Supabase, upsert intentaria
    # insertar una fila nueva sin columnas obligatorias como `name`, provocando:
    # null value in column "name" violates not-null constraint.
    # Para esta migracion solo queremos actualizar items existentes.
    for row in payload_rows:
        item_id = row.get("item_id")
        update_data = {k: v for k, v in row.items() if k != "item_id" and v is not None}
        if not update_data:
            continue
        try:
            existing = (
                session.client.table("inventory_items")
                .select("item_id")
                .eq("item_id", item_id)
                .limit(1)
                .execute()
            )
            existing_rows = getattr(existing, "data", None) or []
            if not existing_rows:
                skipped_missing.append(int(item_id))
                continue

            session.client.table("inventory_items").update(update_data).eq("item_id", item_id).execute()
            migrated += 1
        except Exception as exc:
            errors.append(f"item_id={item_id}: {exc}")
            if len(errors) >= 20:
                break

    status = "success" if not errors else "error"
    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Pedidos",
                action="migrate_supplier_prices_to_inventory_items",
                entity_table="inventory_items",
                entity_id="bulk",
                status=status,
                message=f"Migracion precios proveedor hacia inventory_items: {migrated}/{len(payload_rows)}",
                metadata={
                    "errors": errors[:5],
                    "skipped_missing_count": len(skipped_missing),
                    "skipped_missing_sample": skipped_missing[:20],
                    "by_supplier": preview.get("by_supplier"),
                    "conflict_count": preview.get("conflict_count"),
                },
            ),
        )
    except Exception:
        pass

    return {
        "mode": "execute",
        "operation_id": operation_id,
        "local_supplier_price_rows": len(local_rows),
        "inventory_items_to_update": len(updates),
        "migrated": migrated,
        "errors": errors,
        "skipped_missing_count": len(skipped_missing),
        "skipped_missing_sample": skipped_missing[:30],
        "by_supplier": preview.get("by_supplier"),
        "conflict_count": preview.get("conflict_count"),
    }


SUPPLIER_ORDER_INVENTORY_COLUMNS = (
    "item_id,name,heca_reference,hub_item_code,item_record_type,base_item_code,is_pack,"
    "woo_id,woo_sku,woo_item_kind,woo_parent_id,woo_link_status,"
    "primary_supplier_price,pascal_price,cubic_meters,rotation_c,packages,"
    "store_stock,warehouse_stock,weighted_average_cost,order_calculated_price,"
    "updated_at,source_row"
)

SUPPLIER_ORDER_CODE_FIELDS = ("item_id", "heca_reference", "hub_item_code", "woo_sku")
SUPPLIER_ORDER_DIRECT_PROBE_FIELDS = ("item_id", "hub_item_code", "heca_reference", "woo_sku")
SUPPLIER_ORDER_SOURCE_ROW_CODE_FIELDS = ("item_id", "hub_item_code", "heca_reference", "codigo", "referencia", "ID")
SUPPLIER_ORDER_MATCH_LEVELS = (
    ("item_id", "exact"),
    ("item_id", "canonical"),
    ("hub_item_code", "exact"),
    ("hub_item_code", "canonical"),
    ("heca_reference", "exact"),
    ("heca_reference", "canonical"),
    ("woo_sku", "exact"),
    ("woo_sku", "canonical"),
)
SUPPLIER_ORDER_DEBUG = False


class SupplierOrderCodeAmbiguityError(ValueError):
    pass


def _supplier_order_debug_log(message: str) -> None:
    if SUPPLIER_ORDER_DEBUG:
        print(message)


def _supplier_order_inventory_rows(session, page_size: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        query = (
            session.client.table("inventory_items")
            .select(SUPPLIER_ORDER_INVENTORY_COLUMNS)
            .order("item_id", desc=False)
        )
        if hasattr(query, "range"):
            query = query.range(start, start + page_size - 1)
            paged = True
        else:
            query = query.limit(page_size)
            paged = False
        response = query.execute()
        page = [dict(row) for row in (getattr(response, "data", None) or [])]
        rows.extend(page)
        _supplier_order_debug_log(f"[SUPPLIER_ORDER_BULK_READ] page_start={start} rows={len(page)} total_accum={len(rows)}")
        if not paged or len(page) < page_size:
            break
        start += page_size
    return rows


def _supplier_order_code_values(raw_code: str) -> list[str]:
    values = [str(raw_code or "").strip()]
    if values[0].isdigit():
        canonical = normalize_inventory_numeric_code(values[0])
        if canonical not in values:
            values.append(canonical)
    return [value for value in values if value]


def _supplier_order_probe_value_for_field(field: str, value: str) -> Any:
    if field == "item_id":
        try:
            return int(str(value).strip())
        except Exception:
            return value
    return value


def _supplier_order_probe_sample(row: dict[str, Any]) -> dict[str, Any]:
    source_row = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}
    return {
        "item_id": row.get("item_id"),
        "hub_item_code": row.get("hub_item_code"),
        "heca_reference": row.get("heca_reference"),
        "woo_sku": row.get("woo_sku"),
        "item_record_type": row.get("item_record_type"),
        "is_pack": row.get("is_pack"),
        "base_item_code": row.get("base_item_code"),
        "primary_supplier_price": row.get("primary_supplier_price"),
        "pascal_price": row.get("pascal_price"),
        "rotation_c": row.get("rotation_c"),
        "cubic_meters": row.get("cubic_meters"),
        "packages": row.get("packages"),
        "source_row_keys": sorted(str(key) for key in source_row.keys()),
    }


def _supplier_order_source_row_probe(session, raw_code: str, page_size: int = 500) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    values = {value.lower() for value in _supplier_order_code_values(raw_code)}
    start = 0
    while True:
        query = (
            session.client.table("inventory_items")
            .select(SUPPLIER_ORDER_INVENTORY_COLUMNS)
            .order("item_id", desc=False)
        )
        if hasattr(query, "range"):
            query = query.range(start, start + page_size - 1)
            paged = True
        else:
            query = query.limit(page_size)
            paged = False
        response = query.execute()
        page = [dict(row) for row in (getattr(response, "data", None) or [])]
        for row in page:
            source_row = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}
            for key in SUPPLIER_ORDER_SOURCE_ROW_CODE_FIELDS:
                value = str(source_row.get(key) or "").strip()
                if not value:
                    continue
                candidates = {value.lower()}
                if value.isdigit():
                    candidates.add(normalize_inventory_numeric_code(value).lower())
                if candidates.intersection(values):
                    row_key = _supplier_order_row_key(row)
                    if row_key in seen:
                        continue
                    seen.add(row_key)
                    found.append((f"source_row.{key}", row))
        if not paged or len(page) < page_size:
            break
        start += page_size
    sample = _supplier_order_probe_sample(found[0][1]) if found else {}
    _supplier_order_debug_log(f"[SUPPLIER_ORDER_DIRECT_PROBE_RAW] code={raw_code} by=source_row rows={len(found)} sample={sample}")
    return found


def _supplier_order_direct_probe(session, raw_code: str) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    all_rows = 0
    for field in SUPPLIER_ORDER_DIRECT_PROBE_FIELDS:
        for value in _supplier_order_code_values(raw_code):
            if field == "item_id" and not str(value or "").strip().isdigit():
                _supplier_order_debug_log(f"[SUPPLIER_ORDER_DIRECT_PROBE] code={raw_code} by=item_id skipped=non_numeric")
                continue
            probe_value = _supplier_order_probe_value_for_field(field, value)
            try:
                response = (
                    session.client.table("inventory_items")
                    .select(SUPPLIER_ORDER_INVENTORY_COLUMNS)
                    .eq(field, probe_value)
                    .limit(10)
                    .execute()
                )
                rows = [dict(row) for row in (getattr(response, "data", None) or [])]
            except Exception as exc:
                print(f"[SUPPLIER_ORDER_DIRECT_PROBE] code={raw_code} by={field} error={exc}")
                rows = []
            all_rows += len(rows)
            sample = rows[0] if rows else {}
            _supplier_order_debug_log(
                f"[SUPPLIER_ORDER_DIRECT_PROBE] code={raw_code} by={field} rows={len(rows)} "
                f"sample_item_id={sample.get('item_id', '')} "
                f"item_record_type={sample.get('item_record_type', '')} "
                f"is_pack={sample.get('is_pack', '')} "
                f"base_item_code={sample.get('base_item_code', '')} "
                f"hub_item_code={sample.get('hub_item_code', '')} "
                f"heca_reference={sample.get('heca_reference', '')}"
            )
            _supplier_order_debug_log(
                f"[SUPPLIER_ORDER_DIRECT_PROBE_RAW] code={raw_code} by={field} rows={len(rows)} "
                f"sample={_supplier_order_probe_sample(sample) if sample else {}}"
            )
            for row in rows:
                row_key = _supplier_order_row_key(row)
                if row_key in seen:
                    continue
                seen.add(row_key)
                found.append((field, row))
    if not found:
        for field, row in _supplier_order_source_row_probe(session, raw_code):
            row_key = _supplier_order_row_key(row)
            if row_key in seen:
                continue
            seen.add(row_key)
            found.append((field, row))
    if all_rows == 0:
        _supplier_order_debug_log(f"[SUPPLIER_ORDER_DIRECT_PROBE] code={raw_code} rows=0 in all fields")
    return found


def _supplier_order_row_key(row: dict[str, Any]) -> str:
    item_id = str(row.get("item_id") or "").strip()
    if item_id:
        return f"item_id:{item_id}"
    return "|".join(str(row.get(field) or "").strip().lower() for field in SUPPLIER_ORDER_CODE_FIELDS)


def _supplier_order_build_result(raw_code: str, row: dict[str, Any], field: str, match_mode: str, provider: str) -> dict[str, Any]:
    effective_price = resolve_supplier_order_effective_price(row, provider)
    return {
        "item_id": row.get("item_id"),
        "matched_by": f"{match_mode}:{field}",
        "matched_value": raw_code,
        "supplier": provider,
        "price": effective_price["price"],
        "currency": "EUR",
        "source": effective_price["source"],
        "source_label": effective_price["source_label"],
        "column": effective_price["column"],
        "requested_provider": effective_price["requested_provider"],
        "fallback_used": effective_price["fallback_used"],
        "warning": effective_price["warning"],
        "item": row,
    }


def _supplier_order_direct_fallback(session, raw_code: str, provider: str) -> dict[str, Any] | None:
    candidates = _supplier_order_direct_probe(session, raw_code)
    eligible: dict[str, tuple[str, dict[str, Any]]] = {}
    rejected_reasons: list[str] = []
    for field, row in candidates:
        is_eligible, reason = supplier_order_eligibility_reason(row)
        _supplier_order_debug_log(
            f"[SUPPLIER_ORDER_ELIGIBILITY] code={raw_code} item_id={row.get('item_id', '')} "
            f"eligible={str(is_eligible).lower()} reason={reason}"
        )
        if not is_eligible:
            rejected_reasons.append(reason)
            continue
        eligible[_supplier_order_row_key(row)] = (field, row)
    if len(eligible) > 1:
        candidate_ids = sorted(str(row.get("item_id") or "") for _field, row in eligible.values())
        raise SupplierOrderCodeAmbiguityError(
            f"Codigo de pedido ambiguo {raw_code!r} en fallback directo: "
            f"coincide con inventory_items {', '.join(candidate_ids)}."
        )
    if len(eligible) == 1:
        field, row = next(iter(eligible.values()))
        result = _supplier_order_build_result(raw_code, row, field, f"direct", provider)
        print(
            f"[SUPPLIER_ORDER_DIRECT_RESOLVED] code={raw_code} "
            f"matched_by={result.get('matched_by')} price={result.get('price')} "
            f"rotation_c={row.get('rotation_c', '')}"
        )
        return result
    if candidates:
        reason = rejected_reasons[0] if rejected_reasons else "rejected:unknown"
        _supplier_order_debug_log(f"[SUPPLIER_ORDER_DIRECT_PROBE] code={raw_code} usable=false reason={reason}")
    return None


def resolve_supplier_order_inventory_items(
    session,
    codes: list[Any] | tuple[Any, ...],
    supplier: str,
) -> dict[str, dict[str, Any]]:
    """Resolve order codes in one inventory read, exact before canonical."""
    raw_codes = [str(code or "").strip() for code in codes]
    requested = list(dict.fromkeys(code for code in raw_codes if code))
    if not requested:
        return {}

    indexes: dict[tuple[str, str], dict[str, dict[str, dict[str, Any]]]] = {
        level: {} for level in SUPPLIER_ORDER_MATCH_LEVELS
    }

    inventory_rows = _supplier_order_inventory_rows(session)
    requested_code_values = {code: set(_supplier_order_code_values(code)) for code in requested}
    for code, values in requested_code_values.items():
        matching_rows = [
            row
            for row in inventory_rows
            if any(str(row.get(field) or "").strip() in values for field in SUPPLIER_ORDER_CODE_FIELDS)
        ]
        if matching_rows:
            sample = matching_rows[0]
            _supplier_order_debug_log(
                f"[SUPPLIER_ORDER_BULK_READ_CHECK] code={code} present=true "
                f"item_id={sample.get('item_id', '')}"
            )
        else:
            _supplier_order_debug_log(f"[SUPPLIER_ORDER_BULK_READ_CHECK] code={code} present=false")

    for row in inventory_rows:
        is_eligible, reason = supplier_order_eligibility_reason(row)
        if not is_eligible:
            continue
        row_key = _supplier_order_row_key(row)
        for field in SUPPLIER_ORDER_CODE_FIELDS:
            value = str(row.get(field) or "").strip()
            if not value:
                continue
            exact_key = value.lower()
            indexes[(field, "exact")].setdefault(exact_key, {})[row_key] = row
            if value.isdigit():
                canonical_key = normalize_inventory_numeric_code(value).lower()
                indexes[(field, "canonical")].setdefault(canonical_key, {})[row_key] = row

    provider = _norm_supplier(supplier)
    resolved: dict[str, dict[str, Any]] = {}

    for raw_code in requested:
        selected: tuple[str, str, dict[str, Any]] | None = None
        for field, match_mode in SUPPLIER_ORDER_MATCH_LEVELS:
            if match_mode == "canonical" and not raw_code.isdigit():
                continue
            index_key = (
                normalize_inventory_numeric_code(raw_code).lower()
                if match_mode == "canonical"
                else raw_code.lower()
            )
            candidates = indexes[(field, match_mode)].get(index_key, {})
            if not candidates:
                continue
            if len(candidates) > 1:
                candidate_ids = sorted(str(row.get("item_id") or "") for row in candidates.values())
                raise SupplierOrderCodeAmbiguityError(
                    f"Codigo de pedido ambiguo {raw_code!r} en prioridad {match_mode}:{field}: "
                    f"coincide con inventory_items {', '.join(candidate_ids)}."
                )
            selected = (field, match_mode, next(iter(candidates.values())))
            break
        if selected is None:
            fallback = _supplier_order_direct_fallback(session, raw_code, provider)
            if fallback:
                resolved[raw_code] = fallback
            continue
        matched_field, match_mode, row = selected
        _supplier_order_debug_log(
            f"[SUPPLIER_ORDER_ELIGIBILITY] code={raw_code} item_id={row.get('item_id', '')} "
            f"eligible=true reason=eligible"
        )
        resolved[raw_code] = _supplier_order_build_result(raw_code, row, matched_field, match_mode, provider)
    return resolved


def get_supplier_price(session, item_id: int | str, supplier: str) -> dict[str, Any] | None:
    """Return one supplier price through the shared canonical resolver."""
    raw_code = str(item_id or "").strip()
    if not raw_code:
        return None
    result = resolve_supplier_order_inventory_items(session, [raw_code], supplier).get(raw_code)
    if not result or _safe_float(result.get("price")) <= 0:
        return None
    return result

def list_supplier_prices_for_item(session, item_id: int | str) -> list[dict[str, Any]]:
    try:
        item_int = int(str(item_id).strip())
    except Exception:
        return []
    try:
        response = (
            session.client.table("inventory_items")
            .select(INVENTORY_PRICE_COLUMNS)
            .eq("item_id", item_int)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None) or []
        if not rows:
            return []
        row = rows[0]
        result: list[dict[str, Any]] = []
        primary = _safe_float(row.get("primary_supplier_price"))
        pascal = _safe_float(row.get("pascal_price"))
        if primary > 0:
            result.append({"item_id": item_int, "supplier": "Proveedor principal", "price": primary, "currency": "EUR", "source": "inventory_items.primary_supplier_price"})
        if pascal > 0:
            result.append({"item_id": item_int, "supplier": "Pascal", "price": pascal, "currency": "EUR", "source": "inventory_items.pascal_price"})
        return result
    except Exception:
        return []


def diagnose_supplier_price_columns(session, settings: Settings | None = None) -> dict[str, Any]:
    """Diagnose local supplier_prices vs Supabase inventory_items price columns.

    This does not write anything.
    """
    local_rows = read_local_supplier_prices(settings)
    updates = _build_inventory_price_updates(local_rows)
    by_supplier: dict[str, int] = {}
    for row in local_rows:
        by_supplier[row.supplier] = by_supplier.get(row.supplier, 0) + 1

    local_items = sorted(updates.keys())
    existing_ids: set[int] = set()
    cloud_sample: list[dict[str, Any]] = []
    try:
        for i in range(0, len(local_items), 100):
            batch = local_items[i : i + 100]
            response = (
                session.client.table("inventory_items")
                .select("item_id,name,primary_supplier_price,pascal_price,family,subgroup")
                .in_("item_id", batch)
                .execute()
            )
            for row in getattr(response, "data", None) or []:
                try:
                    existing_ids.add(int(row.get("item_id")))
                except Exception:
                    pass
                if len(cloud_sample) < 20:
                    cloud_sample.append(row)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "local_supplier_price_rows": len(local_rows),
            "local_items": len(local_items),
            "by_supplier": by_supplier,
        }

    missing = [int(item_id) for item_id in local_items if int(item_id) not in existing_ids]
    with_primary = 0
    with_pascal = 0
    try:
        response = (
            session.client.table("inventory_items")
            .select("item_id,primary_supplier_price,pascal_price")
            .or_("primary_supplier_price.not.is.null,pascal_price.not.is.null")
            .limit(1000)
            .execute()
        )
        for row in getattr(response, "data", None) or []:
            if row.get("primary_supplier_price") not in (None, ""):
                with_primary += 1
            if row.get("pascal_price") not in (None, ""):
                with_pascal += 1
    except Exception:
        pass

    conflicts = [
        {"item_id": item_id, "conflicts": data["source_row"]["supplier_price_migration"].get("conflicts", [])}
        for item_id, data in updates.items()
        if data["source_row"]["supplier_price_migration"].get("conflicts")
    ]

    return {
        "ok": True,
        "local_supplier_price_rows": len(local_rows),
        "local_items_to_map": len(local_items),
        "local_by_supplier": by_supplier,
        "supabase_matching_items": len(existing_ids),
        "missing_in_supabase_count": len(missing),
        "missing_in_supabase_sample": missing[:30],
        "supabase_with_primary_supplier_price_sample_count": with_primary,
        "supabase_with_pascal_price_sample_count": with_pascal,
        "conflict_count": len(conflicts),
        "conflict_sample": conflicts[:10],
        "cloud_sample": cloud_sample,
        "mapped_update_sample": list(updates.values())[:10],
    }


def diagnose_supplier_price_resolution(session, codes: list[str], supplier: str) -> list[dict[str, Any]]:
    """Diagnose how order line codes resolve to supplier prices."""
    resolved = resolve_supplier_order_inventory_items(session, codes, supplier)
    result: list[dict[str, Any]] = []
    for code in codes:
        price = resolved.get(str(code or "").strip())
        result.append(
            {
                "code": code,
                "supplier": supplier,
                "resolved": bool(price),
                "item_id": price.get("item_id") if price else None,
                "matched_by": price.get("matched_by") if price else None,
                "price": price.get("price") if price else None,
                "column": price.get("column") if price else None,
            }
        )
    return result


# ---------------------------------------------------------------------------
# UI ERP - Gestion visual de precios de proveedor
# ---------------------------------------------------------------------------

def list_supplier_price_inventory_items(session, *, query: str = "", limit: int = 500) -> list[dict[str, Any]]:
    """Lista items con precios proveedor desde inventory_items."""
    limit = max(1, min(int(limit or 500), 1000))
    select_cols = (
        "item_id,name,family,subgroup,materials,size,commercial_status,"
        "primary_supplier_price,pascal_price,heca_reference,woo_sku,updated_at"
    )
    rows: list[dict[str, Any]] = []
    try:
        q = session.client.table("inventory_items").select(select_cols)
        term = str(query or "").strip()
        if term:
            escaped = term.replace("%", "").replace("*", "")
            q = q.or_(
                ",".join(
                    [
                        f"name.ilike.%{escaped}%",
                        f"heca_reference.ilike.%{escaped}%",
                        f"woo_sku.ilike.%{escaped}%",
                    ]
                )
            )
        response = q.order("item_id").limit(limit).execute()
        rows = list(getattr(response, "data", None) or [])
    except Exception:
        rows = []

    term = str(query or "").strip()
    if term and term.isdigit():
        try:
            response = (
                session.client.table("inventory_items")
                .select(select_cols)
                .eq("item_id", int(term))
                .limit(limit)
                .execute()
            )
            exact = getattr(response, "data", None) or []
            by_id = {str(row.get("item_id")): row for row in rows}
            for row in exact:
                by_id[str(row.get("item_id"))] = row
            rows = list(by_id.values())
        except Exception:
            pass

    return rows


def update_supplier_price_inventory_item(
    session,
    item_id: int | str,
    *,
    primary_supplier_price: Any = None,
    pascal_price: Any = None,
    reason: str = "",
) -> dict[str, Any]:
    """Actualiza precios proveedor de un item en inventory_items.

    No toca WooCommerce. No toca stock. Genera snapshot y audit log.
    """
    try:
        item_int = int(str(item_id).strip())
    except Exception:
        raise ValueError("item_id invalido para actualizar precios proveedor.")

    before_resp = (
        session.client.table("inventory_items")
        .select("item_id,name,primary_supplier_price,pascal_price,updated_at")
        .eq("item_id", item_int)
        .limit(1)
        .execute()
    )
    before_rows = getattr(before_resp, "data", None) or []
    if not before_rows:
        raise ValueError(f"No existe inventory_items.item_id={item_int} en Supabase.")
    before = before_rows[0]

    def _price_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if text == "":
            return None
        try:
            number = float(text.replace(",", "."))
        except Exception:
            raise ValueError(f"Precio invalido: {value}")
        if number < 0:
            raise ValueError("El precio proveedor no puede ser negativo.")
        return round(number, 4)

    update_data: dict[str, Any] = {}
    if primary_supplier_price is not None:
        update_data["primary_supplier_price"] = _price_or_none(primary_supplier_price)
    if pascal_price is not None:
        update_data["pascal_price"] = _price_or_none(pascal_price)
    if not update_data:
        raise ValueError("No hay precios para actualizar.")

    operation_id = new_operation_id("supplier_price_update")
    update_data["updated_at"] = _now_iso()

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Precio Proveedores",
                action="update_supplier_prices",
                entity_table="inventory_items",
                entity_id=str(item_int),
                before_data=before,
                after_data=update_data,
                metadata={"reason": reason},
            ),
        )
    except Exception:
        pass

    response = (
        session.client.table("inventory_items")
        .update(update_data)
        .eq("item_id", item_int)
        .execute()
    )
    updated_rows = getattr(response, "data", None) or []

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Precio Proveedores",
                action="update_supplier_prices",
                entity_table="inventory_items",
                entity_id=str(item_int),
                status="success",
                message=f"Precios proveedor actualizados para item {item_int}",
                metadata={
                    "reason": reason,
                    "primary_supplier_price": update_data.get("primary_supplier_price"),
                    "pascal_price": update_data.get("pascal_price"),
                },
            ),
        )
    except Exception:
        pass

    return {
        "operation_id": operation_id,
        "item_id": item_int,
        "before": before,
        "after": updated_rows[0] if updated_rows else update_data,
    }

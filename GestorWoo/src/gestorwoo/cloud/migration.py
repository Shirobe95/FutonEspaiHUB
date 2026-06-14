from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from gestorwoo.cloud.audit import AuditEvent, CloudAuditError, new_operation_id, write_audit_event, write_snapshot, OperationSnapshot
from gestorwoo.cloud.auth import SupabaseAuthError, register_device_seen, sign_in_with_password
from gestorwoo.config import Settings, load_settings


MIGRATION_TABLES = [
    "products",
    "product_variations",
    "inventory_items",
    "supplier_prices",
    "heca_stock",
    "price_change_proposals",
    "supplier_orders",
    "supplier_order_items",
]

TABLE_PK = {
    "products": "woo_id",
    "product_variations": "woo_id",
    "inventory_items": "item_id",
    "supplier_prices": "item_id,supplier",
    "heca_stock": "normalized_code,warehouse_code",
    "price_change_proposals": "local_sqlite_id",
    "supplier_orders": "local_order_id",
    "supplier_order_items": "local_item_id",
}


@dataclass(frozen=True)
class TableMigrationPlan:
    table: str
    local_exists: bool
    local_rows: int = 0
    cloud_rows_visible: int | None = None
    cloud_ready: bool = False
    message: str = ""


def _login_from_console():
    import getpass
    settings = load_settings()
    default_email = settings.hub_user_email or ""
    prompt = f"Email Supabase [{default_email}]: " if default_email else "Email Supabase: "
    typed_email = input(prompt).strip()
    email = typed_email or default_email
    if not email:
        raise SupabaseAuthError("No se indicó email Supabase.")
    print(f"Login Supabase para: {email}")
    password = getpass.getpass("Contraseña Supabase: ")
    session = sign_in_with_password(email, password, settings)
    register_device_seen(session, settings)
    return session, settings


def _sqlite_conn(settings: Settings) -> sqlite3.Connection:
    db_path = settings.db_path
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base SQLite local: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _local_count(conn: sqlite3.Connection, table: str) -> tuple[bool, int]:
    exists = conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None
    if not exists:
        return False, 0
    return True, int(conn.execute(f"select count(*) as c from {table}").fetchone()["c"])


def _cloud_count(session, table: str) -> tuple[bool, int | None, str]:
    try:
        resp = session.client.table(table).select("*", count="exact").limit(1).execute()
        return True, getattr(resp, "count", None), "OK"
    except Exception as exc:
        return False, None, str(exc)


def collect_migration_preview(session, settings: Settings | None = None) -> list[TableMigrationPlan]:
    settings = settings or load_settings()
    plans: list[TableMigrationPlan] = []
    with _sqlite_conn(settings) as conn:
        for table in MIGRATION_TABLES:
            local_exists, local_rows = _local_count(conn, table)
            cloud_ready, cloud_rows, msg = _cloud_count(session, table)
            plans.append(TableMigrationPlan(table, local_exists, local_rows, cloud_rows, cloud_ready, msg))
    return plans


def format_migration_preview(plans: list[TableMigrationPlan], settings: Settings, role: str | None) -> str:
    total = sum(p.local_rows for p in plans if p.local_exists)
    lines = [
        "PREVIEW MIGRACIÓN SQLITE → SUPABASE",
        "=" * 46,
        f"Modo HUB: {settings.app_mode}",
        f"Rol sesión: {role}",
        f"SQLite local: {settings.db_path}",
        "",
        "TABLAS",
        "-" * 38,
    ]
    for p in plans:
        local = f"local: {p.local_rows}" if p.local_exists else "local: NO EXISTE"
        cloud = f"cloud visibles: {p.cloud_rows_visible}" if p.cloud_ready else f"cloud ERROR: {p.message}"
        action = "crear/actualizar" if p.local_exists and p.local_rows else "sin filas"
        lines.append(f"{p.table}: {local} · {cloud} · acción: {action}")
    lines.extend([
        "",
        f"Total filas candidatas: {total}",
        "",
        "Nada se ha subido todavía.",
        "Para ejecutar la migración real:",
        "python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR",
        "",
        "Notas:",
        "- No toca WooCommerce.",
        "- Solo admin debe ejecutar la migración.",
        "- price_change_proposals usa local_sqlite_id para no duplicar filas.",
    ])
    return "\n".join(lines)


def _json_loads_maybe(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return default


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def _dt(value: Any) -> Any:
    # Postgres acepta timestamps comunes; mantenemos None si no hay valor.
    return value or None


def _bool_int(value: Any) -> bool:
    return bool(value) if value is not None else False


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # Supabase/PostgREST tolera None. Aseguramos JSON serializable.
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _iter_rows(conn: sqlite3.Connection, table: str) -> Iterable[dict[str, Any]]:
    exists, _ = _local_count(conn, table)
    if not exists:
        return []
    return (_row_dict(r) for r in conn.execute(f"select * from {table}"))


def _map_product(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "woo_id": r.get("woo_id"),
        "name": r.get("name") or "(sin nombre)",
        "sku": r.get("sku"),
        "type": r.get("type"),
        "status": r.get("status"),
        "regular_price": r.get("regular_price"),
        "sale_price": r.get("sale_price"),
        "price": r.get("price"),
        "stock_status": r.get("stock_status"),
        "stock_quantity": r.get("stock_quantity"),
        "categories_json": _json_loads_maybe(r.get("categories_json"), []),
        "raw_json": _json_loads_maybe(r.get("raw_json"), {}),
        "synced_at": _dt(r.get("synced_at")),
        "updated_at": now,
        "updated_by": session.user_id,
    })


def _map_variation(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "woo_id": r.get("woo_id"),
        "parent_woo_id": r.get("parent_woo_id"),
        "parent_name": r.get("parent_name") or "(sin padre)",
        "sku": r.get("sku"),
        "status": r.get("status"),
        "regular_price": r.get("regular_price"),
        "sale_price": r.get("sale_price"),
        "price": r.get("price"),
        "stock_status": r.get("stock_status"),
        "stock_quantity": r.get("stock_quantity"),
        "attributes_json": _json_loads_maybe(r.get("attributes_json"), []),
        "attributes_label": r.get("attributes_label"),
        "raw_json": _json_loads_maybe(r.get("raw_json"), {}),
        "synced_at": _dt(r.get("synced_at")),
        "updated_at": now,
        "updated_by": session.user_id,
    })


def _map_inventory(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    source_row = dict(r)
    return _clean_payload({
        "item_id": r.get("item_id"),
        "name": r.get("name") or "(sin nombre)",
        "cubic_meters": r.get("cubic_meters"),
        "rotation_c": r.get("rotation_c"),
        "packages": r.get("packages"),
        "primary_supplier_price": r.get("primary_supplier_price"),
        "pascal_price": r.get("pascal_price"),
        "source": r.get("source"),
        "family": r.get("family"),
        "subgroup": r.get("subgroup"),
        "size": r.get("size"),
        "materials": r.get("materials"),
        "commercial_status": r.get("commercial_status") or "Normal",
        "is_pack": _bool_int(r.get("is_pack")),
        "store_stock": r.get("store_stock"),
        "warehouse_stock": r.get("warehouse_stock"),
        "heca_reference": r.get("heca_reference"),
        "notes": r.get("notes"),
        "woo_item_kind": r.get("woo_item_kind"),
        "woo_id": r.get("woo_id"),
        "woo_parent_id": r.get("woo_parent_id"),
        "woo_sku": r.get("woo_sku"),
        "woo_name": r.get("woo_name"),
        "woo_type": r.get("woo_type"),
        "woo_price": r.get("woo_price"),
        "woo_categories": r.get("woo_categories"),
        "woo_link_status": r.get("woo_link_status") or "Sin enlazar",
        "woo_link_notes": r.get("woo_link_notes"),
        "woo_synced_at": _dt(r.get("woo_synced_at")),
        "order_calculated_price": r.get("order_calculated_price"),
        "supplier_order_qty": r.get("supplier_order_qty"),
        "supplier_order_provider": r.get("supplier_order_provider"),
        "supplier_order_file": r.get("supplier_order_file"),
        "supplier_order_updated_at": _dt(r.get("supplier_order_updated_at")),
        "weighted_average_cost": r.get("weighted_average_cost"),
        "weighted_average_cost_updated_at": _dt(r.get("weighted_average_cost_updated_at")),
        "source_row": source_row,
        "created_at": _dt(r.get("created_at")) or now,
        "updated_at": now,
        "updated_by": session.user_id,
    })


def _map_supplier_price(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "item_id": r.get("item_id"),
        "supplier": r.get("supplier") or "(sin proveedor)",
        "price": r.get("price"),
        "currency": r.get("currency") or "EUR",
        "source": r.get("source"),
        "updated_at": now,
        "updated_by": session.user_id,
    })


def _map_heca_stock(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "normalized_code": str(r.get("normalized_code") or r.get("item_code") or ""),
        "warehouse_code": r.get("warehouse_code") or 0,
        "item_code": str(r.get("item_code") or ""),
        "quantity": r.get("quantity") or 0,
        "quantity_requested": r.get("quantity_requested") or 0,
        "quantity_reserved": r.get("quantity_reserved") or 0,
        "quantity_supplier_ordered": r.get("quantity_supplier_ordered") or 0,
        "imported_at": _dt(r.get("imported_at")) or now,
        "updated_by": session.user_id,
    })


def _map_price_proposal(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "local_sqlite_id": r.get("id"),
        "local_id": r.get("id"),
        "item_kind": r.get("item_kind") or "product",
        "item_woo_id": r.get("item_woo_id"),
        "name": r.get("name") or "(sin nombre)",
        "old_price": r.get("old_price"),
        "new_price": r.get("new_price"),
        "delta": r.get("delta"),
        "notes": r.get("notes"),
        "status": (r.get("status") or "pending") if (r.get("status") or "pending") in {"pending","approved","rejected","published","error","cancelled"} else "pending",
        "created_by": session.user_id,
        "created_at": _dt(r.get("created_at")) or now,
        "published_at": _dt(r.get("published_at")),
        "error_message": r.get("error_message"),
        "source_row": {"local_sqlite_id": r.get("id"), "migrated_from": "sqlite", "migrated_at": now},
    })


def _map_supplier_order(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    return _clean_payload({
        "local_order_id": r.get("order_id"),
        "provider": r.get("provider") or "(sin proveedor)",
        "order_file": r.get("order_file"),
        "status": r.get("status") or "Pendiente",
        "total_items": r.get("total_items") or 0,
        "total_cost": r.get("total_cost") or 0,
        "notes": r.get("notes"),
        "created_by": session.user_id,
        "created_at": _dt(r.get("created_at")) or now,
        "updated_at": _dt(r.get("updated_at")) or now,
        "source_row": {"local_sqlite_id": r.get("order_id"), "migrated_from": "sqlite", "migrated_at": now},
    })


def _map_supplier_order_item(r: dict[str, Any], session, now: str) -> dict[str, Any]:
    # En v9 no intentamos reconstruir FK UUID de order_id para tablas vacías actuales.
    # Guardamos el id local en source_row y local_item_id para futura reconciliación.
    return _clean_payload({
        "local_item_id": r.get("id"),
        "local_id": r.get("id"),
        "item_id": r.get("item_id"),
        "item_code": r.get("item_code"),
        "item_name": r.get("item_name") or "(sin nombre)",
        "quantity_ordered": r.get("quantity_ordered") or 0,
        "quantity_received": r.get("quantity_received") or 0,
        "unit_cost": r.get("unit_cost") or 0,
        "line_cost": r.get("line_cost") or 0,
        "updated_at": _dt(r.get("updated_at")) or now,
        "source_row": {"local_sqlite_id": r.get("id"), "local_order_id": r.get("order_id"), "migrated_from": "sqlite", "migrated_at": now},
    })


MAPPERS = {
    "products": _map_product,
    "product_variations": _map_variation,
    "inventory_items": _map_inventory,
    "supplier_prices": _map_supplier_price,
    "heca_stock": _map_heca_stock,
    "price_change_proposals": _map_price_proposal,
    "supplier_orders": _map_supplier_order,
    "supplier_order_items": _map_supplier_order_item,
}


def _batch(seq: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _upsert_batch(session, table: str, rows: list[dict[str, Any]], batch_size: int = 100) -> int:
    if not rows:
        return 0
    total = 0
    on_conflict = TABLE_PK.get(table)
    for part in _batch(rows, batch_size):
        q = session.client.table(table).upsert(part, on_conflict=on_conflict)
        try:
            q.execute()
        except Exception as exc:
            msg = str(exc)
            if "no unique or exclusion constraint matching the ON CONFLICT specification" in msg:
                raise CloudAuditError(
                    f"La tabla cloud '{table}' no tiene índice/constraint único válido para on_conflict={on_conflict}. "
                    "Ejecuta docs/supabase/15_fix_on_conflict_migracion_v9_1.sql y repite la migración."
                ) from exc
            raise
        total += len(part)
    return total


def execute_sqlite_to_supabase_migration(session, settings: Settings, *, tables: list[str] | None = None) -> dict[str, Any]:
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede ejecutar la migración SQLite → Supabase.")
    selected = tables or MIGRATION_TABLES
    invalid = [t for t in selected if t not in MIGRATION_TABLES]
    if invalid:
        raise CloudAuditError(f"Tablas inválidas para migración: {', '.join(invalid)}")

    operation_id = new_operation_id("MIGRATE")
    started_at = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {"operation_id": operation_id, "tables": {}, "started_at": started_at}

    write_audit_event(session, AuditEvent(
        operation_id=operation_id,
        module="migration",
        action="sqlite_to_supabase_started",
        status="STARTED",
        severity="INFO",
        entity_type="migration",
        entity_id="sqlite_to_supabase",
        before_data={"db_path": str(settings.db_path), "tables": selected},
        after_data=None,
        message="Inicio de migración controlada SQLite → Supabase. No toca WooCommerce.",
    ), settings)

    try:
        with _sqlite_conn(settings) as conn:
            for table in selected:
                exists, count = _local_count(conn, table)
                if not exists or count == 0:
                    result["tables"][table] = {"local_rows": count, "uploaded": 0, "skipped": not exists}
                    continue
                mapper = MAPPERS[table]
                now = datetime.now(timezone.utc).isoformat()
                rows = [mapper(r, session, now) for r in _iter_rows(conn, table)]
                uploaded = _upsert_batch(session, table, rows)
                result["tables"][table] = {"local_rows": count, "uploaded": uploaded, "skipped": False}
                print(f"{table}: subidas/actualizadas {uploaded}/{count}")

        # Verificación de conteos visibles tras migrar.
        verify: dict[str, Any] = {}
        for table in selected:
            ok, cloud_rows, msg = _cloud_count(session, table)
            verify[table] = {"ok": ok, "cloud_rows_visible": cloud_rows, "message": msg}
        result["verify"] = verify
        result["finished_at"] = datetime.now(timezone.utc).isoformat()

        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="migration",
            action="sqlite_to_supabase_finished",
            status="OK",
            severity="INFO",
            entity_type="migration",
            entity_id="sqlite_to_supabase",
            before_data=None,
            after_data=result,
            message="Migración SQLite → Supabase finalizada correctamente. WooCommerce no fue tocado.",
        ), settings)
        return result
    except Exception as exc:
        result["error"] = str(exc)
        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="migration",
            action="sqlite_to_supabase_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="migration",
            entity_id="sqlite_to_supabase",
            before_data=None,
            after_data=result,
            message="Falló la migración SQLite → Supabase.",
            error_detail=str(exc),
        ), settings)
        raise


def run_migration_preview() -> int:
    try:
        session, settings = _login_from_console()
        plans = collect_migration_preview(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_migration_preview(plans, settings, session.role))
    return 0


def run_migration_execute(confirm: str | None = None, tables_csv: str | None = None) -> int:
    if confirm != "MIGRAR":
        print("ERROR: migración no ejecutada.")
        print("Debes usar confirmación explícita:")
        print("python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR")
        return 2
    try:
        session, settings = _login_from_console()
        if (session.role or "").lower() != "admin":
            print("ERROR: solo admin puede ejecutar la migración.")
            return 2
        selected = None
        if tables_csv:
            selected = [t.strip() for t in tables_csv.split(",") if t.strip()]
        result = execute_sqlite_to_supabase_migration(session, settings, tables=selected)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("\nMIGRACIÓN FINALIZADA")
    print("=" * 28)
    print(f"operation_id: {result['operation_id']}")
    for table, info in result.get("tables", {}).items():
        print(f"{table}: local={info.get('local_rows')} · subidas/actualizadas={info.get('uploaded')} · skipped={info.get('skipped')}")
    print("\nVerificación cloud visible:")
    for table, info in result.get("verify", {}).items():
        print(f"{table}: {info.get('cloud_rows_visible')} filas visibles · ok={info.get('ok')}")
    print("\nWooCommerce no fue tocado.")
    return 0

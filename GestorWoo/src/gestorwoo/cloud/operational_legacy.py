from __future__ import annotations

import getpass
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from gestorwoo.cloud.audit import (
    AuditEvent,
    CloudAuditError,
    OperationSnapshot,
    new_operation_id,
    write_audit_event,
    write_snapshot,
)
from gestorwoo.cloud.auth import SupabaseAuthError, register_device_seen, sign_in_with_password
from gestorwoo.cloud.locks import acquire_system_lock, release_system_lock
from futonhub.cloud.services.prices import (
    PRICE_PROPOSAL_STATUSES,
    current_price_from_item as service_current_price_from_item,
    format_price_safety_for_search as service_format_price_safety_for_search,
    money_or_none as service_money_or_none,
    price_safety_preview as service_price_safety_preview,
    product_type as service_product_type,
)
from futonhub.cloud.services import price_proposals as price_proposal_service
from futonhub.cloud.services import inventory as inventory_service
from futonhub.cloud.services import woocommerce_publish as woo_publish_service
from futonhub.cloud.services.rollback import (
    ROLLBACK_ENTITY_SPECS,
    rollback_target_from_snapshot as service_rollback_target_from_snapshot,
    rollback_update_payload as service_rollback_update_payload,
    short_json_diff as service_short_json_diff,
)
from gestorwoo.config import Settings, load_settings
from gestorwoo.woocommerce import WooCommerceClient, WooCommerceError


OPERATIONAL_TABLES = [
    "products",
    "product_variations",
    "inventory_items",
    "supplier_prices",
    "heca_stock",
    "price_change_proposals",
    "supplier_orders",
    "supplier_order_items",
    "business_constants",
]

LOCAL_MIGRATION_TABLES = [
    "products",
    "product_variations",
    "inventory_items",
    "supplier_prices",
    "heca_stock",
    "price_change_proposals",
    "supplier_orders",
    "supplier_order_items",
]


@dataclass(frozen=True)
class LocalTableInfo:
    name: str
    exists: bool
    rows: int | None = None
    columns: list[str] | None = None
    error: str | None = None


def _login_from_console():
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


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}


def inspect_local_sqlite(settings: Settings | None = None) -> list[LocalTableInfo]:
    settings = settings or load_settings()
    db_path = settings.db_path
    result: list[LocalTableInfo] = []
    if not db_path.exists():
        return [
            LocalTableInfo(
                name="gestorwoo.sqlite3",
                exists=False,
                error=f"No existe la base local: {db_path}",
            )
        ]

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        return [
            LocalTableInfo(
                name="gestorwoo.sqlite3",
                exists=False,
                error=f"No se pudo abrir SQLite local: {exc}",
            )
        ]

    try:
        existing = {
            row["name"]
            for row in conn.execute("select name from sqlite_master where type='table'")
        }
        for table in LOCAL_MIGRATION_TABLES:
            if table not in existing:
                result.append(LocalTableInfo(name=table, exists=False))
                continue
            try:
                rows = int(conn.execute(f"select count(*) as total from {table}").fetchone()["total"])
                columns = [r["name"] for r in conn.execute(f"pragma table_info({table})").fetchall()]
                result.append(LocalTableInfo(name=table, exists=True, rows=rows, columns=columns))
            except Exception as exc:
                result.append(LocalTableInfo(name=table, exists=True, error=str(exc)))
    finally:
        conn.close()

    return result


def format_local_sqlite_dry_run(infos: list[LocalTableInfo]) -> str:
    lines = [
        "DRY-RUN MIGRACIÓN SQLITE → SUPABASE",
        "=" * 44,
        "No sube datos. Solo revisa qué hay en la base local y qué tablas serán candidatas.",
        "",
    ]
    for info in infos:
        if not info.exists:
            lines.append(f"{info.name}: NO EXISTE" + (f" · {info.error}" if info.error else ""))
            continue
        if info.error:
            lines.append(f"{info.name}: ERROR · {info.error}")
            continue
        col_count = len(info.columns or [])
        lines.append(f"{info.name}: OK · filas locales: {info.rows} · columnas: {col_count}")

    total_rows = sum((info.rows or 0) for info in infos if info.exists and not info.error)
    lines.extend([
        "",
        f"Total filas candidatas aproximadas: {total_rows}",
        "",
        "Siguiente fase futura:",
        "1. Validar mapeo de columnas.",
        "2. Hacer backup lógico.",
        "3. Subir por lotes.",
        "4. Comparar conteos Supabase vs SQLite.",
        "5. Activar lectura online en módulos concretos.",
    ])
    return "\n".join(lines)


def collect_operational_cloud_status(session) -> str:
    settings = load_settings()
    lines = [
        "ESTADO OPERATIVO SUPABASE FUTONHUB",
        "=" * 42,
        f"Usuario: {session.email}",
        f"Rol cloud: {session.role}",
        "",
        "TABLAS OPERATIVAS",
        "-" * 34,
    ]
    for table in OPERATIONAL_TABLES:
        try:
            response = session.client.table(table).select("*", count="exact").limit(1).execute()
            count = getattr(response, "count", None)
            lines.append(f"{table}: OK" + (f" · filas visibles: {count}" if count is not None else ""))
        except Exception as exc:
            lines.append(f"{table}: ERROR · {exc}")

    try:
        perms = (
            session.client.table("role_permissions")
            .select("module,can_view,can_create,can_update,can_delete,can_execute")
            .eq("role", session.role or "worker")
            .order("module")
            .execute()
        )
        data = getattr(perms, "data", None) or []
        lines.extend(["", f"PERMISOS OPERATIVOS VISIBLES PARA {session.role}", "-" * 34])
        for row in data:
            module = row.get("module")
            if module in {
                "products", "product_variations", "inventory", "supplier_prices", "heca_stock",
                "price_proposals", "orders", "orders_cost", "cost", "cost_pedido",
                "business_constants", "woocommerce", "woocommerce_publish", "logs", "backups",
                "restore", "security", "users", "settings", "migrations",
            }:
                lines.append(
                    f"{module}: ver={row.get('can_view')} · crear={row.get('can_create')} · "
                    f"editar={row.get('can_update')} · ejecutar={row.get('can_execute')}"
                )
    except Exception as exc:
        lines.extend(["", f"No se pudieron leer permisos operativos: {exc}"])
    lines.extend(["", "HARDENING V13.1", "-" * 34])
    if (session.role or "").lower() == "admin":
        lock_key = f"diagnostic:hardening:{settings.machine_name}"
        try:
            acquire_system_lock(
                session,
                lock_key,
                details="Diagnostico hardening v13.1",
                ttl_minutes=2,
                settings=settings,
            )
            release_system_lock(session, lock_key, status="released")
            lines.append("Locks online RPC: OK")
        except Exception as exc:
            lines.append(f"Locks online RPC: ERROR · {exc}")
    else:
        lines.append("Locks online RPC: omitido; solo admin puede probar locks criticos.")
    return "\n".join(lines)


def test_business_constant_change(session, settings: Settings | None = None) -> dict[str, Any]:
    """Crea/actualiza una constante de prueba con snapshot + audit_log.

    No afecta al cálculo real: usa una clave TEST_*. Sirve para validar que un
    usuario operativo puede escribir datos, y que la caja negra registra detrás.
    """
    settings = settings or load_settings()
    key = "TEST_FACTOR_SEGURIDAD"
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("CONSTTEST")

    try:
        before_resp = session.client.table("business_constants").select("*").eq("key", key).limit(1).execute()
        before_rows = getattr(before_resp, "data", None) or []
        before = before_rows[0] if before_rows else None

        previous_value = None
        if before is not None:
            previous_value = before.get("value")
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="business_constants",
                action="test_update_constant",
                entity_type="business_constant",
                entity_id=key,
                before_data=_json_safe(before),
                reason="Prueba segura v7: snapshot antes de cambiar constante TEST_*.",
            )
            write_snapshot(session, snapshot)

        new_value = {
            "test_value": now,
            "previous": previous_value,
            "machine": settings.machine_name,
            "role": session.role or settings.sync_role,
        }
        payload = {
            "key": key,
            "value": new_value,
            "value_type": "json",
            "module": "diagnostic",
            "description": "Constante de prueba v7. No afecta cálculos reales.",
            "updated_by": session.user_id,
        }

        if before is None:
            write_resp = session.client.table("business_constants").insert(payload).execute()
            action = "test_create_constant"
        else:
            write_resp = session.client.table("business_constants").update(payload).eq("key", key).execute()
            action = "test_update_constant"

        written = (getattr(write_resp, "data", None) or [payload])[0]
        event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="business_constant",
            entity_id=key,
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message="Prueba operativa v7 sobre business_constants registrada correctamente.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "before": before, "after": written, "action": action}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action="test_constant_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="business_constant",
            entity_id=key,
            before_data=None,
            after_data=None,
            message="Falló la prueba operativa v7 sobre business_constants.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def test_worker_feedback_constant_change(session, settings: Settings | None = None) -> dict[str, Any]:
    """Prueba pequeña de trabajo conjunto con una constante TEST_* reversible.

    Sirve para entrar como worker, modificar algo operativo sin tocar inventario real,
    y que luego el admin vea audit_log + snapshot + valor actualizado en Supabase.
    """
    settings = settings or load_settings()
    key = "TEST_WORKER_FEEDBACK"
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("WORKERTEST")

    try:
        before_resp = session.client.table("business_constants").select("*").eq("key", key).limit(1).execute()
        before_rows = getattr(before_resp, "data", None) or []
        before = before_rows[0] if before_rows else None

        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="business_constants",
                action="worker_feedback_update_constant",
                entity_type="business_constant",
                entity_id=key,
                before_data=_json_safe(before),
                reason="Prueba worker v8: snapshot antes de actualizar constante TEST_WORKER_FEEDBACK.",
            )
            write_snapshot(session, snapshot)

        new_value = {
            "test_name": "worker_feedback",
            "updated_at": now,
            "updated_by_email": session.email,
            "role": session.role or settings.sync_role,
            "machine": settings.machine_name,
            "note": "Dato de prueba reversible. No afecta inventario, pedidos ni WooCommerce.",
        }
        payload = {
            "key": key,
            "value": new_value,
            "value_type": "json",
            "module": "worker_feedback_test",
            "description": "Constante temporal para probar trabajo worker + auditoría admin. Se puede borrar.",
            "updated_by": session.user_id,
        }

        if before is None:
            write_resp = session.client.table("business_constants").insert(payload).execute()
            action = "worker_feedback_create_constant"
        else:
            write_resp = session.client.table("business_constants").update(payload).eq("key", key).execute()
            action = "worker_feedback_update_constant"

        written = (getattr(write_resp, "data", None) or [payload])[0]
        event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="business_constant",
            entity_id=key,
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message="Prueba real v8: usuario operativo modificó TEST_WORKER_FEEDBACK correctamente.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "before": before, "after": written, "action": action, "key": key}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action="worker_feedback_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="business_constant",
            entity_id=key,
            before_data=None,
            after_data=None,
            message="Falló la prueba real v8 de trabajo worker sobre business_constants.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def clean_worker_feedback_constant(session, settings: Settings | None = None) -> dict[str, Any]:
    """Borra TEST_WORKER_FEEDBACK y deja rastro. Solo debe ejecutarlo admin."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede limpiar la prueba worker.")

    key = "TEST_WORKER_FEEDBACK"
    operation_id = new_operation_id("CLEANWORKERTEST")
    try:
        before_resp = session.client.table("business_constants").select("*").eq("key", key).limit(1).execute()
        before_rows = getattr(before_resp, "data", None) or []
        before = before_rows[0] if before_rows else None

        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="business_constants",
                action="admin_clean_worker_feedback_constant",
                entity_type="business_constant",
                entity_id=key,
                before_data=_json_safe(before),
                reason="Limpieza admin v8: snapshot antes de borrar constante de prueba worker.",
            )
            write_snapshot(session, snapshot)
            session.client.table("business_constants").delete().eq("key", key).execute()
            message = "Admin borró TEST_WORKER_FEEDBACK tras prueba worker."
            status = "OK"
        else:
            message = "No había TEST_WORKER_FEEDBACK para borrar."
            status = "OK"

        event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action="admin_clean_worker_feedback_constant",
            status=status,
            severity="INFO",
            entity_type="business_constant",
            entity_id=key,
            before_data=_json_safe(before),
            after_data={"deleted": before is not None},
            message=message,
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "deleted": before is not None, "key": key}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="business_constants",
            action="admin_clean_worker_feedback_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="business_constant",
            entity_id=key,
            message="Falló la limpieza de TEST_WORKER_FEEDBACK.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise



def _fetch_simulated_order(session, order_file: str = "TEST_WORKER_ORDER") -> dict[str, Any] | None:
    """Devuelve un pedido simulado con sus líneas, o None si no existe."""
    resp = (
        session.client.table("supplier_orders")
        .select("*")
        .eq("order_file", order_file)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    order = rows[0]
    order_id = order.get("order_id")
    items_resp = (
        session.client.table("supplier_order_items")
        .select("*")
        .eq("order_id", order_id)
        .order("item_name")
        .execute()
    )
    order["items"] = getattr(items_resp, "data", None) or []
    return order


def test_worker_simulated_order(session, settings: Settings | None = None) -> dict[str, Any]:
    """Crea/actualiza un pedido simulado reversible para validar trabajo worker.

    No toca inventario real ni WooCommerce. Usa supplier_orders/supplier_order_items
    con order_file TEST_WORKER_ORDER y source_row marcado como test.
    """
    settings = settings or load_settings()
    order_file = "TEST_WORKER_ORDER"
    provider = "TEST_WORKER"
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("WORKERORDER")

    try:
        before = _fetch_simulated_order(session, order_file)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="supplier_orders",
                action="worker_simulated_order_update",
                entity_type="supplier_order",
                entity_id=str(before.get("order_id") or order_file),
                before_data=_json_safe(before),
                reason="Prueba worker v8.5: snapshot antes de actualizar pedido simulado.",
            )
            write_snapshot(session, snapshot)

        total_items = 3
        unit_cost = 12.5
        line_cost = total_items * unit_cost
        order_payload = {
            "provider": provider,
            "order_file": order_file,
            "status": "Simulado",
            "total_items": total_items,
            "total_cost": line_cost,
            "notes": "Pedido simulado creado desde HUB para probar flujo worker/admin. No usar como pedido real.",
            "created_by": session.user_id,
            "updated_at": now,
            "source_row": {
                "test": True,
                "test_name": "worker_simulated_order",
                "updated_at": now,
                "updated_by_email": session.email,
                "role": session.role or settings.sync_role,
                "machine": settings.machine_name,
            },
        }

        if before is None:
            order_resp = session.client.table("supplier_orders").insert(order_payload).execute()
            order = (getattr(order_resp, "data", None) or [order_payload])[0]
            action = "worker_simulated_order_create"
        else:
            order_id = before.get("order_id")
            order_resp = (
                session.client.table("supplier_orders")
                .update(order_payload)
                .eq("order_id", order_id)
                .execute()
            )
            order = (getattr(order_resp, "data", None) or [{**before, **order_payload}])[0]
            action = "worker_simulated_order_update"

        order_id = order.get("order_id")
        # Limpiar/reponer solo líneas de este pedido de test. La FK cascade no se usa aquí.
        if before is not None and order_id:
            try:
                session.client.table("supplier_order_items").delete().eq("order_id", order_id).execute()
            except Exception:
                # Algunas políticas no permiten DELETE directo. Marcamos nueva línea de test igualmente.
                pass

        item_payload = {
            "order_id": order_id,
            "local_id": None,
            "item_id": None,
            "item_code": "TEST-SKU-001",
            "item_name": "Artículo simulado worker",
            "quantity_ordered": total_items,
            "quantity_received": 0,
            "unit_cost": unit_cost,
            "line_cost": line_cost,
            "updated_at": now,
            "source_row": {
                "test": True,
                "operation_id": operation_id,
                "note": "Línea simulada. No inventario real.",
            },
        }
        item_resp = session.client.table("supplier_order_items").insert(item_payload).execute()
        item = (getattr(item_resp, "data", None) or [item_payload])[0]

        after = _json_safe({**order, "items": [item]})
        event = AuditEvent(
            operation_id=operation_id,
            module="supplier_orders",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="supplier_order",
            entity_id=str(order_id or order_file),
            before_data=_json_safe(before),
            after_data=after,
            message="Prueba real v8.5: usuario operativo creó/actualizó un pedido simulado correctamente.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "action": action, "order_id": order_id, "order_file": order_file, "before": before, "after": after}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="supplier_orders",
            action="worker_simulated_order_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="supplier_order",
            entity_id=order_file,
            before_data=None,
            after_data=None,
            message="Falló la prueba v8.5 de pedido simulado worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def clean_worker_simulated_order(session, settings: Settings | None = None) -> dict[str, Any]:
    """Limpia TEST_WORKER_ORDER. Intenta RPC admin si existe, si no marca cancelado."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede limpiar el pedido simulado worker.")

    order_file = "TEST_WORKER_ORDER"
    operation_id = new_operation_id("CLEANWORKERORDER")
    before = None
    try:
        before = _fetch_simulated_order(session, order_file)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="supplier_orders",
                action="admin_clean_worker_simulated_order",
                entity_type="supplier_order",
                entity_id=str(before.get("order_id") or order_file),
                before_data=_json_safe(before),
                reason="Limpieza admin v8.5: snapshot antes de limpiar pedido simulado worker.",
            )
            write_snapshot(session, snapshot)

        deleted = False
        marked_cancelled = False
        if before is not None:
            order_id = before.get("order_id")
            try:
                resp = session.client.rpc(
                    "futonhub_clean_worker_simulated_order",
                    {"p_user_id": session.user_id, "p_order_file": order_file},
                ).execute()
                data = getattr(resp, "data", None)
                deleted = bool(data if isinstance(data, bool) else (data or False))
            except Exception:
                # Fallback sin SQL v8.5: no borra, pero lo deja claramente cancelado.
                session.client.table("supplier_orders").update({
                    "status": "Cancelado",
                    "notes": "Pedido simulado marcado como cancelado por limpieza admin. Puede borrarse con RPC v8.5.",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("order_id", order_id).execute()
                marked_cancelled = True

        event = AuditEvent(
            operation_id=operation_id,
            module="supplier_orders",
            action="admin_clean_worker_simulated_order",
            status="OK",
            severity="INFO",
            entity_type="supplier_order",
            entity_id=order_file,
            before_data=_json_safe(before),
            after_data={"deleted": deleted, "marked_cancelled": marked_cancelled},
            message="Admin limpió o canceló el pedido simulado worker.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "deleted": deleted, "marked_cancelled": marked_cancelled, "order_file": order_file}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="supplier_orders",
            action="admin_clean_worker_simulated_order_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="supplier_order",
            entity_id=order_file,
            before_data=_json_safe(before),
            after_data=None,
            message="Falló la limpieza del pedido simulado worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise



TEST_PRICE_PROPOSAL_WOO_ID = -990001
TEST_PRICE_PROPOSAL_NAME = "TEST_WORKER_PRICE_PROPOSAL"


def _fetch_simulated_price_proposal(session) -> dict[str, Any] | None:
    """Devuelve la propuesta de precio simulada, o None si no existe."""
    resp = (
        session.client.table("price_change_proposals")
        .select("*")
        .eq("item_woo_id", TEST_PRICE_PROPOSAL_WOO_ID)
        .eq("item_kind", "product")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def test_worker_simulated_price_proposal(session, settings: Settings | None = None) -> dict[str, Any]:
    """Crea/actualiza una propuesta de precio TEST_* reversible.

    Valida el flujo real de tienda antes de tocar precios reales:
    - worker crea/edita propuesta
    - Supabase guarda la propuesta
    - caja negra registra audit_log y snapshot
    - no publica en WooCommerce
    """
    settings = settings or load_settings()
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("WORKERPRICE")

    try:
        before = _fetch_simulated_price_proposal(session)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="price_change_proposals",
                action="worker_simulated_price_proposal_update",
                entity_type="price_change_proposal",
                entity_id=str(before.get("id") or TEST_PRICE_PROPOSAL_WOO_ID),
                before_data=_json_safe(before),
                reason="Prueba worker v8.7: snapshot antes de actualizar propuesta de precio TEST_*.",
            )
            write_snapshot(session, snapshot)

        if before is None:
            old_price = 100.0
            new_price = 115.0
        else:
            old_price = float(before.get("new_price") or before.get("old_price") or 100)
            new_price = old_price + 5.0
        delta = new_price - old_price

        payload = {
            "local_id": TEST_PRICE_PROPOSAL_WOO_ID,
            "item_kind": "product",
            "item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID,
            "name": TEST_PRICE_PROPOSAL_NAME,
            "old_price": old_price,
            "new_price": new_price,
            "delta": delta,
            "notes": "Propuesta de precio simulada para validar worker/admin. No publicar en WooCommerce.",
            "status": "pending",
            "created_by": session.user_id,
            "source_row": {
                "test": True,
                "test_name": "worker_simulated_price_proposal",
                "operation_id": operation_id,
                "updated_at": now,
                "updated_by_email": session.email,
                "role": session.role or settings.sync_role,
                "machine": settings.machine_name,
                "note": "Prueba reversible. No toca WooCommerce ni precios reales.",
            },
        }

        if before is None:
            write_resp = session.client.table("price_change_proposals").insert(payload).execute()
            action = "worker_simulated_price_proposal_create"
        else:
            write_resp = (
                session.client.table("price_change_proposals")
                .update(payload)
                .eq("id", before.get("id"))
                .execute()
            )
            action = "worker_simulated_price_proposal_update"

        written = (getattr(write_resp, "data", None) or [payload])[0]
        event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(written.get("id") or TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message="Prueba real v8.7: usuario operativo creó/actualizó propuesta de precio simulada correctamente.",
        )
        write_audit_event(session, event, settings)
        return {
            "operation_id": operation_id,
            "action": action,
            "proposal_id": written.get("id"),
            "item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID,
            "name": TEST_PRICE_PROPOSAL_NAME,
            "old_price": old_price,
            "new_price": new_price,
            "delta": delta,
            "before": before,
            "after": written,
        }
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action="worker_simulated_price_proposal_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="price_change_proposal",
            entity_id=str(TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=None,
            after_data=None,
            message="Falló la prueba v8.7 de propuesta de precio simulada worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def clean_worker_simulated_price_proposal(session, settings: Settings | None = None) -> dict[str, Any]:
    """Limpia TEST_WORKER_PRICE_PROPOSAL. Solo admin."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede limpiar la propuesta de precio simulada worker.")

    operation_id = new_operation_id("CLEANWORKERPRICE")
    before = None
    try:
        before = _fetch_simulated_price_proposal(session)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="price_change_proposals",
                action="admin_clean_worker_simulated_price_proposal",
                entity_type="price_change_proposal",
                entity_id=str(before.get("id") or TEST_PRICE_PROPOSAL_WOO_ID),
                before_data=_json_safe(before),
                reason="Limpieza admin v8.7: snapshot antes de limpiar propuesta de precio simulada worker.",
            )
            write_snapshot(session, snapshot)

        deleted = False
        marked_cancelled = False
        if before is not None:
            try:
                resp = session.client.rpc(
                    "futonhub_clean_worker_simulated_price_proposal",
                    {"p_user_id": session.user_id, "p_item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID},
                ).execute()
                data = getattr(resp, "data", None)
                deleted = bool(data if isinstance(data, bool) else (data or False))
            except Exception:
                # Fallback: si no se ejecutó el SQL v8.7, no borra; deja cancelado.
                session.client.table("price_change_proposals").update({
                    "status": "cancelled",
                    "notes": "Propuesta simulada marcada como cancelada por limpieza admin. Puede borrarse con RPC v8.7.",
                }).eq("id", before.get("id")).execute()
                marked_cancelled = True

        event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action="admin_clean_worker_simulated_price_proposal",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            after_data={"deleted": deleted, "marked_cancelled": marked_cancelled},
            message="Admin limpió o canceló la propuesta de precio simulada worker.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "deleted": deleted, "marked_cancelled": marked_cancelled, "item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action="admin_clean_worker_simulated_price_proposal_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="price_change_proposal",
            entity_id=str(TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            after_data=None,
            message="Falló la limpieza de la propuesta de precio simulada worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise



def review_worker_simulated_price_proposal(session, decision: str, settings: Settings | None = None) -> dict[str, Any]:
    """Admin aprueba o rechaza la propuesta TEST_WORKER_PRICE_PROPOSAL.

    No publica nada en WooCommerce. Solo valida el ciclo:
    worker crea propuesta -> admin revisa -> Supabase actualiza -> caja negra registra.
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede aprobar/rechazar propuestas simuladas.")

    normalized = (decision or "").strip().lower()
    if normalized not in {"approved", "rejected"}:
        raise CloudAuditError("Decisión inválida. Usa approved o rejected.")

    operation_id = new_operation_id("REVIEWPRICE")
    before = None
    try:
        before = _fetch_simulated_price_proposal(session)
        if before is None:
            raise CloudAuditError("No existe TEST_WORKER_PRICE_PROPOSAL para revisar. Primero créala como worker.")

        snapshot = OperationSnapshot(
            operation_id=operation_id,
            module="price_change_proposals",
            action=f"admin_{normalized}_worker_simulated_price_proposal",
            entity_type="price_change_proposal",
            entity_id=str(before.get("id") or TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            reason=f"Revisión admin v8.9: snapshot antes de marcar propuesta simulada como {normalized}.",
        )
        write_snapshot(session, snapshot)

        review_payload = {
            "status": normalized,
            "reviewed_by": session.user_id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "notes": (before.get("notes") or "") + f"\n[TEST] Revisión admin: {normalized}. No publicar en WooCommerce.",
            "source_row": {
                **(before.get("source_row") or {}),
                "review_test": True,
                "review_operation_id": operation_id,
                "review_decision": normalized,
                "reviewed_by_email": session.email,
                "reviewed_by_role": session.role,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        try:
            resp = session.client.rpc(
                "futonhub_review_worker_simulated_price_proposal",
                {
                    "p_user_id": session.user_id,
                    "p_item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID,
                    "p_decision": normalized,
                    "p_operation_id": operation_id,
                },
            ).execute()
            rows = getattr(resp, "data", None) or []
            if isinstance(rows, list) and rows:
                written = rows[0]
            elif isinstance(rows, dict):
                written = rows
            else:
                after_resp = (
                    session.client.table("price_change_proposals")
                    .select("*")
                    .eq("id", before.get("id"))
                    .single()
                    .execute()
                )
                written = getattr(after_resp, "data", None) or review_payload
        except Exception:
            resp = (
                session.client.table("price_change_proposals")
                .update(review_payload)
                .eq("id", before.get("id"))
                .execute()
            )
            written = (getattr(resp, "data", None) or [review_payload])[0]

        event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action=f"admin_{normalized}_worker_simulated_price_proposal",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(before.get("id") or TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message=f"Admin marcó la propuesta de precio simulada worker como {normalized}. No se publicó en WooCommerce.",
        )
        write_audit_event(session, event, settings)
        return {
            "operation_id": operation_id,
            "decision": normalized,
            "proposal_id": before.get("id"),
            "item_woo_id": TEST_PRICE_PROPOSAL_WOO_ID,
            "name": TEST_PRICE_PROPOSAL_NAME,
            "before": before,
            "after": written,
        }
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action="admin_review_worker_simulated_price_proposal_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="price_change_proposal",
            entity_id=str(TEST_PRICE_PROPOSAL_WOO_ID),
            before_data=_json_safe(before),
            after_data=None,
            message="Falló la revisión admin de propuesta de precio simulada worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise




# ---------------------------------------------------------------------------
# v10 - Lectura operativa real desde Supabase y propuestas internas reales
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _short_row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _money_or_none(value: Any) -> float | None:
    return service_money_or_none(value)
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text.replace(",", "."))
    except Exception:
        return None


def _current_price_from_item(item: dict[str, Any]) -> float | None:
    return service_current_price_from_item(item)
    return _money_or_none(_short_row_value(item, "price", "regular_price", "sale_price"))


def _product_type(item: dict[str, Any], kind: str) -> str:
    return service_product_type(item, kind)
    if kind == "variation":
        return "variation"
    return str(item.get("type") or "product").strip().lower()


def _price_safety_preview(item: dict[str, Any], kind: str, proposed_price: float | None, settings: Settings) -> dict[str, Any]:
    return service_price_safety_preview(item, kind, proposed_price, settings)
    """Clasifica riesgos de precio antes de crear/publicar propuestas.

    status puede ser OK, WARNING o ERROR. ERROR bloquea; WARNING requiere
    confirmación explícita. No toca WooCommerce.
    """
    current = _current_price_from_item(item)
    kind = (kind or "").strip().lower()
    item_type = _product_type(item, kind)
    messages: list[str] = []
    status = "OK"

    if proposed_price is not None and proposed_price <= 0:
        messages.append("ERROR: el precio propuesto debe ser mayor que 0.")
        status = "ERROR"

    if kind == "product" and item_type in {"variable", "variable-subscription"}:
        messages.append("ERROR: el producto padre variable no tiene precio vendible único. Crea la propuesta sobre una variación concreta.")
        status = "ERROR"
    elif current is None or current <= 0:
        if kind == "variation":
            messages.append("WARNING: la variación no tiene precio actual válido en la base interna. La propuesta puede crearse, pero exige revisión antes de publicar.")
        else:
            messages.append("WARNING: el producto no tiene precio actual válido en la base interna. La propuesta puede crearse, pero exige revisión antes de publicar.")
        if status != "ERROR":
            status = "WARNING"

    delta = None
    delta_percent = None
    if current is not None and proposed_price is not None and current > 0:
        delta = proposed_price - current
        delta_percent = (delta / current) * 100
        if proposed_price < current:
            drop_percent = ((current - proposed_price) / current) * 100
            if drop_percent >= settings.price_drop_block_percent:
                messages.append(
                    f"ERROR: bajada de precio del {drop_percent:.2f}%, supera el bloqueo configurado "
                    f"({settings.price_drop_block_percent:.2f}%)."
                )
                status = "ERROR"
            elif drop_percent >= settings.price_drop_warning_percent and status != "ERROR":
                messages.append(
                    f"WARNING: bajada de precio del {drop_percent:.2f}%, supera el aviso configurado "
                    f"({settings.price_drop_warning_percent:.2f}%). Requiere confirmación explícita."
                )
                status = "WARNING"

    if not messages:
        messages.append("OK: validación de precio sin alertas.")

    return {
        "status": status,
        "messages": messages,
        "current_price": current,
        "proposed_price": proposed_price,
        "delta": delta,
        "delta_percent": delta_percent,
        "item_type": item_type,
        "warning_threshold_percent": settings.price_drop_warning_percent,
        "block_threshold_percent": settings.price_drop_block_percent,
    }


def _format_price_safety_for_search(row: dict[str, Any]) -> str | None:
    return service_format_price_safety_for_search(row)
    kind = row.get("item_kind")
    item_type = row.get("type") or ("variation" if kind == "variation" else "")
    price = _money_or_none(row.get("price"))
    if kind == "product" and str(item_type).lower() in {"variable", "variable-subscription"} and (price is None or price <= 0):
        return "WARNING: padre variable sin precio propio; usar variaciones."
    if kind == "variation" and (price is None or price <= 0):
        return "WARNING: variación sin precio actual válido."
    if kind == "product" and str(item_type).lower() not in {"variable", "variable-subscription"} and (price is None or price <= 0):
        return "WARNING: producto simple sin precio actual válido."
    return None


def search_cloud_products(session, query: str, limit: int = 15) -> list[dict[str, Any]]:
    return price_proposal_service.search_cloud_products(session, query, limit)
    """Busca productos/variaciones reales ya migrados a Supabase.

    No consulta WooCommerce. Sirve para validar que la base operativa cloud se
    puede usar como fuente interna del HUB.
    """
    q = (query or "").strip()
    if not q:
        raise CloudAuditError("Indica texto de búsqueda para productos Supabase.")
    limit = max(1, min(int(limit or 15), 50))
    pattern = f"%{q}%"
    results: list[dict[str, Any]] = []

    try:
        prod_resp = (
            session.client.table("products")
            .select("woo_id,name,sku,type,status,price,regular_price,sale_price,stock_status,stock_quantity")
            .ilike("name", pattern)
            .order("name")
            .limit(limit)
            .execute()
        )
        for row in getattr(prod_resp, "data", None) or []:
            result_row = {
                "item_kind": "product",
                "woo_id": row.get("woo_id"),
                "name": row.get("name"),
                "sku": row.get("sku"),
                "type": row.get("type"),
                "status": row.get("status"),
                "price": _short_row_value(row, "price", "regular_price", "sale_price"),
                "stock_status": row.get("stock_status"),
                "stock_quantity": row.get("stock_quantity"),
            }
            result_row["price_warning"] = _format_price_safety_for_search(result_row)
            results.append(result_row)
    except Exception as exc:
        raise CloudAuditError(f"No se pudieron buscar productos cloud: {exc}") from exc

    remaining = max(limit - len(results), 0)
    if remaining:
        try:
            var_resp = (
                session.client.table("product_variations")
                .select("woo_id,parent_woo_id,parent_name,sku,status,price,regular_price,sale_price,stock_status,stock_quantity,attributes_label")
                .ilike("parent_name", pattern)
                .order("parent_name")
                .limit(remaining)
                .execute()
            )
            for row in getattr(var_resp, "data", None) or []:
                label = row.get("attributes_label") or "variación"
                result_row = {
                    "item_kind": "variation",
                    "woo_id": row.get("woo_id"),
                    "parent_woo_id": row.get("parent_woo_id"),
                    "name": f"{row.get('parent_name')} · {label}",
                    "sku": row.get("sku"),
                    "type": "variation",
                    "status": row.get("status"),
                    "price": _short_row_value(row, "price", "regular_price", "sale_price"),
                    "stock_status": row.get("stock_status"),
                    "stock_quantity": row.get("stock_quantity"),
                }
                result_row["price_warning"] = _format_price_safety_for_search(result_row)
                results.append(result_row)
        except Exception as exc:
            raise CloudAuditError(f"No se pudieron buscar variaciones cloud: {exc}") from exc
    return results


def format_cloud_product_search(rows: list[dict[str, Any]]) -> str:
    return price_proposal_service.format_cloud_product_search(rows)
    if not rows:
        return "Sin resultados."
    lines = [
        "RESULTADOS PRODUCTOS SUPABASE",
        "=" * 42,
        "Copia item_kind + woo_id para crear propuesta real interna.",
        "",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"{idx}. [{row.get('item_kind')}] woo_id={row.get('woo_id')} · {row.get('name')}"
        )
        lines.append(
            f"   SKU: {row.get('sku') or '-'} · tipo: {row.get('type') or '-'} · precio: {row.get('price') or '-'} · "
            f"stock: {row.get('stock_status') or '-'} {row.get('stock_quantity') if row.get('stock_quantity') is not None else ''}"
        )
        if row.get("price_warning"):
            lines.append(f"   ⚠ {row.get('price_warning')}")
    return "\n".join(lines)


def _fetch_cloud_item_for_price(session, item_kind: str, woo_id: int) -> dict[str, Any]:
    return price_proposal_service.fetch_cloud_item_for_price(session, item_kind, woo_id)
    kind = (item_kind or "").strip().lower()
    if kind not in {"product", "variation"}:
        raise CloudAuditError("item_kind debe ser product o variation.")
    table = "products" if kind == "product" else "product_variations"
    resp = session.client.table(table).select("*").eq("woo_id", int(woo_id)).limit(1).execute()
    rows = getattr(resp, "data", None) or []
    if not rows:
        raise CloudAuditError(f"No existe {kind} con woo_id={woo_id} en Supabase.")
    row = rows[0]
    if kind == "variation":
        row["name"] = f"{row.get('parent_name')} · {row.get('attributes_label') or 'variación'}"
    return row


def _fetch_latest_price_proposal(session, *, item_kind: str | None = None, item_woo_id: int | None = None, status: str | None = None) -> dict[str, Any] | None:
    return price_proposal_service.fetch_latest_price_proposal(session, item_kind=item_kind, item_woo_id=item_woo_id, status=status)
    query = session.client.table("price_change_proposals").select("*").order("created_at", desc=True).limit(1)
    if item_kind:
        query = query.eq("item_kind", item_kind)
    if item_woo_id is not None:
        query = query.eq("item_woo_id", int(item_woo_id))
    if status:
        query = query.eq("status", status)
    resp = query.execute()
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None



def preview_real_price_proposal(session, item_kind: str, woo_id: int, new_price: float, notes: str = "", settings: Settings | None = None) -> dict[str, Any]:
    return price_proposal_service.preview_real_price_proposal(session, item_kind, woo_id, new_price, notes, settings)
    """Previsualiza una propuesta interna sin escribir nada.

    Se usa desde la UI para que el usuario vea qué se va a guardar antes de
    crear la propuesta. No toca WooCommerce ni Supabase.
    """
    settings = settings or load_settings()
    kind = (item_kind or "").strip().lower()
    item = _fetch_cloud_item_for_price(session, kind, int(woo_id))
    proposed_price = _safe_float(new_price, 0.0)
    validation = _price_safety_preview(item, kind, proposed_price, settings)
    old_price = validation.get("current_price")
    return {
        "item": item,
        "item_kind": kind,
        "woo_id": int(woo_id),
        "name": item.get("name") or item.get("parent_name") or f"{kind} {woo_id}",
        "old_price": old_price,
        "new_price": proposed_price,
        "notes": notes or "",
        "price_safety": validation,
    }


def format_real_price_proposal_preview(preview: dict[str, Any]) -> str:
    return price_proposal_service.format_real_price_proposal_preview(preview)
    """Texto legible para revisar una propuesta antes de crear/aprobar/rechazar."""
    safety = preview.get("price_safety") or {}
    old_price = preview.get("old_price")
    new_price = preview.get("new_price")
    delta = safety.get("delta")
    pct = safety.get("delta_percent")
    lines = [
        "PREVIEW PROPUESTA DE PRECIO",
        "=" * 38,
        f"Item: [{preview.get('item_kind')}] {preview.get('woo_id')} · {preview.get('name')}",
        f"Precio actual interno: {old_price if old_price is not None else '-'}",
        f"Precio propuesto: {new_price if new_price is not None else '-'}",
    ]
    if delta is not None:
        if pct is None:
            lines.append(f"Diferencia: {delta:.2f} (sin % por precio base 0/vacío)")
        else:
            lines.append(f"Diferencia: {delta:.2f} ({pct:.2f}%)")
    if preview.get("notes"):
        lines.append(f"Notas: {preview.get('notes')}")
    lines.extend(["", f"Estado seguridad: {safety.get('status') or 'OK'}"])
    for msg in safety.get("messages") or []:
        lines.append(f"- {msg}")
    lines.extend(["", "WooCommerce no será tocado al crear esta propuesta."])
    return "\n".join(lines)


def get_real_price_proposal(session, proposal_id: str) -> dict[str, Any]:
    return price_proposal_service.get_real_price_proposal(session, proposal_id)
    if not proposal_id:
        raise CloudAuditError("Selecciona una propuesta.")
    resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
    rows = getattr(resp, "data", None) or []
    if not rows:
        raise CloudAuditError(f"No se encontró la propuesta {proposal_id}.")
    return rows[0]


def preview_existing_price_proposal(session, proposal_id: str, settings: Settings | None = None) -> dict[str, Any]:
    return price_proposal_service.preview_existing_price_proposal(session, proposal_id, settings)
    """Previsualiza una propuesta ya guardada antes de aprobar/rechazar."""
    settings = settings or load_settings()
    row = get_real_price_proposal(session, proposal_id)
    kind = (row.get("item_kind") or "").strip().lower()
    woo_id = int(row.get("item_woo_id"))
    item = _fetch_cloud_item_for_price(session, kind, woo_id)
    proposed = _safe_float(row.get("new_price"), 0.0)
    validation = _price_safety_preview(item, kind, proposed, settings)
    return {
        "proposal": row,
        "item": item,
        "item_kind": kind,
        "woo_id": woo_id,
        "name": row.get("name") or item.get("name") or item.get("parent_name") or f"{kind} {woo_id}",
        "old_price": row.get("old_price"),
        "new_price": row.get("new_price"),
        "notes": row.get("notes") or "",
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "reviewed_at": row.get("reviewed_at"),
        "price_safety": validation,
    }


def format_existing_price_proposal_preview(preview: dict[str, Any]) -> str:
    return price_proposal_service.format_existing_price_proposal_preview(preview)
    prop = preview.get("proposal") or {}
    safety = preview.get("price_safety") or {}
    old_price = preview.get("old_price")
    new_price = preview.get("new_price")
    delta = None
    pct = None
    try:
        if old_price not in (None, "") and new_price not in (None, ""):
            oldf = float(old_price)
            newf = float(new_price)
            delta = newf - oldf
            if oldf != 0:
                pct = (delta / oldf) * 100
    except Exception:
        pass
    lines = [
        "PREVIEW PROPUESTA GUARDADA",
        "=" * 38,
        f"Estado actual: {preview.get('status') or prop.get('status')}",
        f"Propuesta ID: {prop.get('id')}",
        f"Item: [{preview.get('item_kind')}] {preview.get('woo_id')} · {preview.get('name')}",
        f"Precio actual interno al crear propuesta: {old_price if old_price is not None else '-'}",
        f"Precio propuesto: {new_price if new_price is not None else '-'}",
    ]
    if delta is not None:
        if pct is None:
            lines.append(f"Diferencia: {delta:.2f} (sin % por precio base 0/vacío)")
        else:
            lines.append(f"Diferencia: {delta:.2f} ({pct:.2f}%)")
    if preview.get("notes"):
        lines.append(f"Notas: {preview.get('notes')}")
    source = prop.get("source_row") or {}
    if source.get("created_by_email"):
        lines.append(f"Creado por: {source.get('created_by_email')} · máquina: {source.get('machine') or '-'}")
    if source.get("reviewed_by_email"):
        lines.append(f"Revisado por: {source.get('reviewed_by_email')} · rol: {source.get('reviewed_by_role') or '-'}")
    lines.extend(["", f"Estado seguridad recalculado: {safety.get('status') or 'OK'}"])
    for msg in safety.get("messages") or []:
        lines.append(f"- {msg}")
    lines.extend(["", "Aprobar/rechazar NO toca WooCommerce. Solo cambia el estado interno y genera caja negra."])
    return "\n".join(lines)

def create_real_price_proposal(session, item_kind: str, woo_id: int, new_price: float, notes: str = "", settings: Settings | None = None, acknowledge_price_warning: bool = False) -> dict[str, Any]:
    return price_proposal_service.create_real_price_proposal(session, item_kind, woo_id, new_price, notes, settings, acknowledge_price_warning)
    """Crea/actualiza una propuesta interna real sobre producto migrado.

    No publica nada en WooCommerce. Solo escribe en Supabase y registra caja negra.
    """
    settings = settings or load_settings()
    kind = (item_kind or "").strip().lower()
    item = _fetch_cloud_item_for_price(session, kind, int(woo_id))
    proposed_price = _safe_float(new_price, 0.0)
    validation = _price_safety_preview(item, kind, proposed_price, settings)
    old_price = validation.get("current_price")
    operation_id = new_operation_id("REALPRICE")
    before = None

    if validation["status"] == "ERROR":
        raise CloudAuditError(
            "Validación de precio bloqueada:\n"
            + "\n".join(f"- {m}" for m in validation["messages"])
        )
    if validation["status"] == "WARNING" and not acknowledge_price_warning:
        raise CloudAuditError(
            "Validación de precio requiere confirmación explícita:\n"
            + "\n".join(f"- {m}" for m in validation["messages"])
            + "\n\nSi revisaste el cambio, repite con --ack-price-warning."
        )

    try:
        before = _fetch_latest_price_proposal(session, item_kind=kind, item_woo_id=int(woo_id), status="pending")
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="price_change_proposals",
                action="worker_real_price_proposal_update",
                entity_type="price_change_proposal",
                entity_id=str(before.get("id") or woo_id),
                before_data=_json_safe(before),
                reason="v10: snapshot antes de actualizar propuesta real interna. WooCommerce no se toca.",
            )
            write_snapshot(session, snapshot)

        payload = {
            "local_id": int(woo_id),
            "item_kind": kind,
            "item_woo_id": int(woo_id),
            "name": item.get("name") or item.get("parent_name") or f"{kind} {woo_id}",
            "old_price": old_price,
            "new_price": proposed_price,
            "delta": proposed_price - old_price if old_price is not None else None,
            "notes": notes or "Propuesta real interna creada desde Supabase. No publicar en WooCommerce todavía.",
            "status": "pending",
            "created_by": session.user_id,
            "source_row": {
                "v": "v10_real_price_proposal",
                "operation_id": operation_id,
                "created_by_email": session.email,
                "role": session.role or settings.sync_role,
                "machine": settings.machine_name,
                "woo_publish": False,
                "item_snapshot": _json_safe(item),
                "price_safety": _json_safe(validation),
                "acknowledged_price_warning": bool(acknowledge_price_warning),
            },
        }

        if before is None:
            resp = session.client.table("price_change_proposals").insert(payload).execute()
            action = "worker_real_price_proposal_create"
        else:
            resp = session.client.table("price_change_proposals").update(payload).eq("id", before.get("id")).execute()
            action = "worker_real_price_proposal_update"
        written = (getattr(resp, "data", None) or [payload])[0]

        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(written.get("id") or woo_id),
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message="v10: propuesta de precio real interna creada/actualizada. WooCommerce no fue tocado.",
        ), settings)
        return {"operation_id": operation_id, "action": action, "proposal": written, "item": item, "old_price": old_price, "new_price": proposed_price, "price_safety": validation}
    except CloudAuditError:
        raise
    except Exception as exc:
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="price_change_proposals",
                action="worker_real_price_proposal_failed",
                status="ERROR",
                severity="ERROR",
                entity_type="price_change_proposal",
                entity_id=str(woo_id),
                before_data=_json_safe(before),
                message="Falló v10 propuesta real interna.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise


def review_latest_real_price_proposal(session, decision: str, proposal_id: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    return price_proposal_service.review_latest_real_price_proposal(session, decision, proposal_id, settings)
    """Admin o worker aprueba/rechaza una propuesta real interna. No publica WooCommerce."""
    settings = settings or load_settings()
    role = (session.role or "").lower()
    if role not in {"admin", "worker"}:
        raise CloudAuditError("Solo usuarios admin o worker activos pueden aprobar/rechazar propuestas reales internas.")
    normalized = (decision or "").strip().lower()
    if normalized not in {"approved", "rejected"}:
        raise CloudAuditError("Decisión inválida. Usa approved o rejected.")
    operation_id = new_operation_id("REALREVIEW")
    before = None
    try:
        if proposal_id:
            resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
            rows = getattr(resp, "data", None) or []
            before = rows[0] if rows else None
        else:
            before = _fetch_latest_price_proposal(session, status="pending")
        if before is None:
            raise CloudAuditError("No hay propuesta pendiente para revisar.")
        # No revisar propuestas TEST_* aquí salvo que se pida por el flujo test anterior.
        if (before.get("source_row") or {}).get("test") is True:
            raise CloudAuditError("La última pendiente es de TEST. Usa el flujo de review test para esa propuesta.")

        write_snapshot(session, OperationSnapshot(
            operation_id=operation_id,
            module="price_change_proposals",
            action=f"user_{normalized}_real_price_proposal",
            entity_type="price_change_proposal",
            entity_id=str(before.get("id")),
            before_data=_json_safe(before),
            reason=f"v12: snapshot antes de marcar propuesta real interna como {normalized}. WooCommerce no se toca.",
        ))
        payload = {
            "status": normalized,
            "reviewed_by": session.user_id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "notes": (before.get("notes") or "") + f"\n[v10] Revisión admin: {normalized}. No publicado en WooCommerce.",
            "source_row": {
                **(before.get("source_row") or {}),
                "review_operation_id": operation_id,
                "review_decision": normalized,
                "reviewed_by_email": session.email,
                "reviewed_by_role": session.role,
                "woo_publish": False,
            },
        }
        resp = session.client.table("price_change_proposals").update(payload).eq("id", before.get("id")).execute()
        written = (getattr(resp, "data", None) or [{**before, **payload}])[0]
        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action=f"user_{normalized}_real_price_proposal",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(before.get("id")),
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message=f"v12: usuario marcó propuesta real interna como {normalized}. WooCommerce no fue tocado.",
        ), settings)
        return {"operation_id": operation_id, "decision": normalized, "proposal": written, "before": before}
    except CloudAuditError:
        raise
    except Exception as exc:
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="price_change_proposals",
                action="user_review_real_price_proposal_failed",
                status="ERROR",
                severity="ERROR",
                entity_type="price_change_proposal",
                entity_id=str((before or {}).get("id") or proposal_id or "latest"),
                before_data=_json_safe(before),
                message="Falló v12 revisión de propuesta real interna.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise



def list_real_price_proposals(session, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return price_proposal_service.list_real_price_proposals(session, status, limit)
    """Lista propuestas reales internas para bandeja operativa.

    Excluye propuestas de test marcadas en source_row.test.
    """
    normalized_status = (status or "").strip().lower()
    if normalized_status and normalized_status != "all" and normalized_status not in PRICE_PROPOSAL_STATUSES:
        raise CloudAuditError(
            "Estado invalido. Usa: "
            + ", ".join(sorted(PRICE_PROPOSAL_STATUSES))
            + " o all."
        )
    query = session.client.table("price_change_proposals").select("*").order("created_at", desc=True).limit(max(1, min(int(limit or 50), 200)))
    if normalized_status and normalized_status != "all":
        query = query.eq("status", normalized_status)
    resp = query.execute()
    rows = getattr(resp, "data", None) or []
    result: list[dict[str, Any]] = []
    for row in rows:
        source = row.get("source_row") or {}
        if source.get("test") is True:
            continue
        result.append(row)
    return result


def format_real_price_proposals(rows: list[dict[str, Any]]) -> str:
    return price_proposal_service.format_real_price_proposals(rows)
    lines = [
        "PROPUESTAS REALES INTERNAS",
        "=" * 38,
        "WooCommerce no se toca desde esta vista.",
        "",
    ]
    if not rows:
        lines.append("No hay propuestas reales para mostrar.")
        return "\n".join(lines)
    for idx, row in enumerate(rows, start=1):
        old_price = _safe_money(row.get("old_price"))
        new_price = _safe_money(row.get("new_price"))
        delta = None if old_price is None or new_price is None else new_price - old_price
        pct = None
        if delta is not None and old_price not in (None, 0):
            pct = (delta / old_price) * 100
        lines.append(f"{idx}. {row.get('status')} · [{row.get('item_kind')}] {row.get('item_woo_id')} · {row.get('name')}")
        lines.append(f"   propuesta_id: {row.get('id')}")
        lines.append(f"   precio anterior interno: {old_price} · propuesto: {new_price}")
        if delta is not None:
            if pct is None:
                lines.append(f"   diferencia: {delta:.2f} (sin % por precio base 0/vacío)")
            else:
                lines.append(f"   diferencia: {delta:.2f} ({pct:.2f}%)")
        lines.append(f"   creado: {row.get('created_at')} · revisado: {row.get('reviewed_at') or '-'}")
        source = row.get("source_row") or {}
        if source.get("created_by_email"):
            lines.append(f"   creado por: {source.get('created_by_email')} · máquina: {source.get('machine') or '-'}")
        if source.get("reviewed_by_email"):
            lines.append(f"   revisado por: {source.get('reviewed_by_email')} · rol: {source.get('reviewed_by_role') or '-'}")
        lines.append("")
    return "\n".join(lines)


def run_cloud_list_real_price_proposals(status: str = "pending", limit: int = 50) -> int:
    try:
        session, _settings = _login_from_console()
        rows = list_real_price_proposals(session, status=status, limit=limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_real_price_proposals(rows))
    return 0

def run_cloud_search_products(query: str, limit: int = 15) -> int:
    try:
        session, _settings = _login_from_console()
        rows = search_cloud_products(session, query, limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_cloud_product_search(rows))
    return 0


def run_cloud_real_price_proposal(item_kind: str, woo_id: int, new_price: float, notes: str = "", ack_price_warning: bool = False) -> int:
    try:
        session, settings = _login_from_console()
        result = create_real_price_proposal(session, item_kind, int(woo_id), float(new_price), notes, settings, acknowledge_price_warning=ack_price_warning)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    proposal = result["proposal"]
    item = result["item"]
    print("Propuesta real interna creada/actualizada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print(f"item: [{proposal.get('item_kind')}] {proposal.get('item_woo_id')} · {item.get('name') or item.get('parent_name')}")
    print(f"precio anterior: {result['old_price']}")
    print(f"precio propuesto: {result['new_price']}")
    safety = result.get("price_safety") or {}
    print(f"validación precio: {safety.get('status')}")
    for msg in safety.get("messages") or []:
        print(f" - {msg}")
    if safety.get("delta") is not None:
        print(f"diferencia: {safety.get('delta'):.2f} ({safety.get('delta_percent'):.2f}%)")
    print("WooCommerce no fue tocado.")
    return 0



def price_heart_attack_tests(session, item_kind: str, woo_id: int, settings: Settings | None = None) -> dict[str, Any]:
    """Ejecuta pruebas de estrés de precio sin escribir datos.

    No crea propuestas, no toca WooCommerce y no actualiza Supabase. Solo usa la
    misma lógica de validación que protege las propuestas reales.
    """
    settings = settings or load_settings()
    kind = (item_kind or "").strip().lower()
    item = _fetch_cloud_item_for_price(session, kind, int(woo_id))
    current = _current_price_from_item(item)
    base = float(current or 100.0)
    warning_drop = min(max(settings.price_drop_warning_percent + 10.0, settings.price_drop_warning_percent), settings.price_drop_block_percent - 1.0)
    if warning_drop <= settings.price_drop_warning_percent:
        warning_drop = settings.price_drop_warning_percent
    if warning_drop >= settings.price_drop_block_percent:
        warning_drop = max(settings.price_drop_warning_percent, settings.price_drop_block_percent - 1.0)
    warning_price = round(base * (1.0 - warning_drop / 100.0), 2)
    if warning_price <= 0:
        warning_price = 0.01
    block_drop = max(settings.price_drop_block_percent, settings.price_drop_block_percent + 5.0)
    block_price = round(base * (1.0 - block_drop / 100.0), 2)
    if block_price <= 0:
        block_price = 0.01
    cases = [
        {
            "case": "precio_cero",
            "title": "Ataque 1: precio propuesto 0",
            "expected": "ERROR",
            "proposed_price": 0.0,
        },
        {
            "case": "bajada_amarilla",
            "title": f"Ataque 2: bajada amarilla >= {settings.price_drop_warning_percent:.2f}%",
            "expected": "WARNING" if current and current > 0 else "WARNING",
            "proposed_price": warning_price,
        },
        {
            "case": "bajada_roja",
            "title": f"Ataque 3: bajada roja >= {settings.price_drop_block_percent:.2f}%",
            "expected": "ERROR" if current and current > 0 else "WARNING",
            "proposed_price": block_price,
        },
    ]
    results: list[dict[str, Any]] = []
    for case in cases:
        validation = _price_safety_preview(item, kind, case["proposed_price"], settings)
        results.append({**case, "validation": validation})
    return {
        "item": item,
        "item_kind": kind,
        "woo_id": int(woo_id),
        "current_price": current,
        "warning_threshold_percent": settings.price_drop_warning_percent,
        "block_threshold_percent": settings.price_drop_block_percent,
        "results": results,
    }


def format_price_heart_attack_tests(result: dict[str, Any]) -> str:
    item = result.get("item") or {}
    lines = [
        "PRUEBAS ATAQUE AL CORAZÓN · PRECIOS",
        "=" * 48,
        "No crea propuestas. No toca WooCommerce. No modifica Supabase.",
        "",
        f"Item: [{result.get('item_kind')}] {result.get('woo_id')} · {item.get('name') or item.get('parent_name') or '-'}",
        f"Precio actual interno usado: {result.get('current_price') if result.get('current_price') is not None else '0/vacío'}",
        f"Umbral WARNING: {result.get('warning_threshold_percent'):.2f}%",
        f"Umbral ERROR: {result.get('block_threshold_percent'):.2f}%",
        "",
    ]
    all_ok = True
    for idx, case in enumerate(result.get("results") or [], start=1):
        validation = case.get("validation") or {}
        actual = validation.get("status") or "OK"
        expected = case.get("expected")
        ok = actual == expected
        all_ok = all_ok and ok
        lines.append(f"{idx}. {case.get('title')}")
        lines.append(f"   Precio probado: {case.get('proposed_price')}")
        lines.append(f"   Esperado: {expected} · Resultado: {actual} · {'OK' if ok else 'REVISAR'}")
        if validation.get("delta") is not None:
            pct = validation.get("delta_percent")
            if pct is None:
                lines.append(f"   Diferencia: {validation.get('delta'):.2f} (sin % por base 0/vacía)")
            else:
                lines.append(f"   Diferencia: {validation.get('delta'):.2f} ({pct:.2f}%)")
        for msg in validation.get("messages") or []:
            lines.append(f"   - {msg}")
        lines.append("")
    lines.append("RESULTADO GLOBAL: " + ("OK · barreras de precio responden como esperado." if all_ok else "REVISAR · alguna barrera no respondió como esperado."))
    return "\n".join(lines)


def run_cloud_price_heart_attack_tests(item_kind: str, woo_id: int) -> int:
    try:
        session, settings = _login_from_console()
        result = price_heart_attack_tests(session, item_kind, int(woo_id), settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_price_heart_attack_tests(result))
    return 0


def run_cloud_review_real_price_proposal(decision: str, proposal_id: str = "") -> int:
    try:
        session, settings = _login_from_console()
        result = review_latest_real_price_proposal(session, decision, proposal_id or None, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    prop = result["proposal"]
    print("Propuesta real interna revisada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"decision: {result['decision']}")
    print(f"proposal_id: {prop.get('id')}")
    print(f"item: [{prop.get('item_kind')}] {prop.get('item_woo_id')} · {prop.get('name')}")
    print("WooCommerce no fue tocado.")
    return 0


def run_cloud_review_worker_price_test(decision: str) -> int:
    try:
        session, settings = _login_from_console()
        result = review_worker_simulated_price_proposal(session, decision, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Propuesta de precio simulada revisada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"decision: {result['decision']}")
    print("Tabla: price_change_proposals")
    print(f"item_woo_id: {result['item_woo_id']}")
    print("No se publicó nada en WooCommerce.")
    return 0

def run_cloud_worker_price_test() -> int:
    try:
        session, settings = _login_from_console()
        result = test_worker_simulated_price_proposal(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Propuesta de precio simulada worker creada/actualizada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print("Tabla: price_change_proposals")
    print(f"item_woo_id: {result['item_woo_id']}")
    print(f"old_price: {result['old_price']}")
    print(f"new_price: {result['new_price']}")
    print("Admin debe verlo en audit_logs, operation_snapshots y price_change_proposals.")
    return 0


def run_cloud_clean_worker_price_test() -> int:
    try:
        session, settings = _login_from_console()
        result = clean_worker_simulated_price_proposal(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Limpieza de propuesta de precio simulada worker completada.")
    print(f"operation_id: {result['operation_id']}")
    print(f"deleted: {result['deleted']}")
    print(f"marked_cancelled: {result['marked_cancelled']}")
    print(f"item_woo_id: {result['item_woo_id']}")
    return 0


TEST_INVENTORY_ITEM_ID = -900001
TEST_INVENTORY_ITEM_NAME = "TEST_WORKER_INVENTORY_ITEM"


def _fetch_simulated_inventory_item(session) -> dict[str, Any] | None:
    """Devuelve el item de inventario simulado, o None si no existe."""
    resp = (
        session.client.table("inventory_items")
        .select("*")
        .eq("item_id", TEST_INVENTORY_ITEM_ID)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def test_worker_simulated_inventory_change(session, settings: Settings | None = None) -> dict[str, Any]:
    """Crea/actualiza un item de inventario TEST_* reversible.

    Es una prueba más cercana al trabajo real de tienda, pero aislada:
    - item_id negativo reservado para pruebas
    - name TEST_WORKER_INVENTORY_ITEM
    - no enlaza WooCommerce
    - no afecta inventario real
    """
    settings = settings or load_settings()
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("WORKERINV")

    try:
        before = _fetch_simulated_inventory_item(session)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="inventory_items",
                action="worker_simulated_inventory_update",
                entity_type="inventory_item",
                entity_id=str(TEST_INVENTORY_ITEM_ID),
                before_data=_json_safe(before),
                reason="Prueba worker v8.6: snapshot antes de actualizar inventario simulado TEST_*.",
            )
            write_snapshot(session, snapshot)

        previous_store_stock = 0 if before is None else float(before.get("store_stock") or 0)
        previous_warehouse_stock = 0 if before is None else float(before.get("warehouse_stock") or 0)
        new_store_stock = previous_store_stock + 1
        new_warehouse_stock = previous_warehouse_stock + 2

        payload = {
            "item_id": TEST_INVENTORY_ITEM_ID,
            "name": TEST_INVENTORY_ITEM_NAME,
            "family": "TEST",
            "subgroup": "WORKER_SIMULATION",
            "commercial_status": "Simulado",
            "store_stock": new_store_stock,
            "warehouse_stock": new_warehouse_stock,
            "notes": "Item de inventario simulado para validar worker/admin. No usar como inventario real.",
            "woo_link_status": "TEST_NO_WOO",
            "source_row": {
                "test": True,
                "test_name": "worker_simulated_inventory",
                "operation_id": operation_id,
                "updated_at": now,
                "updated_by_email": session.email,
                "role": session.role or settings.sync_role,
                "machine": settings.machine_name,
                "note": "Prueba reversible. No toca WooCommerce ni inventario real.",
            },
            "updated_at": now,
            "updated_by": session.user_id,
        }

        if before is None:
            write_resp = session.client.table("inventory_items").insert(payload).execute()
            action = "worker_simulated_inventory_create"
        else:
            write_resp = (
                session.client.table("inventory_items")
                .update(payload)
                .eq("item_id", TEST_INVENTORY_ITEM_ID)
                .execute()
            )
            action = "worker_simulated_inventory_update"

        written = (getattr(write_resp, "data", None) or [payload])[0]
        event = AuditEvent(
            operation_id=operation_id,
            module="inventory_items",
            action=action,
            status="OK",
            severity="INFO",
            entity_type="inventory_item",
            entity_id=str(TEST_INVENTORY_ITEM_ID),
            before_data=_json_safe(before),
            after_data=_json_safe(written),
            message="Prueba real v8.6: usuario operativo creó/actualizó inventario simulado correctamente.",
        )
        write_audit_event(session, event, settings)
        return {
            "operation_id": operation_id,
            "action": action,
            "item_id": TEST_INVENTORY_ITEM_ID,
            "name": TEST_INVENTORY_ITEM_NAME,
            "before": before,
            "after": written,
            "store_stock": new_store_stock,
            "warehouse_stock": new_warehouse_stock,
        }
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="inventory_items",
            action="worker_simulated_inventory_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="inventory_item",
            entity_id=str(TEST_INVENTORY_ITEM_ID),
            before_data=None,
            after_data=None,
            message="Falló la prueba v8.6 de inventario simulado worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def clean_worker_simulated_inventory(session, settings: Settings | None = None) -> dict[str, Any]:
    """Limpia TEST_WORKER_INVENTORY_ITEM. Solo admin."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede limpiar el inventario simulado worker.")

    operation_id = new_operation_id("CLEANWORKERINV")
    before = None
    try:
        before = _fetch_simulated_inventory_item(session)
        if before is not None:
            snapshot = OperationSnapshot(
                operation_id=operation_id,
                module="inventory_items",
                action="admin_clean_worker_simulated_inventory",
                entity_type="inventory_item",
                entity_id=str(TEST_INVENTORY_ITEM_ID),
                before_data=_json_safe(before),
                reason="Limpieza admin v8.6: snapshot antes de limpiar inventario simulado worker.",
            )
            write_snapshot(session, snapshot)

        deleted = False
        marked_inactive = False
        if before is not None:
            try:
                resp = session.client.rpc(
                    "futonhub_clean_worker_simulated_inventory",
                    {"p_user_id": session.user_id, "p_item_id": TEST_INVENTORY_ITEM_ID},
                ).execute()
                data = getattr(resp, "data", None)
                deleted = bool(data if isinstance(data, bool) else (data or False))
            except Exception:
                # Fallback: si no se ejecutó el SQL v8.6, no borra; lo marca claramente.
                session.client.table("inventory_items").update({
                    "commercial_status": "Cancelado",
                    "notes": "Inventario simulado marcado como cancelado por limpieza admin. Puede borrarse con RPC v8.6.",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("item_id", TEST_INVENTORY_ITEM_ID).execute()
                marked_inactive = True

        event = AuditEvent(
            operation_id=operation_id,
            module="inventory_items",
            action="admin_clean_worker_simulated_inventory",
            status="OK",
            severity="INFO",
            entity_type="inventory_item",
            entity_id=str(TEST_INVENTORY_ITEM_ID),
            before_data=_json_safe(before),
            after_data={"deleted": deleted, "marked_inactive": marked_inactive},
            message="Admin limpió o canceló el inventario simulado worker.",
        )
        write_audit_event(session, event, settings)
        return {"operation_id": operation_id, "deleted": deleted, "marked_inactive": marked_inactive, "item_id": TEST_INVENTORY_ITEM_ID}
    except CloudAuditError:
        raise
    except Exception as exc:
        error_event = AuditEvent(
            operation_id=operation_id,
            module="inventory_items",
            action="admin_clean_worker_simulated_inventory_failed",
            status="ERROR",
            severity="ERROR",
            entity_type="inventory_item",
            entity_id=str(TEST_INVENTORY_ITEM_ID),
            before_data=_json_safe(before),
            after_data=None,
            message="Falló la limpieza del inventario simulado worker.",
            error_detail=str(exc),
        )
        try:
            write_audit_event(session, error_event, settings)
        except Exception:
            pass
        raise


def run_cloud_worker_inventory_test() -> int:
    try:
        session, settings = _login_from_console()
        result = test_worker_simulated_inventory_change(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Inventario simulado worker creado/actualizado correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print("Tabla: inventory_items")
    print(f"item_id: {result['item_id']}")
    print(f"store_stock: {result['store_stock']}")
    print(f"warehouse_stock: {result['warehouse_stock']}")
    print("Admin debe verlo en audit_logs, operation_snapshots e inventory_items.")
    return 0


def run_cloud_clean_worker_inventory_test() -> int:
    try:
        session, settings = _login_from_console()
        result = clean_worker_simulated_inventory(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Limpieza de inventario simulado worker completada.")
    print(f"operation_id: {result['operation_id']}")
    print(f"deleted: {result['deleted']}")
    print(f"marked_inactive: {result['marked_inactive']}")
    print(f"item_id: {result['item_id']}")
    return 0

def run_cloud_worker_feedback_test() -> int:
    try:
        session, settings = _login_from_console()
        result = test_worker_feedback_constant_change(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Prueba worker real creada/actualizada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print(f"Tabla: business_constants")
    print(f"Clave: {result['key']}")
    print("Admin debe verla en audit_logs, operation_snapshots y business_constants.")
    return 0


def run_cloud_clean_worker_feedback_test() -> int:
    try:
        session, settings = _login_from_console()
        result = clean_worker_feedback_constant(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Limpieza de prueba worker completada.")
    print(f"operation_id: {result['operation_id']}")
    print(f"deleted: {result['deleted']}")
    print(f"Clave: {result['key']}")
    return 0



def run_cloud_worker_order_test() -> int:
    try:
        session, settings = _login_from_console()
        result = test_worker_simulated_order(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Pedido simulado worker creado/actualizado correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print(f"Tabla: supplier_orders / supplier_order_items")
    print(f"order_file: {result['order_file']}")
    print(f"order_id: {result['order_id']}")
    print("Admin debe verlo en audit_logs, operation_snapshots y supplier_orders.")
    return 0


def run_cloud_clean_worker_order_test() -> int:
    try:
        session, settings = _login_from_console()
        result = clean_worker_simulated_order(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Limpieza de pedido simulado worker completada.")
    print(f"operation_id: {result['operation_id']}")
    print(f"deleted: {result['deleted']}")
    print(f"marked_cancelled: {result['marked_cancelled']}")
    print(f"order_file: {result['order_file']}")
    return 0


# ---------------------------------------------------------------------------
# v11 - Importación quirúrgica de un producto WooCommerce de prueba a Supabase
# ---------------------------------------------------------------------------

def _woo_product_to_cloud_payload(product: dict[str, Any], session, settings: Settings) -> dict[str, Any]:
    return {
        "woo_id": int(product.get("id")),
        "name": product.get("name") or f"Producto Woo {product.get('id')}",
        "sku": product.get("sku") or None,
        "type": product.get("type") or None,
        "status": product.get("status") or None,
        "regular_price": product.get("regular_price") or None,
        "sale_price": product.get("sale_price") or None,
        "price": product.get("price") or None,
        "stock_status": product.get("stock_status") or None,
        "stock_quantity": product.get("stock_quantity"),
        "categories_json": product.get("categories") or [],
        "raw_json": _json_safe(product),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": session.user_id,
    }


def _variation_label(variation: dict[str, Any]) -> str:
    labels: list[str] = []
    for attr in variation.get("attributes") or []:
        name = attr.get("name") or attr.get("slug") or "Atributo"
        option = attr.get("option") or ""
        if option:
            labels.append(f"{name}: {option}")
    return " · ".join(labels)


def _woo_variation_to_cloud_payload(variation: dict[str, Any], parent: dict[str, Any], session, settings: Settings) -> dict[str, Any]:
    return {
        "woo_id": int(variation.get("id")),
        "parent_woo_id": int(parent.get("id")),
        "parent_name": parent.get("name") or f"Producto Woo {parent.get('id')}",
        "sku": variation.get("sku") or None,
        "status": variation.get("status") or None,
        "regular_price": variation.get("regular_price") or None,
        "sale_price": variation.get("sale_price") or None,
        "price": variation.get("price") or None,
        "stock_status": variation.get("stock_status") or None,
        "stock_quantity": variation.get("stock_quantity"),
        "attributes_json": variation.get("attributes") or [],
        "attributes_label": _variation_label(variation),
        "raw_json": _json_safe(variation),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": session.user_id,
    }


def _find_woocommerce_product(client: WooCommerceClient, woo_id: int | None = None, query: str | None = None) -> dict[str, Any]:
    if woo_id:
        return client.get(f"products/{int(woo_id)}").json()
    if not query or not query.strip():
        raise CloudAuditError("Indica --woo-id o --query para localizar el producto WooCommerce.")
    response = client.get("products", params={"search": query.strip(), "per_page": 20, "page": 1, "status": "any"})
    products = response.json()
    if not products:
        raise CloudAuditError(f"WooCommerce no devolvió productos para la búsqueda: {query}")
    # Preferimos coincidencia exacta por nombre si existe; si no, el primer resultado.
    normalized = query.strip().casefold()
    for product in products:
        if (product.get("name") or "").strip().casefold() == normalized:
            return product
    return products[0]


def import_single_woocommerce_product_to_supabase(session, woo_id: int | None = None, query: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Importa un solo producto WooCommerce y sus variaciones a Supabase.

    Uso pensado para el producto de prueba creado después de la migración.
    No publica cambios en WooCommerce. Solo lee WooCommerce y actualiza Supabase.
    Requiere admin porque usa credenciales WooCommerce y modifica tablas maestras cloud.
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede importar productos desde WooCommerce a Supabase.")

    operation_id = new_operation_id("WOOIMPORT")
    product_before = None
    variation_befores: list[dict[str, Any]] = []
    try:
        client = WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
        product = _find_woocommerce_product(client, woo_id=woo_id, query=query)
        product_id = int(product.get("id"))

        before_resp = session.client.table("products").select("*").eq("woo_id", product_id).limit(1).execute()
        before_rows = getattr(before_resp, "data", None) or []
        product_before = before_rows[0] if before_rows else None
        if product_before is not None:
            write_snapshot(session, OperationSnapshot(
                operation_id=operation_id,
                module="woocommerce_import",
                action="admin_import_single_product_update",
                entity_type="product",
                entity_id=str(product_id),
                before_data=_json_safe(product_before),
                reason="v11: snapshot antes de actualizar producto WooCommerce importado a Supabase.",
            ))

        product_payload = _woo_product_to_cloud_payload(product, session, settings)
        session.client.table("products").upsert(product_payload, on_conflict="woo_id").execute()

        variations = list(client.iter_product_variations(product_id)) if (product.get("type") in {"variable", "variable-subscription"} or True) else []
        variation_payloads: list[dict[str, Any]] = []
        for variation in variations:
            variation_id = int(variation.get("id"))
            vb_resp = session.client.table("product_variations").select("*").eq("woo_id", variation_id).limit(1).execute()
            vb_rows = getattr(vb_resp, "data", None) or []
            if vb_rows:
                variation_befores.append(vb_rows[0])
            variation_payloads.append(_woo_variation_to_cloud_payload(variation, product, session, settings))

        if variation_befores:
            write_snapshot(session, OperationSnapshot(
                operation_id=operation_id,
                module="woocommerce_import",
                action="admin_import_single_product_variations_update",
                entity_type="product_variations",
                entity_id=str(product_id),
                before_data=_json_safe({"product_id": product_id, "variations": variation_befores}),
                reason="v11: snapshot antes de actualizar variaciones WooCommerce importadas a Supabase.",
            ))

        if variation_payloads:
            session.client.table("product_variations").upsert(variation_payloads, on_conflict="woo_id").execute()

        event = AuditEvent(
            operation_id=operation_id,
            module="woocommerce_import",
            action="admin_import_single_product_to_supabase",
            status="OK",
            severity="INFO",
            entity_type="product",
            entity_id=str(product_id),
            before_data=_json_safe({"product": product_before, "variations": variation_befores}),
            after_data=_json_safe({
                "product": {"woo_id": product_id, "name": product.get("name"), "type": product.get("type"), "price": product.get("price")},
                "variations_imported": len(variation_payloads),
                "variation_ids": [v.get("woo_id") for v in variation_payloads],
            }),
            message="Admin importó un producto WooCommerce concreto a Supabase. WooCommerce solo fue leído; no se publicó ningún cambio.",
        )
        write_audit_event(session, event, settings)
        return {
            "operation_id": operation_id,
            "product_id": product_id,
            "name": product.get("name"),
            "type": product.get("type"),
            "price": product.get("price"),
            "variations_imported": len(variation_payloads),
            "variation_ids": [v.get("woo_id") for v in variation_payloads],
            "updated_existing_product": product_before is not None,
            "updated_existing_variations": len(variation_befores),
        }
    except (CloudAuditError, WooCommerceError):
        raise
    except Exception as exc:
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="woocommerce_import",
                action="admin_import_single_product_to_supabase_failed",
                status="ERROR",
                severity="ERROR",
                entity_type="product",
                entity_id=str(woo_id or query or "unknown"),
                before_data=_json_safe({"product": product_before, "variations": variation_befores}),
                after_data=None,
                message="Falló la importación quirúrgica de producto WooCommerce a Supabase.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise


def run_cloud_import_woocommerce_product(woo_id: int | None = None, query: str | None = None) -> int:
    try:
        session, settings = _login_from_console()
        result = import_single_woocommerce_product_to_supabase(session, woo_id=woo_id, query=query, settings=settings)
    except (SupabaseAuthError, CloudAuditError, WooCommerceError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Producto WooCommerce importado a Supabase correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"producto: {result['product_id']} · {result['name']}")
    print(f"tipo: {result['type']} · precio: {result['price']}")
    print(f"variaciones importadas/actualizadas: {result['variations_imported']}")
    if result["variation_ids"]:
        print("variation_ids: " + ", ".join(str(v) for v in result["variation_ids"]))
    print("WooCommerce solo fue leído. No se publicó ningún cambio.")
    return 0


# ================================
# v11.2 - Preview protegido de publicación WooCommerce
# ================================

def _safe_money(value: Any) -> float | None:
    return _money_or_none(value)


def _proposal_item_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    return woo_publish_service.proposal_item_snapshot(proposal)
    source = proposal.get("source_row") or {}
    snap = source.get("item_snapshot") or {}
    return snap if isinstance(snap, dict) else {}


def _fetch_cloud_item_for_proposal(session, proposal: dict[str, Any]) -> dict[str, Any]:
    return woo_publish_service.fetch_cloud_item_for_proposal(session, proposal)
    kind = (proposal.get("item_kind") or "").strip().lower()
    woo_id = int(proposal.get("item_woo_id") or proposal.get("local_id") or 0)
    if kind in {"product", "variation"} and woo_id:
        try:
            return _fetch_cloud_item_for_price(session, kind, woo_id)
        except Exception:
            pass
    snap = _proposal_item_snapshot(proposal)
    if snap:
        if kind == "variation" and "name" not in snap:
            snap["name"] = f"{snap.get('parent_name')} · {snap.get('attributes_label') or 'variación'}"
        return snap
    return {
        "woo_id": woo_id,
        "name": proposal.get("name") or f"{kind} {woo_id}",
        "type": "variation" if kind == "variation" else "product",
        "price": proposal.get("old_price"),
    }


def _fetch_woo_item_readonly(client: WooCommerceClient, session, proposal: dict[str, Any]) -> dict[str, Any] | None:
    return woo_publish_service.fetch_woo_item_readonly(client, session, proposal)
    """Lee WooCommerce sin modificar nada para construir preview de publicación."""
    kind = (proposal.get("item_kind") or "").strip().lower()
    woo_id = int(proposal.get("item_woo_id") or proposal.get("local_id") or 0)
    if not woo_id:
        return None
    if kind == "product":
        return client.get(f"products/{woo_id}").json()
    if kind == "variation":
        cloud_item = _fetch_cloud_item_for_proposal(session, proposal)
        parent_id = cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id")
        if not parent_id:
            # Fallback: busca la variación en Supabase por woo_id para extraer parent_woo_id.
            resp = session.client.table("product_variations").select("parent_woo_id").eq("woo_id", woo_id).limit(1).execute()
            rows = getattr(resp, "data", None) or []
            parent_id = rows[0].get("parent_woo_id") if rows else None
        if not parent_id:
            raise CloudAuditError(f"No se pudo determinar parent_woo_id para la variación {woo_id}.")
        return client.get(f"products/{int(parent_id)}/variations/{woo_id}").json()
    raise CloudAuditError("La propuesta no tiene item_kind válido para WooCommerce.")


def _fetch_approved_price_proposals(session, *, proposal_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    return woo_publish_service.fetch_approved_price_proposals(session, proposal_id=proposal_id, limit=limit)
    query = session.client.table("price_change_proposals").select("*").eq("status", "approved").order("reviewed_at", desc=True).limit(max(1, min(int(limit or 20), 50)))
    if proposal_id:
        query = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1)
    resp = query.execute()
    rows = getattr(resp, "data", None) or []
    # Evita arrastrar propuestas de test en el preview real.
    filtered = []
    for row in rows:
        source = row.get("source_row") or {}
        if source.get("test") is True or str(row.get("name") or "").startswith("TEST_"):
            continue
        filtered.append(row)
    return filtered


def preview_woocommerce_publish(session, *, proposal_id: str | None = None, limit: int = 20, settings: Settings | None = None) -> dict[str, Any]:
    return woo_publish_service.preview_woocommerce_publish(session, proposal_id=proposal_id, limit=limit, settings=settings)
    """Preview de publicación WooCommerce. Lee Woo y Supabase, no ejecuta PUT.

    Devuelve filas con estado OK/WARNING/ERROR y un resumen. Es la antesala de una
    publicación futura, pero aquí WooCommerce solo se consulta.
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede generar preview de publicación WooCommerce.")
    operation_id = new_operation_id("WOOPREVIEW")
    client = WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
    proposals = _fetch_approved_price_proposals(session, proposal_id=proposal_id, limit=limit)
    rows: list[dict[str, Any]] = []
    counts = {"OK": 0, "WARNING": 0, "ERROR": 0}

    try:
        for proposal in proposals:
            kind = (proposal.get("item_kind") or "").strip().lower()
            new_price = _safe_money(proposal.get("new_price"))
            cloud_item = _fetch_cloud_item_for_proposal(session, proposal)
            validation = _price_safety_preview(cloud_item, kind, new_price, settings)
            woo_data = None
            woo_price = None
            woo_regular_price = None
            woo_sale_price = None
            woo_error = None
            messages = list(validation.get("messages") or [])
            status = validation.get("status") or "OK"
            try:
                woo_data = _fetch_woo_item_readonly(client, session, proposal)
                woo_price = _safe_money(_short_row_value(woo_data or {}, "price", "regular_price", "sale_price"))
                woo_regular_price = _safe_money((woo_data or {}).get("regular_price"))
                woo_sale_price = _safe_money((woo_data or {}).get("sale_price"))
                if woo_sale_price is not None and woo_sale_price > 0:
                    messages.append("WARNING: WooCommerce tiene sale_price activo. La publicación cambiará regular_price, pero el precio visible podría seguir siendo el sale_price.")
                    if status != "ERROR":
                        status = "WARNING"
                # Seguridad extra: compara con Woo actual, no solo con Supabase.
                if woo_price is None or woo_price <= 0:
                    messages.append("WARNING: WooCommerce devuelve precio actual vacío/0 para este item vendible. Se permite continuar, pero no se puede calcular porcentaje de bajada frente a Woo.")
                    if status != "ERROR":
                        status = "WARNING"
                elif new_price is not None and new_price > 0:
                    drop = ((woo_price - new_price) / woo_price) * 100 if new_price < woo_price else 0.0
                    if drop >= settings.price_drop_block_percent:
                        messages.append(f"ERROR: frente a WooCommerce actual, la bajada sería {drop:.2f}% y supera el bloqueo ({settings.price_drop_block_percent:.2f}%).")
                        status = "ERROR"
                    elif drop >= settings.price_drop_warning_percent and status != "ERROR":
                        messages.append(f"WARNING: frente a WooCommerce actual, la bajada sería {drop:.2f}% y requiere revisión.")
                        status = "WARNING"
                old_price_proposal = _safe_money(proposal.get("old_price"))
                if old_price_proposal is not None and woo_price is not None and abs(old_price_proposal - woo_price) > 0.009:
                    msg = f"WARNING: el precio actual en WooCommerce ({woo_price:.2f}) no coincide con el old_price de la propuesta ({old_price_proposal:.2f})."
                    messages.append(msg)
                    if status == "OK":
                        status = "WARNING"
            except Exception as exc:
                woo_error = str(exc)
                messages.append(f"ERROR: no se pudo leer WooCommerce para este item: {exc}")
                status = "ERROR"

            counts[status] = counts.get(status, 0) + 1
            delta_vs_woo = (new_price - woo_price) if (new_price is not None and woo_price is not None) else None
            delta_pct_vs_woo = (delta_vs_woo / woo_price * 100) if (delta_vs_woo is not None and woo_price) else None
            rows.append({
                "status": status,
                "proposal_id": proposal.get("id"),
                "item_kind": kind,
                "item_woo_id": proposal.get("item_woo_id"),
                "name": proposal.get("name") or cloud_item.get("name") or cloud_item.get("parent_name"),
                "proposal_status": proposal.get("status"),
                "old_price_proposal": proposal.get("old_price"),
                "new_price": new_price,
                "cloud_current_price": validation.get("current_price"),
                "woo_current_price": woo_price,
                "woo_regular_price": woo_regular_price,
                "woo_sale_price": woo_sale_price,
                "delta_vs_woo": delta_vs_woo,
                "delta_pct_vs_woo": delta_pct_vs_woo,
                "messages": messages,
                "woo_error": woo_error,
            })

        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_preview_woocommerce_publish",
            status="OK",
            severity="INFO" if counts.get("ERROR", 0) == 0 else "WARNING",
            entity_type="price_change_proposals",
            entity_id=str(proposal_id or "approved_batch"),
            before_data=None,
            after_data=_json_safe({"rows": rows, "counts": counts}),
            message="v11.2: preview de publicación WooCommerce generado. WooCommerce solo fue leído; no se publicó ningún cambio.",
        ), settings)
        return {"operation_id": operation_id, "rows": rows, "counts": counts, "proposal_count": len(proposals)}
    except Exception as exc:
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="woocommerce_publish",
                action="admin_preview_woocommerce_publish_failed",
                status="ERROR",
                severity="ERROR",
                entity_type="price_change_proposals",
                entity_id=str(proposal_id or "approved_batch"),
                message="Falló el preview de publicación WooCommerce.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise


def format_woocommerce_publish_preview(result: dict[str, Any]) -> str:
    return woo_publish_service.format_woocommerce_publish_preview(result)
    rows = result.get("rows") or []
    counts = result.get("counts") or {}
    lines = [
        "PREVIEW PUBLICACIÓN WOOCOMMERCE",
        "=" * 44,
        f"operation_id: {result.get('operation_id')}",
        "WooCommerce solo fue leído. NO se publicó ningún cambio.",
        f"Propuestas evaluadas: {len(rows)} · OK={counts.get('OK',0)} · WARNING={counts.get('WARNING',0)} · ERROR={counts.get('ERROR',0)}",
        "",
    ]
    if not rows:
        lines.append("No hay propuestas reales aprobadas para publicar.")
        return "\n".join(lines)
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}. {row.get('status')} · [{row.get('item_kind')}] {row.get('item_woo_id')} · {row.get('name')}")
        lines.append(f"   propuesta_id: {row.get('proposal_id')}")
        lines.append(f"   precio Woo actual: {row.get('woo_current_price')} · propuesto: {row.get('new_price')}")
        if row.get("delta_vs_woo") is not None:
            lines.append(f"   diferencia vs Woo: {row.get('delta_vs_woo'):.2f} ({row.get('delta_pct_vs_woo'):.2f}%)")
        for msg in row.get("messages") or []:
            prefix = "   - "
            lines.append(prefix + msg)
        lines.append("")
    if counts.get("ERROR", 0):
        lines.append("BLOQUEO: hay errores rojos. No se debe publicar hasta corregirlos.")
    elif counts.get("WARNING", 0):
        lines.append("AVISO: hay warnings amarillos. Revisión admin obligatoria antes de publicar en una futura fase.")
    else:
        lines.append("Preview limpio: listo para preparar la fase futura de confirmación escrita, todavía sin publicar.")
    return "\n".join(lines)


def run_cloud_woocommerce_publish_preview(limit: int = 20, proposal_id: str = "") -> int:
    try:
        session, settings = _login_from_console()
        result = preview_woocommerce_publish(session, proposal_id=proposal_id or None, limit=limit, settings=settings)
    except (SupabaseAuthError, CloudAuditError, WooCommerceError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_woocommerce_publish_preview(result))
    return 0



def _format_publish_row_for_confirm(row: dict[str, Any]) -> str:
    return woo_publish_service.format_publish_row_for_confirm(row)
    lines = [
        f"{row.get('status')} · [{row.get('item_kind')}] {row.get('item_woo_id')} · {row.get('name')}",
        f"propuesta_id: {row.get('proposal_id')}",
        f"precio Woo actual: {row.get('woo_current_price')} · propuesto: {row.get('new_price')}",
    ]
    if row.get("delta_vs_woo") is not None:
        lines.append(f"diferencia vs Woo: {row.get('delta_vs_woo'):.2f} ({row.get('delta_pct_vs_woo'):.2f}%)")
    for msg in row.get("messages") or []:
        lines.append("- " + msg)
    return "\n".join(lines)


def publish_woocommerce_price(session, *, proposal_id: str, confirm: str = "", acknowledge_warnings: bool = False, settings: Settings | None = None) -> dict[str, Any]:
    return woo_publish_service.publish_woocommerce_price(session, proposal_id=proposal_id, confirm=confirm, acknowledge_warnings=acknowledge_warnings, settings=settings)
    """Publica UNA propuesta aprobada en WooCommerce con triple candado.

    Seguridad v11.4:
    - solo admin
    - exige proposal_id concreto
    - exige --confirm PUBLICAR
    - genera preview justo antes
    - bloquea ERROR
    - WARNING exige --ack-woo-warning
    - actualiza WooCommerce con PUT solo después de pasar esas validaciones
    - marca la propuesta como published en Supabase y actualiza el espejo cloud del precio
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede publicar cambios en WooCommerce.")
    proposal_id = (proposal_id or "").strip()
    if not proposal_id:
        raise CloudAuditError("Debes indicar --proposal-id. En v11.4 solo se publica una propuesta por operación.")
    if (confirm or "").strip().upper() != "PUBLICAR":
        raise CloudAuditError("Publicación bloqueada. Debes repetir con --confirm PUBLICAR.")

    operation_id = new_operation_id("WOOPUBLISH")
    lock_key = f"woocommerce_publish:{proposal_id}"
    lock_acquired = False
    publishing_marked = False
    woo_written = False
    before_bundle: dict[str, Any] | None = None
    try:
        acquire_system_lock(
            session,
            lock_key,
            details=f"Publicacion WooCommerce proposal_id={proposal_id}",
            ttl_minutes=15,
            settings=settings,
        )
        lock_acquired = True
        client = WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
        preview = preview_woocommerce_publish(session, proposal_id=proposal_id, limit=1, settings=settings)
        rows = preview.get("rows") or []
        if not rows:
            raise CloudAuditError("No se encontró una propuesta aprobada real para ese proposal_id.")
        row = rows[0]
        if row.get("status") == "ERROR":
            raise CloudAuditError("Publicación bloqueada por errores rojos en preview:\n" + _format_publish_row_for_confirm(row))
        if row.get("status") == "WARNING" and not acknowledge_warnings:
            raise CloudAuditError(
                "Publicación requiere confirmación de warnings amarillos. Revisa el preview y repite con --ack-woo-warning.\n"
                + _format_publish_row_for_confirm(row)
            )

        resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
        proposals = getattr(resp, "data", None) or []
        if not proposals:
            raise CloudAuditError("No se encontró la propuesta en Supabase.")
        proposal = proposals[0]
        if proposal.get("status") != "approved":
            raise CloudAuditError(f"La propuesta no está approved. Estado actual: {proposal.get('status')}")

        publishing_resp = session.client.table("price_change_proposals").update({
            "status": "publishing",
            "error_message": None,
        }).eq("id", proposal_id).eq("status", "approved").execute()
        if not (getattr(publishing_resp, "data", None) or []):
            raise CloudAuditError("No se pudo marcar la propuesta como publishing. Revisa si otro proceso la modifico.")
        publishing_marked = True

        kind = (proposal.get("item_kind") or "").strip().lower()
        woo_id = int(proposal.get("item_woo_id") or proposal.get("local_id") or 0)
        new_price = _safe_money(proposal.get("new_price"))
        if new_price is None or new_price <= 0:
            raise CloudAuditError("Precio propuesto inválido. Debe ser mayor que 0.")

        cloud_item = _fetch_cloud_item_for_proposal(session, proposal)
        woo_before = _fetch_woo_item_readonly(client, session, proposal)
        before_bundle = {
            "proposal": _json_safe(proposal),
            "preview_row": _json_safe(row),
            "cloud_item": _json_safe(cloud_item),
            "woo_before": _json_safe(woo_before),
        }
        write_snapshot(session, OperationSnapshot(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_woocommerce_price",
            entity_type="price_change_proposal",
            entity_id=str(proposal_id),
            before_data=_json_safe(before_bundle),
            reason="v11.5: snapshot antes de publicar precio en WooCommerce.",
        ))

        if kind == "product":
            woo_after = client.update_product_price(woo_id, float(new_price))
            woo_written = True
            session.client.table("products").update({
                "price": f"{new_price:.2f}",
                "regular_price": f"{new_price:.2f}",
            }).eq("woo_id", woo_id).execute()
        elif kind == "variation":
            parent_id = cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id")
            if not parent_id:
                raise CloudAuditError(f"No se pudo determinar parent_woo_id para la variación {woo_id}.")
            woo_after = client.update_variation_price(int(parent_id), woo_id, float(new_price))
            woo_written = True
            session.client.table("product_variations").update({
                "price": f"{new_price:.2f}",
                "regular_price": f"{new_price:.2f}",
            }).eq("woo_id", woo_id).execute()
        else:
            raise CloudAuditError("item_kind inválido para publicación WooCommerce.")

        now = datetime.now(timezone.utc).isoformat()
        proposal_source = proposal.get("source_row") or {}
        proposal_update = {
            "status": "published",
            "published_by": session.user_id,
            "published_at": now,
            "notes": (proposal.get("notes") or "") + f"\n[v11.5] Publicado en WooCommerce por admin. operation_id={operation_id}",
            "source_row": {
                **proposal_source,
                "woo_publish": True,
                "publish_operation_id": operation_id,
                "published_by_email": session.email,
                "published_machine": settings.machine_name,
                "woo_before": _json_safe(woo_before),
                "woo_after": _json_safe(woo_after),
                "acknowledged_woo_warnings": bool(acknowledge_warnings),
            },
        }
        try:
            update_resp = session.client.table("price_change_proposals").update(proposal_update).eq("id", proposal_id).execute()
        except Exception as exc:
            # v11.5: defensa ante esquemas Supabase antiguos.
            # En algunos proyectos la tabla price_change_proposals no tenía published_by todavía.
            # Si WooCommerce ya fue actualizado, no dejamos la operación medio fantasma:
            # reintentamos marcando la propuesta como published y guardando el autor en source_row.
            msg = str(exc)
            if "published_by" in msg and ("schema cache" in msg or "PGRST204" in msg):
                fallback_update = dict(proposal_update)
                fallback_update.pop("published_by", None)
                fallback_source = dict(fallback_update.get("source_row") or {})
                fallback_source["published_by_missing_column_fallback"] = True
                fallback_source["published_by_user_id"] = session.user_id
                fallback_update["source_row"] = fallback_source
                update_resp = session.client.table("price_change_proposals").update(fallback_update).eq("id", proposal_id).execute()
                proposal_update = fallback_update
            else:
                raise
        updated_proposal = (getattr(update_resp, "data", None) or [{**proposal, **proposal_update}])[0]

        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_woocommerce_price",
            status="OK",
            severity="CRITICAL" if row.get("status") == "WARNING" else "INFO",
            entity_type="price_change_proposal",
            entity_id=str(proposal_id),
            before_data=_json_safe(before_bundle),
            after_data=_json_safe({"proposal": updated_proposal, "woo_after": woo_after}),
            message="v11.5: precio publicado en WooCommerce con confirmación escrita. Supabase actualizado.",
        ), settings)
        return {
            "operation_id": operation_id,
            "proposal": updated_proposal,
            "preview_row": row,
            "woo_before": woo_before,
            "woo_after": woo_after,
            "new_price": new_price,
            "item_kind": kind,
            "woo_id": woo_id,
        }
    except CloudAuditError:
        if publishing_marked and not woo_written:
            try:
                session.client.table("price_change_proposals").update({"status": "approved"}).eq("id", proposal_id).eq("status", "publishing").execute()
            except Exception:
                pass
        raise
    except Exception as exc:
        if publishing_marked:
            try:
                failure_status = "error" if woo_written else "approved"
                session.client.table("price_change_proposals").update({
                    "status": failure_status,
                    "error_message": str(exc)[:500],
                }).eq("id", proposal_id).eq("status", "publishing").execute()
            except Exception:
                pass
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="woocommerce_publish",
                action="admin_publish_woocommerce_price_failed",
                status="ERROR",
                severity="CRITICAL",
                entity_type="price_change_proposal",
                entity_id=str(proposal_id),
                before_data=_json_safe(before_bundle),
                message="Falló v11.5 publicación de precio en WooCommerce.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise
    finally:
        if lock_acquired:
            release_system_lock(session, lock_key, status="released")


def format_woocommerce_publish_result(result: dict[str, Any]) -> str:
    return woo_publish_service.format_woocommerce_publish_result(result)
    row = result.get("preview_row") or {}
    lines = [
        "PUBLICACIÓN WOOCOMMERCE COMPLETADA",
        "=" * 44,
        f"operation_id: {result.get('operation_id')}",
        f"item: [{result.get('item_kind')}] {result.get('woo_id')} · {row.get('name')}",
        f"propuesta_id: {(result.get('proposal') or {}).get('id')}",
        f"nuevo regular_price publicado: {result.get('new_price'):.2f}",
        "Supabase fue actualizado y la propuesta quedó como published.",
        "Caja negra: audit_log + operation_snapshot generados.",
    ]
    if row.get("status") == "WARNING":
        lines.append("AVISO: se publicó con warnings reconocidos explícitamente por admin.")
    return "\n".join(lines)


def run_cloud_woocommerce_publish_execute(proposal_id: str, confirm: str = "", ack_woo_warning: bool = False) -> int:
    try:
        session, settings = _login_from_console()
        result = publish_woocommerce_price(
            session,
            proposal_id=proposal_id,
            confirm=confirm,
            acknowledge_warnings=ack_woo_warning,
            settings=settings,
        )
    except (SupabaseAuthError, CloudAuditError, WooCommerceError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2
    print(format_woocommerce_publish_result(result))
    return 0

def run_cloud_operational_status() -> int:
    try:
        session, _settings = _login_from_console()
        print(collect_operational_cloud_status(session))
        return 0
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2


def run_migrate_sqlite_to_supabase_dry_run() -> int:
    settings = load_settings()
    infos = inspect_local_sqlite(settings)
    print(format_local_sqlite_dry_run(infos))
    return 0


def run_cloud_test_constant() -> int:
    try:
        session, settings = _login_from_console()
        result = test_business_constant_change(session, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Prueba de constante operativa creada/actualizada correctamente.")
    print(f"operation_id: {result['operation_id']}")
    print(f"action: {result['action']}")
    print("Tabla: business_constants")
    print("Clave: TEST_FACTOR_SEGURIDAD")
    print("También se registró audit_log y, si ya existía valor previo, operation_snapshot.")
    return 0

# =====================================================
# v12.3 - Inventario real interno Supabase (sin WooCommerce)
# =====================================================

def _coerce_optional_float(value: Any) -> float | None:
    return inventory_service.coerce_optional_float(value)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
        if value == '':
            return None
    return float(value)


def search_cloud_inventory_items(session, query: str, limit: int = 25) -> list[dict[str, Any]]:
    return inventory_service.search_cloud_inventory_items(session, query, limit)
    """Busca items reales de inventory_items en Supabase.

    No toca WooCommerce. Devuelve filas operativas internas.
    """
    q = (query or '').strip()
    if not q:
        return []
    limit = max(1, min(int(limit or 25), 100))
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(data: list[dict[str, Any]] | None) -> None:
        for row in data or []:
            item_id = row.get('item_id')
            try:
                key = int(item_id)
            except Exception:
                key = hash(str(row))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    cols = 'item_id,name,family,subgroup,size,store_stock,warehouse_stock,woo_item_kind,woo_id,woo_name,woo_sku,woo_link_status,updated_at'
    # Búsqueda exacta numérica primero.
    if q.isdigit() or (q.startswith('-') and q[1:].isdigit()):
        n = int(q)
        for col in ('item_id', 'woo_id'):
            try:
                resp = session.client.table('inventory_items').select(cols).eq(col, n).limit(limit).execute()
                add(getattr(resp, 'data', None))
            except Exception:
                pass
    # Búsqueda textual por campos principales. Varias queries para evitar depender de or_ con escaping.
    pattern = f'%{q}%'
    for col in ('name', 'woo_name', 'woo_sku', 'heca_reference'):
        if len(rows) >= limit:
            break
        try:
            resp = session.client.table('inventory_items').select(cols).ilike(col, pattern).limit(limit).execute()
            add(getattr(resp, 'data', None))
        except Exception:
            continue
    return rows[:limit]


def format_cloud_inventory_search(rows: list[dict[str, Any]]) -> str:
    return inventory_service.format_cloud_inventory_search(rows)
    lines = [
        'RESULTADOS INVENTARIO SUPABASE',
        '=' * 40,
        'Copia item_id para actualizar inventario interno. WooCommerce no se toca.',
        '',
    ]
    if not rows:
        lines.append('Sin resultados.')
        return '\n'.join(lines)
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. item_id={row.get('item_id')} · {row.get('name') or row.get('woo_name') or '-'}")
        lines.append(f"   familia: {row.get('family') or '-'} · grupo: {row.get('subgroup') or '-'} · tamaño: {row.get('size') or '-'}")
        lines.append(f"   stock tienda: {row.get('store_stock')} · almacén: {row.get('warehouse_stock')}")
        lines.append(f"   Woo: [{row.get('woo_item_kind') or '-'}] {row.get('woo_id') or '-'} · {row.get('woo_name') or '-'} · link: {row.get('woo_link_status') or '-'}")
    return '\n'.join(lines)


def _fetch_inventory_item_by_id(session, item_id: int) -> dict[str, Any] | None:
    return inventory_service.fetch_inventory_item_by_id(session, item_id)
    resp = session.client.table('inventory_items').select('*').eq('item_id', int(item_id)).limit(1).execute()
    rows = getattr(resp, 'data', None) or []
    return rows[0] if rows else None


def preview_internal_inventory_update(session, item_id: int, store_stock: Any = None, warehouse_stock: Any = None, notes: str = '') -> dict[str, Any]:
    return inventory_service.preview_internal_inventory_update(session, item_id, store_stock, warehouse_stock, notes)
    before = _fetch_inventory_item_by_id(session, int(item_id))
    if before is None:
        raise CloudAuditError(f'No existe inventory_items.item_id={item_id} en Supabase.')
    new_store = _coerce_optional_float(store_stock)
    new_warehouse = _coerce_optional_float(warehouse_stock)
    if new_store is None and new_warehouse is None:
        raise CloudAuditError('Indica al menos stock tienda o stock almacén.')
    if new_store is not None and new_store < 0:
        raise CloudAuditError('Stock tienda no puede ser negativo.')
    if new_warehouse is not None and new_warehouse < 0:
        raise CloudAuditError('Stock almacén no puede ser negativo.')
    after = dict(before)
    if new_store is not None:
        after['store_stock'] = new_store
    if new_warehouse is not None:
        after['warehouse_stock'] = new_warehouse
    if notes:
        existing_notes = before.get('notes') or ''
        after['notes'] = (existing_notes + '\n' if existing_notes else '') + notes
    return {
        'item_id': int(item_id),
        'before': before,
        'after': after,
        'store_change': None if new_store is None else new_store - float(before.get('store_stock') or 0),
        'warehouse_change': None if new_warehouse is None else new_warehouse - float(before.get('warehouse_stock') or 0),
        'notes': notes,
    }


def format_internal_inventory_preview(preview: dict[str, Any]) -> str:
    return inventory_service.format_internal_inventory_preview(preview)
    b = preview.get('before') or {}
    a = preview.get('after') or {}
    lines = [
        'PREVIEW CAMBIO INVENTARIO INTERNO',
        '=' * 44,
        'No toca WooCommerce. Solo actualiza Supabase si confirmas.',
        '',
        f"Item ID: {preview.get('item_id')}",
        f"Nombre: {b.get('name') or b.get('woo_name') or '-'}",
        f"Woo: [{b.get('woo_item_kind') or '-'}] {b.get('woo_id') or '-'} · {b.get('woo_name') or '-'}",
        '',
        f"Stock tienda: {b.get('store_stock')} → {a.get('store_stock')}" + (f"  Δ {preview.get('store_change'):+.2f}" if preview.get('store_change') is not None else ''),
        f"Stock almacén: {b.get('warehouse_stock')} → {a.get('warehouse_stock')}" + (f"  Δ {preview.get('warehouse_change'):+.2f}" if preview.get('warehouse_change') is not None else ''),
    ]
    if preview.get('notes'):
        lines.extend(['', f"Nota a añadir: {preview.get('notes')}"])
    lines.extend(['', 'Se generará operation_snapshot + audit_log.'])
    return '\n'.join(lines)


def update_internal_inventory_item(session, item_id: int, store_stock: Any = None, warehouse_stock: Any = None, notes: str = '', settings: Settings | None = None) -> dict[str, Any]:
    return inventory_service.update_internal_inventory_item(session, item_id, store_stock, warehouse_stock, notes, settings)
    settings = settings or load_settings()
    preview = preview_internal_inventory_update(session, item_id, store_stock, warehouse_stock, notes)
    before = preview['before']
    after = preview['after']
    operation_id = new_operation_id('INVREAL')
    now = datetime.now(timezone.utc).isoformat()

    snapshot = OperationSnapshot(
        operation_id=operation_id,
        module='inventory_items',
        action='internal_inventory_update',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        reason='Cambio real interno de inventario en Supabase antes de aplicar actualización.',
    )
    write_snapshot(session, snapshot)

    update_payload: dict[str, Any] = {
        'updated_at': now,
        'updated_by': session.user_id,
        'source_row': {
            'operation_id': operation_id,
            'updated_by_email': session.email,
            'role': session.role,
            'machine': settings.machine_name,
            'inventory_change': True,
            'note': 'Cambio interno Supabase. WooCommerce no fue tocado.',
        },
    }
    if after.get('store_stock') != before.get('store_stock'):
        update_payload['store_stock'] = after.get('store_stock')
    if after.get('warehouse_stock') != before.get('warehouse_stock'):
        update_payload['warehouse_stock'] = after.get('warehouse_stock')
    if after.get('notes') != before.get('notes'):
        update_payload['notes'] = after.get('notes')

    resp = session.client.table('inventory_items').update(update_payload).eq('item_id', int(item_id)).execute()
    written_rows = getattr(resp, 'data', None) or []
    written = written_rows[0] if written_rows else {**before, **update_payload}

    event = AuditEvent(
        operation_id=operation_id,
        module='inventory_items',
        action='internal_inventory_update',
        status='OK',
        severity='INFO',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        after_data=_json_safe(written),
        message='Inventario interno actualizado en Supabase. WooCommerce no fue tocado.',
    )
    write_audit_event(session, event, settings)
    return {'operation_id': operation_id, 'before': before, 'after': written, 'preview': preview}


def run_cloud_search_inventory(query: str, limit: int = 25) -> int:
    try:
        session, _settings = _login_from_console()
        rows = search_cloud_inventory_items(session, query, limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print(format_cloud_inventory_search(rows))
    return 0


def run_cloud_inventory_update_internal(item_id: int, store_stock: str = '', warehouse_stock: str = '', notes: str = '', execute: bool = False) -> int:
    try:
        session, settings = _login_from_console()
        preview = preview_internal_inventory_update(session, item_id, store_stock or None, warehouse_stock or None, notes)
        print(format_internal_inventory_preview(preview))
        if not execute:
            print('\nPREVIEW ONLY: no se aplicó nada. Repite con --execute para actualizar Supabase.')
            return 0
        typed = input('\nEscribe APLICAR para confirmar cambio interno de inventario: ').strip().upper()
        if typed != 'APLICAR':
            print('Cancelado. No se aplicó nada.')
            return 1
        result = update_internal_inventory_item(session, item_id, store_stock or None, warehouse_stock or None, notes, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print('\nCAMBIO INVENTARIO INTERNO APLICADO')
    print('=' * 42)
    print(f"operation_id: {result['operation_id']}")
    print(f'item_id: {item_id}')
    print('Supabase actualizado. WooCommerce no fue tocado.')
    print('Caja negra: audit_log + operation_snapshot generados.')
    return 0

# =====================================================
# v12.4 · Rollback lógico desde operation_snapshot
# =====================================================

ROLLBACK_ENTITY_SPECS = {
    'inventory_item': {
        'table': 'inventory_items',
        'key': 'item_id',
        'label': 'Inventario interno',
        'safe_note': 'Solo revierte Supabase. WooCommerce no se toca.',
    },
    'price_change_proposal': {
        'table': 'price_change_proposals',
        'key': 'id',
        'label': 'Propuesta de precio',
        'safe_note': 'Solo revierte el estado/datos internos de la propuesta en Supabase. WooCommerce no se toca.',
    },
    'business_constant': {
        'table': 'business_constants',
        'key': 'key',
        'label': 'Constante del negocio',
        'safe_note': 'Revierte una constante en Supabase. Revisa cálculos después si era una constante real.',
    },
}


def _require_admin_role(session) -> None:
    if (session.role or '').strip().lower() != 'admin':
        raise CloudAuditError('Solo admin puede ejecutar esta operación.')


def _fetch_snapshot_by_operation_id(session, operation_id: str) -> dict[str, Any]:
    op = (operation_id or '').strip()
    if not op:
        raise CloudAuditError('Indica operation_id del snapshot.')
    # v12.4: preferimos RPC admin para evitar falsos bloqueos si el subcliente REST
    # pierde el token. Si el SQL de v12.4 aún no existe, se usa fallback directo.
    try:
        resp = session.client.rpc(
            'futonhub_read_snapshot_by_operation_id',
            {'p_user_id': session.user_id, 'p_operation_id': op},
        ).execute()
        rows = getattr(resp, 'data', None) or []
        if rows:
            return rows[0]
    except Exception:
        pass
    resp = (
        session.client.table('operation_snapshots')
        .select('*')
        .eq('operation_id', op)
        .order('created_at', desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, 'data', None) or []
    if not rows:
        raise CloudAuditError(f'No se encontró operation_snapshot con operation_id={op}.')
    return rows[0]


def list_rollback_candidates(session, limit: int = 30) -> list[dict[str, Any]]:
    _require_admin_role(session)
    limit = max(1, min(int(limit or 30), 100))
    resp = (
        session.client.table('operation_snapshots')
        .select('id,created_at,operation_id,module,action,entity_type,entity_id,reason')
        .order('created_at', desc=True)
        .limit(limit)
        .execute()
    )
    rows = getattr(resp, 'data', None) or []
    supported = set(ROLLBACK_ENTITY_SPECS)
    for row in rows:
        row['rollback_supported'] = (row.get('entity_type') in supported)
    return rows


def format_rollback_candidates(rows: list[dict[str, Any]]) -> str:
    lines = [
        'SNAPSHOTS CANDIDATOS A ROLLBACK',
        '=' * 48,
        'Solo admin. Preview obligatorio antes de revertir. WooCommerce no se toca.',
        '',
    ]
    if not rows:
        lines.append('Sin snapshots visibles.')
        return '\n'.join(lines)
    for i, row in enumerate(rows, start=1):
        support = 'OK' if row.get('rollback_supported') else 'NO SOPORTADO'
        lines.append(
            f"{i}. {support} · {row.get('created_at') or ''} · {row.get('operation_id') or ''}"
        )
        lines.append(
            f"   {row.get('module') or ''}.{row.get('action') or ''} · {row.get('entity_type') or ''}:{row.get('entity_id') or ''}"
        )
        if row.get('reason'):
            lines.append(f"   {row.get('reason')}")
    return '\n'.join(lines)


def _rollback_target_from_snapshot(snapshot: dict[str, Any]) -> tuple[dict[str, Any], str, str, Any]:
    return service_rollback_target_from_snapshot(snapshot)
    entity_type = snapshot.get('entity_type')
    spec = ROLLBACK_ENTITY_SPECS.get(entity_type)
    if not spec:
        raise CloudAuditError(f"Rollback no soportado para entity_type={entity_type!r}.")
    before = snapshot.get('before_data') or {}
    if not isinstance(before, dict) or not before:
        raise CloudAuditError('El snapshot no contiene before_data válido para restaurar.')
    table = spec['table']
    key = spec['key']
    key_value = before.get(key)
    if key_value in (None, ''):
        # Fallback para snapshots antiguos que guardaron entity_id como identificador.
        key_value = snapshot.get('entity_id')
    if key_value in (None, ''):
        raise CloudAuditError(f'No se pudo determinar la clave {key} para restaurar {entity_type}.')
    return before, table, key, key_value


def _fetch_current_row_for_rollback(session, table: str, key: str, key_value: Any) -> dict[str, Any] | None:
    resp = session.client.table(table).select('*').eq(key, key_value).limit(1).execute()
    rows = getattr(resp, 'data', None) or []
    return rows[0] if rows else None


def _rollback_update_payload(table: str, key: str, before: dict[str, Any], *, user_id: str | None = None) -> dict[str, Any]:
    return service_rollback_update_payload(table, key, before, user_id=user_id)
    payload = dict(before)
    # Evita cambiar claves primarias o metadatos conflictivos. Dejamos created_at quieto.
    for protected in {'id', key, 'created_at'}:
        payload.pop(protected, None)
    # Marcamos trazabilidad del rollback si la tabla lo soporta.
    if table in {'inventory_items', 'business_constants'}:
        payload['updated_at'] = datetime.now(timezone.utc).isoformat()
    if user_id and table in {'inventory_items', 'business_constants'}:
        payload['updated_by'] = user_id
    return _json_safe(payload) or {}


def preview_rollback_from_snapshot(session, operation_id: str) -> dict[str, Any]:
    _require_admin_role(session)
    snapshot = _fetch_snapshot_by_operation_id(session, operation_id)
    before, table, key, key_value = _rollback_target_from_snapshot(snapshot)
    current = _fetch_current_row_for_rollback(session, table, key, key_value)
    if current is None:
        raise CloudAuditError(f'No existe fila actual en {table} donde {key}={key_value}. No se puede revertir automáticamente.')
    spec = ROLLBACK_ENTITY_SPECS.get(snapshot.get('entity_type')) or {}
    return {
        'snapshot': snapshot,
        'table': table,
        'key': key,
        'key_value': key_value,
        'before_data': before,
        'current_data': current,
        'entity_label': spec.get('label') or snapshot.get('entity_type'),
        'safe_note': spec.get('safe_note') or 'WooCommerce no se toca.',
    }


def _short_json_diff(before: dict[str, Any], current: dict[str, Any], max_items: int = 12) -> list[str]:
    return service_short_json_diff(before, current, max_items)
    keys = sorted(set(before.keys()) | set(current.keys()))
    lines: list[str] = []
    for key in keys:
        if before.get(key) != current.get(key):
            lines.append(f"{key}: actual={current.get(key)!r} → restaurar={before.get(key)!r}")
        if len(lines) >= max_items:
            remaining = len([k for k in keys if before.get(k) != current.get(k)]) - len(lines)
            if remaining > 0:
                lines.append(f"... y {remaining} cambio(s) más")
            break
    return lines


def format_rollback_preview(preview: dict[str, Any]) -> str:
    snap = preview.get('snapshot') or {}
    current = preview.get('current_data') or {}
    before = preview.get('before_data') or {}
    diff = _short_json_diff(before, current)
    lines = [
        'PREVIEW ROLLBACK DESDE SNAPSHOT',
        '=' * 48,
        'Solo admin. Revertirá datos internos en Supabase.',
        'WooCommerce NO se toca.',
        '',
        f"Snapshot operation_id: {snap.get('operation_id')}",
        f"Origen: {snap.get('module')}.{snap.get('action')}",
        f"Entidad: {snap.get('entity_type')}:{snap.get('entity_id')}",
        f"Tabla destino: {preview.get('table')} · {preview.get('key')}={preview.get('key_value')}",
        f"Tipo: {preview.get('entity_label')}",
        '',
        preview.get('safe_note') or 'WooCommerce no se toca.',
        '',
        'Cambios que se revertirían:',
    ]
    if diff:
        lines.extend(f'- {line}' for line in diff)
    else:
        lines.append('- No se detectan diferencias entre actual y snapshot previo.')
    lines.extend(['', 'Para ejecutar por consola: añade --execute --confirm REVERTIR'])
    return '\n'.join(lines)


def execute_rollback_from_snapshot(session, operation_id: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    preview = preview_rollback_from_snapshot(session, operation_id)
    snapshot = preview['snapshot']
    current = preview['current_data']
    before = preview['before_data']
    table = preview['table']
    key = preview['key']
    key_value = preview['key_value']
    rollback_operation_id = new_operation_id('ROLLBACK')

    # Snapshot del estado justo antes de revertir, para poder deshacer el rollback si hiciera falta.
    rollback_snapshot = OperationSnapshot(
        operation_id=rollback_operation_id,
        module='rollback',
        action='rollback_from_snapshot',
        entity_type=snapshot.get('entity_type') or 'unknown',
        entity_id=str(snapshot.get('entity_id') or key_value),
        before_data=_json_safe(current),
        reason=f"Estado actual antes de revertir usando snapshot {snapshot.get('operation_id')}. WooCommerce no se toca.",
    )
    write_snapshot(session, rollback_snapshot)

    payload = _rollback_update_payload(table, key, before, user_id=session.user_id)
    if not payload:
        raise CloudAuditError('No hay datos restaurables en el snapshot después de limpiar claves protegidas.')
    resp = session.client.table(table).update(payload).eq(key, key_value).execute()
    written_rows = getattr(resp, 'data', None) or []
    restored = written_rows[0] if written_rows else {**current, **payload}

    event = AuditEvent(
        operation_id=rollback_operation_id,
        module='rollback',
        action='rollback_from_snapshot',
        status='ROLLED_BACK',
        severity='WARNING',
        entity_type=snapshot.get('entity_type') or 'unknown',
        entity_id=str(snapshot.get('entity_id') or key_value),
        before_data=_json_safe(current),
        after_data=_json_safe(restored),
        message=f"Rollback interno ejecutado desde snapshot {snapshot.get('operation_id')}. WooCommerce no fue tocado.",
    )
    write_audit_event(session, event, settings)
    return {
        'operation_id': rollback_operation_id,
        'source_operation_id': snapshot.get('operation_id'),
        'table': table,
        'key': key,
        'key_value': key_value,
        'before_current': current,
        'restored': restored,
        'preview': preview,
    }


def run_cloud_rollback_candidates(limit: int = 30) -> int:
    try:
        session, _settings = _login_from_console()
        rows = list_rollback_candidates(session, limit=limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print(format_rollback_candidates(rows))
    return 0


def run_cloud_rollback_snapshot(operation_id: str, execute: bool = False, confirm: str = '') -> int:
    try:
        session, settings = _login_from_console()
        preview = preview_rollback_from_snapshot(session, operation_id)
        print(format_rollback_preview(preview))
        if not execute:
            print('\nPREVIEW ONLY: no se aplicó nada.')
            return 0
        if (confirm or '').strip().upper() != 'REVERTIR':
            print('\nERROR: para ejecutar rollback debes pasar --confirm REVERTIR.')
            return 2
        typed = input('\nEscribe REVERTIR para confirmar rollback interno: ').strip().upper()
        if typed != 'REVERTIR':
            print('Cancelado. No se aplicó rollback.')
            return 1
        result = execute_rollback_from_snapshot(session, operation_id, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print('\nROLLBACK INTERNO COMPLETADO')
    print('=' * 40)
    print(f"operation_id rollback: {result['operation_id']}")
    print(f"snapshot origen: {result['source_operation_id']}")
    print(f"tabla: {result['table']} · {result['key']}={result['key_value']}")
    print('Supabase fue revertido al before_data del snapshot.')
    print('WooCommerce no fue tocado.')
    print('Caja negra: nuevo audit_log + nuevo operation_snapshot generados.')
    return 0

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from futonhub.cloud.audit import AuditEvent, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from futonhub.core.config import load_settings


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _safe_source(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source_row")
    return source if isinstance(source, dict) else {}


SUPPLIER_ORDER_COLUMNS = "order_id,local_order_id,provider,order_file,status,total_items,total_cost,notes,created_at,updated_at,source_row"
SUPPLIER_ORDER_ITEM_COLUMNS = "id,order_id,local_id,item_id,item_code,item_name,quantity_ordered,quantity_received,unit_cost,line_cost,updated_at,source_row"


def list_cloud_supplier_orders(session, limit: int = 100) -> list[dict[str, Any]]:
    """Lee pedidos de proveedor reales desde Supabase.

    No devuelve mock data. La UI decide si muestra estado vacio.
    """
    limit = max(1, min(int(limit or 100), 500))
    try:
        response = (
            session.client.table("supplier_orders")
            .select(SUPPLIER_ORDER_COLUMNS)
            .neq("status", "cancelled")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        response = (
            session.client.table("supplier_orders")
            .select(SUPPLIER_ORDER_COLUMNS)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
    rows = list(getattr(response, "data", None) or [])
    return [row for row in rows if not _is_cancelled_or_deleted(row)]


def _is_line_deleted(row: dict[str, Any]) -> bool:
    source = _safe_source(row)
    deleted = source.get("ui_deleted")
    if deleted is True:
        return True
    if isinstance(deleted, str) and deleted.strip().lower() in {"true", "1", "yes", "si", "si"}:
        return True
    if isinstance(deleted, (int, float)) and deleted == 1:
        return True
    return False


def _row_updated_key(row: dict[str, Any]) -> str:
    return str(row.get("updated_at") or "")


def _line_identity(row: dict[str, Any], fallback_index: int) -> tuple[str, str]:
    source = _safe_source(row)
    line_index = source.get("ui_line_index")
    if line_index not in (None, ""):
        return ("line_index", str(line_index))
    return (
        "fallback",
        "|".join([
            str(row.get("item_code") or ""),
            str(row.get("item_name") or ""),
            str(row.get("quantity_ordered") or ""),
            str(fallback_index),
        ]),
    )


def list_cloud_supplier_order_items(session, order_id: str) -> list[dict[str, Any]]:
    if not order_id:
        return []
    response = (
        session.client.table("supplier_order_items")
        .select(SUPPLIER_ORDER_ITEM_COLUMNS)
        .eq("order_id", str(order_id))
        .order("updated_at", desc=False)
        .execute()
    )
    rows = [row for row in list(getattr(response, "data", None) or []) if not _is_line_deleted(row)]

    # Si RLS no permite borrar fisicamente ni marcar como borradas las lineas
    # antiguas, al guardar un pedido calculado pueden quedar duplicadas.
    # Conservamos la version mas reciente de cada ui_line_index para que
    # Modificar no duplique visualmente las lineas al reabrir un pedido en
    # Validacion/Calculado.
    latest_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    order_by_identity: dict[tuple[str, str], int] = {}
    for index, row in enumerate(rows):
        identity = _line_identity(row, index)
        if identity not in order_by_identity:
            order_by_identity[identity] = index
        current = latest_by_identity.get(identity)
        if current is None or _row_updated_key(row) >= _row_updated_key(current):
            latest_by_identity[identity] = row

    deduped = sorted(latest_by_identity.values(), key=lambda row: order_by_identity.get(_line_identity(row, 0), 0))
    return deduped


def _is_cancelled_or_deleted(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status in {"cancelled", "canceled", "cancelado", "deleted", "eliminado"}:
        return True
    source = _safe_source(row)
    deleted = source.get("ui_deleted")
    if deleted is True:
        return True
    if isinstance(deleted, str) and deleted.strip().lower() in {"true", "1", "yes", "si", "si"}:
        return True
    return False


def summarize_order_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    total_qty = 0.0
    total_cost = 0.0
    total_m3 = 0.0
    warnings = 0
    errors = 0
    for item in items:
        qty = _safe_float(item.get("quantity_ordered"), 0.0)
        line_cost = _safe_float(item.get("line_cost"), 0.0)
        source = _safe_source(item)
        m3 = _safe_float(source.get("total_m3") or source.get("m3_total") or source.get("cubic_meters_total"), 0.0)
        status = str(source.get("status") or source.get("ui_status") or "").strip().lower()
        total_qty += qty
        total_cost += line_cost
        total_m3 += m3
        if status in {"warning", "validacion", "validacion"}:
            warnings += 1
        if status in {"error", "critical", "bloqueado"}:
            errors += 1
    return {
        "total_qty": total_qty,
        "total_cost": total_cost,
        "total_m3": total_m3,
        "warnings": warnings,
        "errors": errors,
    }


def order_display_name(row: dict[str, Any]) -> str:
    source = _safe_source(row)
    for key in ("ui_order_name", "order_name", "name", "display_name"):
        value = source.get(key)
        if value not in (None, ""):
            return str(value)
    if row.get("order_file"):
        return str(row.get("order_file"))
    if row.get("local_order_id"):
        return f"Pedido {row.get('local_order_id')}"
    return str(row.get("order_id") or "Pedido sin nombre")


def format_order_date(row: dict[str, Any]) -> str:
    value = row.get("updated_at") or row.get("created_at") or ""
    text = str(value or "")
    if not text:
        return "-"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%d/%m/%Y")
    except Exception:
        return text[:10] or "-"



def create_supplier_order_draft(
    session,
    *,
    provider: str,
    order_name: str,
    order_file: str = "",
    file_type: str = "",
    notes: str = "",
    inputs: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Crea un pedido borrador real en Supabase.

    El objetivo es permitir guardar trabajo antes de tener costes del proveedor.
    No calcula, no toca inventario y no toca WooCommerce.
    """
    settings = load_settings()
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("ORDERDRAFT")
    safe_provider = str(provider or "Otros").strip() or "Otros"
    safe_name = str(order_name or "").strip()
    if not safe_name:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        safe_name = f"PED-{safe_provider[:3].upper()}-{stamp}"
    safe_file = str(order_file or f"{safe_name}.borrador").strip()
    safe_file_type = str(file_type or "BORRADOR").strip().upper()
    payload = {
        "provider": safe_provider,
        "order_file": safe_file,
        "status": "Borrador",
        "total_items": len(items or []),
        "total_cost": 0,
        "notes": notes or "Borrador guardado desde UI ERP. Pendiente de calculo.",
        "created_by": getattr(session, "user_id", None),
        "updated_at": now,
        "source_row": {
            "ui_order_name": safe_name,
            "file_type": safe_file_type,
            "inputs": inputs or {},
            "ui_created_from": "erp_orders_draft",
            "operation_id": operation_id,
            "created_at": now,
            "created_by_email": getattr(session, "email", None),
            "role": getattr(session, "role", None) or settings.sync_role,
            "machine": settings.machine_name,
        },
    }
    try:
        response = session.client.table("supplier_orders").insert(payload).execute()
        order = (getattr(response, "data", None) or [payload])[0]
        order_id = str(order.get("order_id") or safe_name)
        inserted_items: list[dict[str, Any]] = []
        if items:
            line_payloads: list[dict[str, Any]] = []
            for index, item in enumerate(items, start=1):
                source = item.get("source_row") if isinstance(item.get("source_row"), dict) else {}
                source = {**source, "ui_order_draft_operation_id": operation_id, "ui_line_index": index}
                line_payloads.append({
                    "order_id": order_id,
                    "item_code": str(item.get("code") or "").strip(),
                    "item_name": str(item.get("name") or "").strip(),
                    "quantity_ordered": _safe_float(item.get("quantity"), 0.0),
                    "quantity_received": 0,
                    "unit_cost": None,
                    "line_cost": None,
                    "updated_at": now,
                    "source_row": source,
                })
            if line_payloads:
                item_response = session.client.table("supplier_order_items").insert(line_payloads).execute()
                inserted_items = list(getattr(item_response, "data", None) or line_payloads)
        if inserted_items:
            order = {**order, "source_row": {**(order.get("source_row") or {}), "loaded_items_count": len(inserted_items)}}
        try:
            write_snapshot(
                session,
                OperationSnapshot(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="create_draft",
                    entity_type="supplier_order",
                    entity_id=order_id,
                    before_data={},
                    reason="Borrador de pedido creado desde UI ERP.",
                ),
            )
        except Exception:
            pass
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="create_draft",
                    status="OK",
                    severity="INFO",
                    entity_type="supplier_order",
                    entity_id=order_id,
                    before_data=None,
                    after_data={**order, "items_count": len(inserted_items)},
                    message="Borrador de pedido guardado desde UI ERP.",
                ),
                settings,
            )
        except Exception:
            pass
        return order
    except Exception as exc:
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="create_draft_failed",
                    status="ERROR",
                    severity="ERROR",
                    entity_type="supplier_order",
                    entity_id=safe_name,
                    before_data=None,
                    after_data=payload,
                    message="No se pudo guardar el borrador de pedido desde UI ERP.",
                    error_detail=str(exc),
                ),
                settings,
            )
        except Exception:
            pass
        raise


def update_supplier_order_draft(
    session,
    *,
    order_id: str,
    provider: str,
    order_name: str,
    order_file: str = "",
    file_type: str = "",
    notes: str = "",
    inputs: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Actualiza un pedido borrador real y sus lineas.

    Se usa desde la ventana Modificar/Calcular pedido cuando el pedido ya existe.
    No calcula, no toca inventario y no toca WooCommerce.
    """
    if not order_id:
        return create_supplier_order_draft(
            session,
            provider=provider,
            order_name=order_name,
            order_file=order_file,
            file_type=file_type,
            notes=notes,
            inputs=inputs,
            items=items,
        )

    settings = load_settings()
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("ORDERDRAFTUPD")
    safe_provider = str(provider or "Otros").strip() or "Otros"
    safe_name = str(order_name or "").strip() or str(order_file or order_id)
    safe_file = str(order_file or f"{safe_name}.borrador").strip()
    safe_file_type = str(file_type or "BORRADOR").strip().upper()
    try:
        current_response = session.client.table("supplier_orders").select("*").eq("order_id", str(order_id)).limit(1).execute()
        before_order = (getattr(current_response, "data", None) or [{}])[0]
    except Exception:
        before_order = {}

    source_before = _safe_source(before_order)
    source_after = {
        **source_before,
        "ui_order_name": safe_name,
        "file_type": safe_file_type,
        "inputs": inputs or {},
        "ui_updated_from": "erp_orders_draft",
        "update_operation_id": operation_id,
        "updated_at": now,
        "updated_by_email": getattr(session, "email", None),
        "role": getattr(session, "role", None) or settings.sync_role,
        "machine": settings.machine_name,
    }
    payload = {
        "provider": safe_provider,
        "order_file": safe_file,
        "status": "Borrador",
        "total_items": len(items or []),
        "total_cost": 0,
        "notes": notes or "Borrador actualizado desde UI ERP. Pendiente de calculo.",
        "updated_at": now,
        "source_row": source_after,
    }
    try:
        response = session.client.table("supplier_orders").update(payload).eq("order_id", str(order_id)).execute()
        updated_order = (getattr(response, "data", None) or [{**before_order, **payload, "order_id": str(order_id)}])[0]

        try:
            session.client.table("supplier_order_items").delete().eq("order_id", str(order_id)).execute()
        except Exception:
            # Si RLS impide delete fisico, intentamos limpiar logicamente las lineas antiguas.
            try:
                session.client.table("supplier_order_items").update({
                    "updated_at": now,
                    "source_row": {"ui_deleted": True, "ui_deleted_at": now, "ui_delete_operation_id": operation_id},
                }).eq("order_id", str(order_id)).execute()
            except Exception:
                pass

        inserted_items: list[dict[str, Any]] = []
        if items:
            line_payloads: list[dict[str, Any]] = []
            for index, item in enumerate(items, start=1):
                source = item.get("source_row") if isinstance(item.get("source_row"), dict) else {}
                source = {**source, "ui_order_draft_operation_id": operation_id, "ui_line_index": index}
                line_payloads.append({
                    "order_id": str(order_id),
                    "item_code": str(item.get("code") or "").strip(),
                    "item_name": str(item.get("name") or "").strip(),
                    "quantity_ordered": _safe_float(item.get("quantity"), 0.0),
                    "quantity_received": 0,
                    "unit_cost": None,
                    "line_cost": None,
                    "updated_at": now,
                    "source_row": source,
                })
            if line_payloads:
                item_response = session.client.table("supplier_order_items").insert(line_payloads).execute()
                inserted_items = list(getattr(item_response, "data", None) or line_payloads)

        try:
            write_snapshot(
                session,
                OperationSnapshot(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="update_draft",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    reason="Borrador de pedido actualizado desde UI ERP.",
                ),
            )
        except Exception:
            pass
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="update_draft",
                    status="OK",
                    severity="INFO",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    after_data={**updated_order, "items_count": len(inserted_items)},
                    message="Borrador de pedido actualizado desde UI ERP.",
                ),
                settings,
            )
        except Exception:
            pass
        return updated_order
    except Exception as exc:
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="update_draft_failed",
                    status="ERROR",
                    severity="ERROR",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    after_data=payload,
                    message="No se pudo actualizar el borrador de pedido desde UI ERP.",
                    error_detail=str(exc),
                ),
                settings,
            )
        except Exception:
            pass
        raise



def update_supplier_order_calculation(
    session,
    *,
    order_id: str,
    provider: str,
    order_name: str,
    order_file: str = "",
    file_type: str = "",
    notes: str = "",
    inputs: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    status: str = "Calculado",
) -> dict[str, Any]:
    """Guarda el resultado de calculo de un pedido y sus lineas.

    No toca inventario ni WooCommerce. Solo persiste cabecera/lineas calculadas
    para que el pedido pueda cerrarse y reabrirse con costes.
    """
    if not order_id:
        # Si todavia no existe, lo creamos como pedido calculado basico.
        order = create_supplier_order_draft(
            session,
            provider=provider,
            order_name=order_name,
            order_file=order_file,
            file_type=file_type,
            notes=notes,
            inputs=inputs,
            items=items,
        )
        order_id = str(order.get("order_id") or "")
        if not order_id:
            return order

    settings = load_settings()
    now = datetime.now(timezone.utc).isoformat()
    operation_id = new_operation_id("ORDERCALC")
    safe_provider = str(provider or "Otros").strip() or "Otros"
    safe_name = str(order_name or "").strip() or str(order_file or order_id)
    safe_file = str(order_file or f"{safe_name}.pedido").strip()
    safe_file_type = str(file_type or "BORRADOR").strip().upper()
    safe_status = str(status or "Calculado").strip() or "Calculado"
    items = list(items or [])
    total_cost = sum(_safe_float(item.get("line_cost") or item.get("final_cost"), 0.0) for item in items)
    total_items = sum(_safe_float(item.get("quantity"), 0.0) for item in items)
    try:
        current_response = session.client.table("supplier_orders").select("*").eq("order_id", str(order_id)).limit(1).execute()
        before_order = (getattr(current_response, "data", None) or [{}])[0]
    except Exception:
        before_order = {}
    source_before = _safe_source(before_order)
    source_after = {
        **source_before,
        "ui_order_name": safe_name,
        "file_type": safe_file_type,
        "inputs": inputs or {},
        "ui_updated_from": "erp_orders_calculation",
        "calculation_operation_id": operation_id,
        "updated_at": now,
        "updated_by_email": getattr(session, "email", None),
        "role": getattr(session, "role", None) or settings.sync_role,
        "machine": settings.machine_name,
    }
    payload = {
        "provider": safe_provider,
        "order_file": safe_file,
        "status": safe_status,
        "total_items": int(total_items) if float(total_items).is_integer() else total_items,
        "total_cost": round(total_cost, 2),
        "notes": notes or "Pedido calculado desde UI ERP.",
        "updated_at": now,
        "source_row": source_after,
    }
    try:
        response = session.client.table("supplier_orders").update(payload).eq("order_id", str(order_id)).execute()
        updated_order = (getattr(response, "data", None) or [{**before_order, **payload, "order_id": str(order_id)}])[0]
        try:
            session.client.table("supplier_order_items").delete().eq("order_id", str(order_id)).execute()
        except Exception:
            try:
                session.client.table("supplier_order_items").update({
                    "updated_at": now,
                    "source_row": {"ui_deleted": True, "ui_deleted_at": now, "ui_delete_operation_id": operation_id},
                }).eq("order_id", str(order_id)).execute()
            except Exception:
                pass
        line_payloads: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            source = item.get("source_row") if isinstance(item.get("source_row"), dict) else {}
            source = {**source, "ui_order_calculation_operation_id": operation_id, "ui_line_index": index}
            qty = _safe_float(item.get("quantity"), 0.0)
            line_cost = _safe_float(item.get("line_cost") or item.get("final_cost"), 0.0)
            unit_cost = _safe_float(item.get("unit_cost"), 0.0) or (round(line_cost / qty, 2) if qty else line_cost)
            line_payloads.append({
                "order_id": str(order_id),
                "item_code": str(item.get("code") or "").strip(),
                "item_name": str(item.get("name") or "").strip(),
                "quantity_ordered": qty,
                "quantity_received": 0,
                "unit_cost": unit_cost,
                "line_cost": line_cost,
                "updated_at": now,
                "source_row": source,
            })
        inserted_items: list[dict[str, Any]] = []
        if line_payloads:
            item_response = session.client.table("supplier_order_items").insert(line_payloads).execute()
            inserted_items = list(getattr(item_response, "data", None) or line_payloads)
        try:
            write_snapshot(
                session,
                OperationSnapshot(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="calculate_order",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    reason="Pedido calculado desde UI ERP.",
                ),
            )
        except Exception:
            pass
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="calculate_order",
                    status="OK" if safe_status == "Calculado" else "WARNING",
                    severity="INFO" if safe_status == "Calculado" else "WARNING",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    after_data={**updated_order, "items_count": len(inserted_items), "total_cost": total_cost},
                    message="Pedido calculado y guardado desde UI ERP.",
                ),
                settings,
            )
        except Exception:
            pass
        return updated_order
    except Exception as exc:
        try:
            write_audit_event(
                session,
                AuditEvent(
                    operation_id=operation_id,
                    module="supplier_orders",
                    action="calculate_order_failed",
                    status="ERROR",
                    severity="ERROR",
                    entity_type="supplier_order",
                    entity_id=str(order_id),
                    before_data=before_order,
                    after_data=payload,
                    message="No se pudo guardar el calculo del pedido desde UI ERP.",
                    error_detail=str(exc),
                ),
                settings,
            )
        except Exception:
            pass
        raise


def cancel_supplier_order(session, order_id: str, *, reason: str = "") -> dict[str, Any]:
    """Cancela logicamente un pedido de proveedor.

    No borra historico ni lineas. No toca inventario ni WooCommerce.
    """
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("Falta order_id para cancelar pedido.")

    operation_id = new_operation_id("supplier_order_cancel")
    now = datetime.now(timezone.utc).isoformat()

    existing_resp = (
        session.client.table("supplier_orders")
        .select(SUPPLIER_ORDER_COLUMNS)
        .eq("order_id", order_id)
        .limit(1)
        .execute()
    )
    rows = getattr(existing_resp, "data", None) or []
    if not rows:
        raise ValueError(f"No existe el pedido {order_id} en Supabase.")
    before = rows[0]
    status = str(before.get("status") or "").strip().lower()
    if status in {"recibido completo", "received", "received_full"}:
        raise ValueError("No se puede borrar/cancelar directamente un pedido recibido completo.")

    source = _safe_source(before)
    source.update(
        {
            "ui_cancelled": True,
            "ui_cancelled_at": now,
            "ui_cancelled_by_email": session.email,
            "ui_cancel_operation_id": operation_id,
            "ui_cancel_reason": reason,
        }
    )
    update_data = {
        "status": "cancelled",
        "updated_at": now,
        "notes": (str(before.get("notes") or "") + f"\nCancelado ERP: {reason}").strip(),
        "source_row": source,
    }

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Pedidos",
                action="cancel_supplier_order",
                entity_table="supplier_orders",
                entity_id=order_id,
                before_data=before,
                after_data=update_data,
                metadata={"reason": reason},
            ),
        )
    except Exception:
        pass

    session.client.table("supplier_orders").update(update_data).eq("order_id", order_id).execute()

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Pedidos",
                action="cancel_supplier_order",
                entity_table="supplier_orders",
                entity_id=order_id,
                status="success",
                message=f"Pedido cancelado desde UI ERP: {order_id}",
                metadata={"reason": reason},
            ),
        )
    except Exception:
        pass

    return {"operation_id": operation_id, "order_id": order_id, "status": "cancelled"}


# =====================================================
# ERP - Recepcion parcial/completa de pedidos
# =====================================================

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def preview_receive_supplier_order(
    session,
    *,
    order_id: str,
    received_lines: list[dict[str, Any]],
    destination: str = "warehouse",
    notes: str = "",
) -> dict[str, Any]:
    """Previsualiza la recepcion de un pedido.

    received_lines:
      [{"line_id": ..., "item_code": ..., "quantity_received_now": ...}]
    """
    order_id = str(order_id or "").strip()
    if not order_id:
        raise ValueError("Falta order_id.")

    destination = str(destination or "warehouse").strip().lower()
    if destination not in {"store", "warehouse"}:
        raise ValueError("Destino invalido. Usa tienda o almacen.")

    order_resp = session.client.table("supplier_orders").select("*").eq("order_id", order_id).limit(1).execute()
    order_rows = getattr(order_resp, "data", None) or []
    if not order_rows:
        raise ValueError(f"No existe el pedido {order_id}.")
    order = order_rows[0]

    items = list_cloud_supplier_order_items(session, order_id)
    by_line_id = {str(row.get("id")): row for row in items if row.get("id") not in (None, "")}
    by_code = {str(row.get("item_code") or row.get("item_id") or "").strip(): row for row in items}

    preview_lines: list[dict[str, Any]] = []
    errors: list[str] = []
    total_receive = 0.0

    for line in received_lines:
        line_id = str(line.get("line_id") or "").strip()
        code = str(line.get("item_code") or line.get("code") or "").strip()
        order_line = by_line_id.get(line_id) or by_code.get(code)
        if not order_line:
            errors.append(f"No se encontro linea para item {code or line_id}.")
            continue

        qty_ordered = _safe_float(order_line.get("quantity_ordered"), 0.0)
        qty_prev_received = _safe_float(order_line.get("quantity_received"), 0.0)
        qty_now = _safe_float(line.get("quantity_received_now"), 0.0)
        item_code = str(order_line.get("item_code") or code).strip()
        if qty_now < 0:
            errors.append(f"{item_code}: cantidad recibida negativa.")
            continue
        if qty_now == 0:
            continue
        if qty_prev_received + qty_now > qty_ordered:
            errors.append(f"{item_code}: recibido supera lo pedido ({qty_prev_received + qty_now:g} > {qty_ordered:g}).")
            continue

        inv_resp = session.client.table("inventory_items").select("item_id,name,store_stock,warehouse_stock,weighted_average_cost,source_row").eq("item_id", int(item_code)).limit(1).execute()
        inv_rows = getattr(inv_resp, "data", None) or []
        if not inv_rows:
            errors.append(f"{item_code}: no existe en inventory_items.")
            continue
        inv = inv_rows[0]
        store_before = _safe_float(inv.get("store_stock"), 0.0)
        warehouse_before = _safe_float(inv.get("warehouse_stock"), 0.0)
        store_after = store_before + qty_now if destination == "store" else store_before
        warehouse_after = warehouse_before + qty_now if destination == "warehouse" else warehouse_before

        preview_lines.append(
            {
                "line_id": order_line.get("id"),
                "item_code": item_code,
                "item_name": order_line.get("item_name") or inv.get("name"),
                "quantity_ordered": qty_ordered,
                "quantity_received_before": qty_prev_received,
                "quantity_received_now": qty_now,
                "quantity_received_after": qty_prev_received + qty_now,
                "destination": destination,
                "store_stock_before": store_before,
                "store_stock_after": store_after,
                "warehouse_stock_before": warehouse_before,
                "warehouse_stock_after": warehouse_after,
                "inventory_before": inv,
                "order_line_before": order_line,
            }
        )
        total_receive += qty_now

    ordered_total = sum(_safe_float(row.get("quantity_ordered"), 0.0) for row in items)
    received_after_total = sum(_safe_float(row.get("quantity_received"), 0.0) for row in items) + total_receive
    if received_after_total <= 0:
        new_status = str(order.get("status") or "Calculado")
    elif received_after_total >= ordered_total and ordered_total > 0:
        new_status = "Recibido completo"
    else:
        new_status = "Recibido parcial"

    return {
        "order": order,
        "items": items,
        "lines": preview_lines,
        "errors": errors,
        "destination": destination,
        "notes": notes,
        "total_receive": total_receive,
        "ordered_total": ordered_total,
        "received_after_total": received_after_total,
        "new_status": new_status,
    }


def receive_supplier_order(
    session,
    *,
    order_id: str,
    received_lines: list[dict[str, Any]],
    destination: str = "warehouse",
    notes: str = "",
) -> dict[str, Any]:
    """Aplica recepcion parcial/completa.

    Actualiza:
    - inventory_items.store_stock o warehouse_stock
    - supplier_order_items.quantity_received
    - supplier_orders.status

    No toca WooCommerce ni Hexa.
    """
    settings = load_settings()
    preview = preview_receive_supplier_order(
        session,
        order_id=order_id,
        received_lines=received_lines,
        destination=destination,
        notes=notes,
    )
    if preview.get("errors"):
        raise ValueError("No se puede aplicar recepcion con errores: " + "; ".join(preview["errors"]))
    if not preview.get("lines"):
        raise ValueError("No hay cantidades recibidas para aplicar.")

    operation_id = new_operation_id("ORDERRECV")
    now = datetime.now(timezone.utc).isoformat()
    order = preview["order"]

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="supplier_orders",
                action="receive_order",
                entity_type="supplier_order",
                entity_id=str(order_id),
                before_data={
                    "order": order,
                    "lines": [line.get("order_line_before") for line in preview["lines"]],
                    "inventory": [line.get("inventory_before") for line in preview["lines"]],
                    "preview": {k: v for k, v in preview.items() if k not in {"order", "items", "lines"}},
                },
                reason="Snapshot antes de recibir pedido desde UI ERP.",
            ),
        )
    except Exception:
        pass

    updated_inventory: list[dict[str, Any]] = []
    updated_lines: list[dict[str, Any]] = []

    for line in preview["lines"]:
        item_code = int(str(line["item_code"]))
        inv_payload = {"updated_at": now}
        source_row = line.get("inventory_before", {}).get("source_row")
        if not isinstance(source_row, dict):
            source_row = {}
        source_row = {
            **source_row,
            "last_receive_operation_id": operation_id,
            "last_receive_order_id": order_id,
            "last_receive_destination": line["destination"],
            "last_receive_qty": line["quantity_received_now"],
            "last_receive_at": now,
            "last_receive_by_email": getattr(session, "email", None),
        }
        inv_payload["source_row"] = source_row
        if line["destination"] == "store":
            inv_payload["store_stock"] = line["store_stock_after"]
        else:
            inv_payload["warehouse_stock"] = line["warehouse_stock_after"]

        inv_resp = session.client.table("inventory_items").update(inv_payload).eq("item_id", item_code).execute()
        updated_inventory.extend(list(getattr(inv_resp, "data", None) or [{**line.get("inventory_before", {}), **inv_payload}]))

        order_line_source = line.get("order_line_before", {}).get("source_row")
        if not isinstance(order_line_source, dict):
            order_line_source = {}
        order_line_source = {
            **order_line_source,
            "last_receive_operation_id": operation_id,
            "last_receive_qty": line["quantity_received_now"],
            "last_receive_destination": line["destination"],
            "last_receive_at": now,
        }
        line_payload = {
            "quantity_received": line["quantity_received_after"],
            "updated_at": now,
            "source_row": order_line_source,
        }
        if line.get("line_id") not in (None, ""):
            line_resp = session.client.table("supplier_order_items").update(line_payload).eq("id", line["line_id"]).execute()
        else:
            line_resp = session.client.table("supplier_order_items").update(line_payload).eq("order_id", order_id).eq("item_code", str(item_code)).execute()
        updated_lines.extend(list(getattr(line_resp, "data", None) or [line_payload]))

    order_source = _safe_source(order)
    receive_history = order_source.get("receive_history")
    if not isinstance(receive_history, list):
        receive_history = []
    receive_history.append(
        {
            "operation_id": operation_id,
            "received_at": now,
            "destination": preview["destination"],
            "total_receive": preview["total_receive"],
            "notes": notes,
            "user_email": getattr(session, "email", None),
        }
    )
    order_source = {
        **order_source,
        "receive_history": receive_history,
        "last_receive_operation_id": operation_id,
        "last_receive_at": now,
        "last_receive_destination": preview["destination"],
    }
    order_payload = {
        "status": preview["new_status"],
        "updated_at": now,
        "notes": (str(order.get("notes") or "") + (f"\nRecepcion ERP: {notes}" if notes else "\nRecepcion ERP registrada.")).strip(),
        "source_row": order_source,
    }
    order_resp = session.client.table("supplier_orders").update(order_payload).eq("order_id", str(order_id)).execute()
    updated_order = (getattr(order_resp, "data", None) or [{**order, **order_payload}])[0]

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="supplier_orders",
                action="receive_order",
                status="OK",
                severity="INFO",
                entity_type="supplier_order",
                entity_id=str(order_id),
                before_data={"order": order},
                after_data={
                    "order": updated_order,
                    "updated_inventory_count": len(updated_inventory),
                    "updated_lines_count": len(updated_lines),
                    "new_status": preview["new_status"],
                    "total_receive": preview["total_receive"],
                },
                message="Pedido recibido desde UI ERP. Se actualizo stock interno Supabase. WooCommerce/Hexa no fueron tocados.",
            ),
            settings,
        )
    except Exception:
        pass

    return {
        "operation_id": operation_id,
        "order": updated_order,
        "updated_inventory": updated_inventory,
        "updated_lines": updated_lines,
        "preview": preview,
    }

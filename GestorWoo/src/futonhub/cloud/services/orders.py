from __future__ import annotations

import json
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
                entity_type="supplier_orders",
                entity_id=order_id,
                before_data=before,
                reason=json.dumps({"reason": reason}, ensure_ascii=False, default=str),
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
                entity_type="supplier_orders",
                entity_id=order_id,
                status="success",
                message=f"Pedido cancelado desde UI ERP: {order_id}",
                after_data={"reason": reason},
            ),
        )
    except Exception:
        pass

    return {"operation_id": operation_id, "order_id": order_id, "status": "cancelled"}


# =====================================================
# ERP - Recepcion parcial/completa de pedidos
# =====================================================

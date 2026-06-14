from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from futonhub.cloud.audit import AuditEvent, CloudAuditError, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from gestorwoo.config import Settings, load_settings


def _json_safe(value: Any) -> Any:
    import json
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default



def _source_row_dict(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source_row")
    return source if isinstance(source, dict) else {}


def _truthy_source_flag(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "si", "sí"}
    if isinstance(value, (int, float)):
        return value == 1
    return False


def _is_ui_deleted(row: dict[str, Any]) -> bool:
    source = _source_row_dict(row)
    return _truthy_source_flag(source.get("ui_deleted"))

from futonhub.cloud.services.prices import PRICE_PROPOSAL_STATUSES, format_price_safety_for_search as _format_price_safety_for_search, money_or_none as _safe_money, price_safety_preview as _price_safety_preview, short_row_value as _short_row_value

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


def _legacy_short_row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _legacy_money_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text.replace(",", "."))
    except Exception:
        return None


def _legacy_current_price_from_item(item: dict[str, Any]) -> float | None:
    return _money_or_none(_short_row_value(item, "price", "regular_price", "sale_price"))


def _legacy_product_type(item: dict[str, Any], kind: str) -> str:
    if kind == "variation":
        return "variation"
    return str(item.get("type") or "product").strip().lower()


def _legacy_price_safety_preview(item: dict[str, Any], kind: str, proposed_price: float | None, settings: Settings) -> dict[str, Any]:
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


def _legacy_format_price_safety_for_search(row: dict[str, Any]) -> str | None:
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
    if not proposal_id:
        raise CloudAuditError("Selecciona una propuesta.")
    resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
    rows = getattr(resp, "data", None) or []
    if not rows:
        raise CloudAuditError(f"No se encontró la propuesta {proposal_id}.")
    return rows[0]


def preview_existing_price_proposal(session, proposal_id: str, settings: Settings | None = None) -> dict[str, Any]:
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




def delete_real_price_proposal_group(session, proposal_id: str, proposal_name: str | None = None, settings: Settings | None = None) -> dict[str, Any]:
    """Elimina una propuesta real de UI-ERP.

    Si la propuesta pertenece a un grupo visual por `source_row.ui_proposal_name`,
    elimina todos los registros pendientes/no publicados que comparten ese nombre.
    Si Supabase/RLS no permite DELETE, marca los registros como `ui_deleted` para
    ocultarlos de la bandeja sin perder trazabilidad.
    """
    settings = settings or load_settings()
    if not proposal_id:
        raise CloudAuditError("Selecciona una propuesta real para borrar.")
    operation_id = new_operation_id("PRICEDEL")
    try:
        resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
        rows = getattr(resp, "data", None) or []
        if not rows:
            raise CloudAuditError(f"No se encontró la propuesta {proposal_id}.")
        selected = rows[0]
        selected_source = _source_row_dict(selected)
        group_name = (proposal_name or selected_source.get("ui_proposal_name") or "").strip()
        target_rows = [selected]
        if group_name:
            all_resp = session.client.table("price_change_proposals").select("*").limit(500).execute()
            all_rows = getattr(all_resp, "data", None) or []
            target_rows = []
            for row in all_rows:
                source = _source_row_dict(row)
                if _is_ui_deleted(row):
                    continue
                if str(source.get("ui_proposal_name") or "").strip() == group_name:
                    target_rows.append(row)
            if not target_rows:
                target_rows = [selected]
        protected_statuses = {"published", "publishing"}
        blocked = [row for row in target_rows if str(row.get("status") or "").strip().lower() in protected_statuses]
        if blocked:
            raise CloudAuditError("No se puede borrar una propuesta publicada o en publicación. Crea una nueva propuesta de corrección.")

        before_data = _json_safe(target_rows)
        for row in target_rows:
            write_snapshot(session, OperationSnapshot(
                operation_id=operation_id,
                module="price_change_proposals",
                action="ui_delete_price_proposal",
                entity_type="price_change_proposal",
                entity_id=str(row.get("id")),
                before_data=_json_safe(row),
                reason="UI-ERP: snapshot antes de borrar propuesta de Cambio de Precios.",
            ))

        ids = [row.get("id") for row in target_rows if row.get("id")]
        hard_deleted = False
        soft_deleted = False

        def soft_delete_rows() -> None:
            nonlocal soft_deleted
            now = datetime.now(timezone.utc).isoformat()
            for row in target_rows:
                source = _source_row_dict(row)
                source.update({
                    "ui_deleted": True,
                    "ui_deleted_at": now,
                    "ui_deleted_by_email": session.email,
                    "ui_delete_operation_id": operation_id,
                })
                session.client.table("price_change_proposals").update({
                    "status": "rejected",
                    "source_row": source,
                    "notes": (row.get("notes") or "") + "\n[UI-ERP] Propuesta borrada/ocultada desde Cambio de Precios.",
                }).eq("id", row.get("id")).execute()
            soft_deleted = True

        try:
            for row_id in ids:
                session.client.table("price_change_proposals").delete().eq("id", row_id).execute()
            remaining = []
            for row_id in ids:
                check = session.client.table("price_change_proposals").select("id, source_row").eq("id", row_id).limit(1).execute()
                remaining.extend(getattr(check, "data", None) or [])
            if remaining:
                # Supabase/RLS puede devolver DELETE sin error aunque no haya eliminado nada.
                # Verificamos y, si sigue existiendo, aplicamos borrado lógico.
                soft_delete_rows()
            else:
                hard_deleted = True
        except Exception:
            soft_delete_rows()

        write_audit_event(session, AuditEvent(
            operation_id=operation_id,
            module="price_change_proposals",
            action="ui_delete_price_proposal",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id=str(proposal_id),
            before_data=before_data,
            after_data={"deleted_count": len(target_rows), "hard_deleted": hard_deleted, "soft_deleted": soft_deleted, "proposal_name": group_name},
            message="UI-ERP: propuesta de Cambio de Precios borrada desde la bandeja.",
        ), settings)
        return {"operation_id": operation_id, "deleted_count": len(target_rows), "hard_deleted": hard_deleted, "soft_deleted": soft_deleted, "proposal_name": group_name}
    except CloudAuditError:
        raise
    except Exception as exc:
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="price_change_proposals",
                action="ui_delete_price_proposal_failed",
                status="ERROR",
                severity="ERROR",
                entity_type="price_change_proposal",
                entity_id=str(proposal_id),
                message="Falló el borrado de propuesta desde UI-ERP.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise

def list_real_price_proposals(session, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
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
        source = _source_row_dict(row)
        if source.get("test") is True or _is_ui_deleted(row):
            continue
        result.append(row)
    return result


def format_real_price_proposals(rows: list[dict[str, Any]]) -> str:
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



fetch_cloud_item_for_price = _fetch_cloud_item_for_price
fetch_latest_price_proposal = _fetch_latest_price_proposal

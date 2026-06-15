from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from futonhub.cloud.audit import AuditEvent, CloudAuditError, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from futonhub.cloud.locks import acquire_system_lock, release_system_lock
from futonhub.cloud.services.inventory import sync_woocommerce_price_inventory_state
from futonhub.cloud.services.price_proposals import fetch_cloud_item_for_price as _fetch_cloud_item_for_price
from futonhub.cloud.services.prices import money_or_none as _money_or_none, price_safety_preview as _price_safety_preview, short_row_value as _short_row_value
from gestorwoo.config import Settings, load_settings
from gestorwoo.woocommerce import WooCommerceClient




def _blackbox_record_exists(session, table: str, operation_id: str) -> bool:
    """Comprueba que la caja negra se persistió realmente, no solo que la RPC respondió."""
    try:
        resp = session.client.table(table).select("id,operation_id").eq("operation_id", operation_id).limit(1).execute()
        return bool(getattr(resp, "data", None) or [])
    except Exception:
        return False


def _ensure_snapshot_persisted(session, snapshot: OperationSnapshot) -> dict[str, Any]:
    result = write_snapshot(session, snapshot)
    if _blackbox_record_exists(session, "operation_snapshots", snapshot.operation_id):
        return result
    # Segundo intento defensivo. Algunas RPC antiguas devolvían éxito sin fila persistida.
    result = write_snapshot(session, snapshot)
    if not _blackbox_record_exists(session, "operation_snapshots", snapshot.operation_id):
        raise CloudAuditError(
            f"No se confirmó la persistencia del operation_snapshot {snapshot.operation_id}. "
            "Publicación bloqueada antes de tocar WooCommerce."
        )
    return result


def _ensure_audit_persisted(session, event: AuditEvent, settings: Settings) -> dict[str, Any]:
    result = write_audit_event(session, event, settings)
    if _blackbox_record_exists(session, "audit_logs", event.operation_id):
        return result
    result = write_audit_event(session, event, settings)
    if not _blackbox_record_exists(session, "audit_logs", event.operation_id):
        raise CloudAuditError(
            f"WooCommerce fue actualizado, pero no se confirmó el audit_log {event.operation_id}. "
            "La operación no puede declararse completamente cerrada."
        )
    return result

def _json_safe(value: Any) -> Any:
    import json
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}

# ================================
# v11.2 - Preview protegido de publicación WooCommerce
# ================================

def _safe_money(value: Any) -> float | None:
    return _money_or_none(value)

def _effective_woo_price(data: dict[str, Any] | None) -> float | None:
    data = data or {}
    sale = _safe_money(data.get("sale_price"))
    if sale is not None and sale > 0:
        return sale
    regular = _safe_money(data.get("regular_price"))
    if regular is not None and regular > 0:
        return regular
    return _safe_money(data.get("price"))


def _format_price_value(value: Any) -> str | None:
    amount = _safe_money(value)
    if amount is None:
        return None
    return f"{amount:.2f}"


def _pricing_payload_for_effective_price(woo_before: dict[str, Any], new_price: float) -> tuple[dict[str, Any], str]:
    """Construye una escritura que garantice que el precio visible sea new_price.

    - Si existe rebaja activa y new_price < regular_price, se actualiza sale_price.
    - Si new_price >= regular_price, se convierte en precio normal y se limpia sale_price.
    - Sin rebaja activa, se actualiza regular_price y se limpia sale_price.
    """
    regular = _safe_money(woo_before.get("regular_price"))
    sale = _safe_money(woo_before.get("sale_price"))
    formatted = f"{new_price:.2f}"
    if sale is not None and sale > 0 and regular is not None and regular > 0 and new_price < regular:
        return {"sale_price": formatted}, "sale_price"
    return {"regular_price": formatted, "sale_price": ""}, "regular_price"


def _pricing_snapshot(data: dict[str, Any] | None) -> dict[str, Any]:
    data = data or {}
    return {
        "price": data.get("price"),
        "regular_price": data.get("regular_price"),
        "sale_price": data.get("sale_price"),
        "on_sale": data.get("on_sale"),
        "date_on_sale_from": data.get("date_on_sale_from"),
        "date_on_sale_to": data.get("date_on_sale_to"),
    }


def _proposal_item_snapshot(proposal: dict[str, Any]) -> dict[str, Any]:
    source = proposal.get("source_row") or {}
    snap = source.get("item_snapshot") or {}
    return snap if isinstance(snap, dict) else {}


def _fetch_cloud_item_for_proposal(session, proposal: dict[str, Any]) -> dict[str, Any]:
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
                woo_price = _effective_woo_price(woo_data)
                woo_regular_price = _safe_money((woo_data or {}).get("regular_price"))
                woo_sale_price = _safe_money((woo_data or {}).get("sale_price"))
                if woo_sale_price is not None and woo_sale_price > 0:
                    messages.append("INFO: WooCommerce tiene sale_price activo. La publicación ajustará el campo necesario para que el precio visible coincida con la propuesta.")
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
        publish_snapshot = OperationSnapshot(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_woocommerce_price",
            entity_type="price_change_proposal",
            entity_id=str(proposal_id),
            before_data=_json_safe(before_bundle),
            reason="v11.5: snapshot antes de publicar precio en WooCommerce.",
        )
        _ensure_snapshot_persisted(session, publish_snapshot)

        pricing_payload, pricing_strategy = _pricing_payload_for_effective_price(woo_before or {}, float(new_price))
        if kind == "product":
            woo_put_response = client.update_product_pricing(woo_id, pricing_payload)
            woo_written = True
            woo_verified = _fetch_woo_item_readonly(client, session, proposal)
            mirror_table = "products"
        elif kind == "variation":
            parent_id = cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id")
            if not parent_id:
                raise CloudAuditError(f"No se pudo determinar parent_woo_id para la variación {woo_id}.")
            woo_put_response = client.update_variation_pricing(int(parent_id), woo_id, pricing_payload)
            woo_written = True
            woo_verified = _fetch_woo_item_readonly(client, session, proposal)
            mirror_table = "product_variations"
        else:
            raise CloudAuditError("item_kind inválido para publicación WooCommerce.")

        verified_effective_price = _effective_woo_price(woo_verified)
        if verified_effective_price is None or abs(verified_effective_price - float(new_price)) > 0.009:
            # Compensación inmediata: intenta devolver Woo al estado anterior.
            rollback_payload = {
                "regular_price": str((woo_before or {}).get("regular_price") or ""),
                "sale_price": str((woo_before or {}).get("sale_price") or ""),
            }
            try:
                if kind == "product":
                    client.update_product_pricing(woo_id, rollback_payload)
                else:
                    client.update_variation_pricing(int(parent_id), woo_id, rollback_payload)
            except Exception:
                pass
            raise CloudAuditError(
                f"WooCommerce respondió a la escritura, pero la verificación posterior devolvió precio efectivo "
                f"{verified_effective_price!r} en vez de {new_price:.2f}. Se intentó restaurar el estado anterior."
            )

        woo_after = woo_verified
        inventory_sync_result = sync_woocommerce_price_inventory_state(
            session,
            operation_id=operation_id,
            proposal=proposal,
            cloud_item=cloud_item,
            woo_id=woo_id,
            before_price=_format_price_value(_effective_woo_price(woo_before)),
            verified_price=_format_price_value(verified_effective_price),
            action="admin_publish_woocommerce_price",
            message="Precio Woo publicado y verificado.",
            metadata={
                "proposal_id": proposal_id,
                "item_kind": kind,
                "woo_id": woo_id,
                "parent_woo_id": cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id"),
                "pricing_payload": _json_safe(pricing_payload),
                "pricing_strategy": pricing_strategy,
            },
        )
        mirror_payload = {
            "price": str(woo_verified.get("price") or f"{new_price:.2f}"),
            "regular_price": str(woo_verified.get("regular_price") or ""),
            "sale_price": str(woo_verified.get("sale_price") or ""),
        }
        session.client.table(mirror_table).update(mirror_payload).eq("woo_id", woo_id).execute()

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
                "woo_put_response": _json_safe(woo_put_response),
                "woo_after_verified": _json_safe(woo_after),
                "pricing_payload": _json_safe(pricing_payload),
                "pricing_strategy": pricing_strategy,
                "verified_effective_price": verified_effective_price,
                "inventory_sync": _json_safe(inventory_sync_result),
                "inventory_history": _json_safe(inventory_sync_result.get("history")),
                "inventory_history_resolution": _json_safe(inventory_sync_result.get("resolution")),
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

        publish_event = AuditEvent(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_woocommerce_price",
            status="OK",
            severity="WARNING" if row.get("status") == "WARNING" else "INFO",
            entity_type="price_change_proposal",
            entity_id=str(proposal_id),
            before_data=_json_safe(before_bundle),
            after_data=_json_safe({"proposal": updated_proposal, "woo_put_response": woo_put_response, "woo_after_verified": woo_after, "pricing_payload": pricing_payload, "pricing_strategy": pricing_strategy, "verified_effective_price": verified_effective_price}),
            message="Precio efectivo publicado y verificado en WooCommerce. Supabase actualizado.",
        )
        _ensure_audit_persisted(session, publish_event, settings)
        return {
            "operation_id": operation_id,
            "proposal": updated_proposal,
            "preview_row": row,
            "woo_before": woo_before,
            "woo_after": woo_after,
            "woo_put_response": woo_put_response,
            "pricing_payload": pricing_payload,
            "pricing_strategy": pricing_strategy,
            "verified_effective_price": verified_effective_price,
            "new_price": new_price,
            "item_kind": kind,
            "woo_id": woo_id,
            "inventory_sync": inventory_sync_result,
            "inventory_history": inventory_sync_result.get("history"),
            "inventory_history_resolution": inventory_sync_result.get("resolution"),
        }
    except CloudAuditError as exc:
        if publishing_marked and not woo_written:
            try:
                session.client.table("price_change_proposals").update({"status": "approved"}).eq("id", proposal_id).eq("status", "publishing").execute()
            except Exception:
                pass
        if woo_written:
            try:
                session.client.table("price_change_proposals").update({
                    "status": "error",
                    "error_message": "Woo actualizado, pero fallo cierre interno de Inventario/historial. Reintentar sincronizacion interna sin republicar Woo.",
                }).eq("id", proposal_id).execute()
            except Exception:
                pass
            try:
                write_audit_event(session, AuditEvent(
                    operation_id=operation_id,
                    module="woocommerce_publish",
                    action="admin_publish_woocommerce_price_partial_internal_sync_failed",
                    status="ERROR",
                    severity="CRITICAL",
                    entity_type="price_change_proposal",
                    entity_id=str(proposal_id),
                    before_data=_json_safe(before_bundle),
                    after_data={"woo_written": True, "proposal_id": proposal_id, "internal_sync_error": str(exc)},
                    message="WooCommerce fue actualizado y verificado, pero fallo la sincronizacion interna de Inventario/historial.",
                    error_detail=str(exc),
                ), settings)
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
    row = result.get("preview_row") or {}
    lines = [
        "PUBLICACIÓN WOOCOMMERCE COMPLETADA",
        "=" * 44,
        f"operation_id: {result.get('operation_id')}",
        f"item: [{result.get('item_kind')}] {result.get('woo_id')} · {row.get('name')}",
        f"propuesta_id: {(result.get('proposal') or {}).get('id')}",
        f"nuevo precio efectivo verificado: {result.get('verified_effective_price'):.2f}",
        "Supabase fue actualizado y la propuesta quedó como published.",
        "Caja negra: audit_log + operation_snapshot generados.",
    ]
    if row.get("status") == "WARNING":
        lines.append("AVISO: se publicó con warnings reconocidos explícitamente por admin.")
    return "\n".join(lines)



proposal_item_snapshot = _proposal_item_snapshot
fetch_cloud_item_for_proposal = _fetch_cloud_item_for_proposal
fetch_woo_item_readonly = _fetch_woo_item_readonly
fetch_approved_price_proposals = _fetch_approved_price_proposals
format_publish_row_for_confirm = _format_publish_row_for_confirm

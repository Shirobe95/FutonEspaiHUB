from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from futonhub.cloud.audit import AuditEvent, CloudAuditError, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from futonhub.cloud.locks import acquire_system_lock, release_system_lock
from futonhub.cloud.services.inventory import sync_woocommerce_price_inventory_state
from futonhub.cloud.services.price_proposals import fetch_cloud_item_for_price as _fetch_cloud_item_for_price
from futonhub.cloud.services.prices import money_or_none as _money_or_none, price_safety_preview as _price_safety_preview, short_row_value as _short_row_value
from gestorwoo.config import Settings, load_settings
from gestorwoo.woocommerce import WooCommerceClient




def _blackbox_record_exists(session, table: str, operation_id: str) -> bool:
    """Comprueba que la caja negra se persistio realmente, no solo que la RPC respondio."""
    try:
        resp = session.client.table(table).select("id,operation_id").eq("operation_id", operation_id).limit(1).execute()
        return bool(getattr(resp, "data", None) or [])
    except Exception:
        return False


def _ensure_snapshot_persisted(session, snapshot: OperationSnapshot) -> dict[str, Any]:
    result = write_snapshot(session, snapshot)
    if _blackbox_record_exists(session, "operation_snapshots", snapshot.operation_id):
        return result
    # Segundo intento defensivo. Algunas RPC antiguas devolvian exito sin fila persistida.
    result = write_snapshot(session, snapshot)
    if not _blackbox_record_exists(session, "operation_snapshots", snapshot.operation_id):
        raise CloudAuditError(
            f"No se confirmo la persistencia del operation_snapshot {snapshot.operation_id}. "
            "Publicacion bloqueada antes de tocar WooCommerce."
        )
    return result


def _ensure_audit_persisted(session, event: AuditEvent, settings: Settings) -> dict[str, Any]:
    result = write_audit_event(session, event, settings)
    if _blackbox_record_exists(session, "audit_logs", event.operation_id):
        return result
    result = write_audit_event(session, event, settings)
    if not _blackbox_record_exists(session, "audit_logs", event.operation_id):
        raise CloudAuditError(
            f"WooCommerce fue actualizado, pero no se confirmo el audit_log {event.operation_id}. "
            "La operacion no puede declararse completamente cerrada."
        )
    return result

def _json_safe(value: Any) -> Any:
    import json
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}

# ================================
# v11.2 - Preview protegido de publicacion WooCommerce
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


def _proposal_canonical_identity(proposal: dict[str, Any]) -> tuple[str, int, str]:
    source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
    kind = str(source.get("ui_canonical_item_kind") or proposal.get("item_kind") or "").strip().lower()
    try:
        woo_id = int(source.get("ui_canonical_woo_id") or proposal.get("item_woo_id") or proposal.get("local_id"))
    except Exception as exc:
        raise CloudAuditError("La propuesta no tiene woo_id canonico valido.") from exc
    if kind not in {"product", "variation", "pack"} or woo_id <= 0:
        raise CloudAuditError("La propuesta no tiene identidad canonica publicable.")
    return kind, woo_id, f"{kind}:{woo_id}"


def _remote_target_for_proposal(session, proposal: dict[str, Any]) -> dict[str, Any]:
    kind, woo_id, canonical_key = _proposal_canonical_identity(proposal)
    snapshot = _proposal_item_snapshot(proposal)
    cloud_item = _fetch_cloud_item_for_proposal(session, proposal)
    remote_kind = kind
    if kind == "pack":
        remote_kind = str(
            snapshot.get("woo_item_kind")
            or snapshot.get("remote_item_kind")
            or cloud_item.get("woo_item_kind")
            or "product"
        ).strip().lower()
    if remote_kind == "product":
        return {
            "canonical_key": canonical_key,
            "canonical_kind": kind,
            "woo_id": woo_id,
            "remote_kind": "product",
            "remote_key": f"product:{woo_id}",
            "endpoint": f"products/{woo_id}",
            "cloud_item": cloud_item,
        }
    if remote_kind == "variation":
        parent_id = (
            snapshot.get("woo_parent_id")
            or snapshot.get("parent_woo_id")
            or cloud_item.get("woo_parent_id")
            or cloud_item.get("parent_woo_id")
        )
        try:
            parent_id = int(parent_id)
        except Exception as exc:
            raise CloudAuditError(
                f"{canonical_key} no tiene parent product ID fiable."
            ) from exc
        return {
            "canonical_key": canonical_key,
            "canonical_kind": kind,
            "woo_id": woo_id,
            "parent_woo_id": parent_id,
            "remote_kind": "variation",
            "remote_key": f"variation:{parent_id}:{woo_id}",
            "endpoint": f"products/{parent_id}/variations/{woo_id}",
            "cloud_item": cloud_item,
        }
    raise CloudAuditError(f"{canonical_key} no tiene destino Woo publicable.")


def _fetch_remote_target(client: WooCommerceClient, target: dict[str, Any]) -> dict[str, Any]:
    return client.get(str(target["endpoint"])).json()


def _write_remote_target(
    client: WooCommerceClient,
    target: dict[str, Any],
    payload: dict[str, Any],
) -> Any:
    if target["remote_kind"] == "product":
        return client.update_product_pricing(int(target["woo_id"]), payload)
    return client.update_variation_pricing(
        int(target["parent_woo_id"]),
        int(target["woo_id"]),
        payload,
    )


def _proposal_is_deleted(proposal: dict[str, Any]) -> bool:
    source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
    value = source.get("ui_deleted")
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes", "si", "si"}


def _fetch_price_proposal_rows(session, proposal_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    ids = list(dict.fromkeys(str(value).strip() for value in proposal_ids if str(value).strip()))
    if not ids:
        raise CloudAuditError("La propuesta no contiene IDs reales.")
    response = session.client.table("price_change_proposals").select("*").in_("id", ids).limit(max(len(ids), 1)).execute()
    rows = list(getattr(response, "data", None) or [])
    by_id = {str(row.get("id")): row for row in rows}
    missing = [row_id for row_id in ids if row_id not in by_id]
    if missing:
        raise CloudAuditError("Faltan lineas reales de la propuesta: " + ", ".join(missing[:5]))
    return [by_id[row_id] for row_id in ids]


def _fetch_cloud_item_for_proposal(session, proposal: dict[str, Any]) -> dict[str, Any]:
    kind = (proposal.get("item_kind") or "").strip().lower()
    woo_id = int(proposal.get("item_woo_id") or proposal.get("local_id") or 0)
    if kind in {"product", "variation", "pack"} and woo_id:
        try:
            return _fetch_cloud_item_for_price(session, kind, woo_id)
        except Exception:
            pass
    snap = _proposal_item_snapshot(proposal)
    if snap:
        if kind == "variation" and "name" not in snap:
            snap["name"] = f"{snap.get('parent_name')} - {snap.get('attributes_label') or 'variacion'}"
        return snap
    return {
        "woo_id": woo_id,
        "name": proposal.get("name") or f"{kind} {woo_id}",
        "type": "variation" if kind == "variation" else "product",
        "price": proposal.get("old_price"),
    }


def _fetch_woo_item_readonly(client: WooCommerceClient, session, proposal: dict[str, Any]) -> dict[str, Any] | None:
    """Lee WooCommerce sin modificar nada para construir preview de publicacion."""
    kind = (proposal.get("item_kind") or "").strip().lower()
    woo_id = int(proposal.get("item_woo_id") or proposal.get("local_id") or 0)
    if not woo_id:
        return None
    if kind in {"product", "pack"}:
        return client.get(f"products/{woo_id}").json()
    if kind == "variation":
        cloud_item = _fetch_cloud_item_for_proposal(session, proposal)
        parent_id = cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id")
        if not parent_id:
            # Fallback: busca la variacion en Supabase por woo_id para extraer parent_woo_id.
            resp = session.client.table("product_variations").select("parent_woo_id").eq("woo_id", woo_id).limit(1).execute()
            rows = getattr(resp, "data", None) or []
            parent_id = rows[0].get("parent_woo_id") if rows else None
        if not parent_id:
            raise CloudAuditError(f"No se pudo determinar parent_woo_id para la variacion {woo_id}.")
        return client.get(f"products/{int(parent_id)}/variations/{woo_id}").json()
    raise CloudAuditError("La propuesta no tiene item_kind valido para WooCommerce.")


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
    """Preview de publicacion WooCommerce. Lee Woo y Supabase, no ejecuta PUT.

    Devuelve filas con estado OK/WARNING/ERROR y un resumen. Es la antesala de una
    publicacion futura, pero aqui WooCommerce solo se consulta.
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede generar preview de publicacion WooCommerce.")
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
                    messages.append("INFO: WooCommerce tiene sale_price activo. La publicacion ajustara el campo necesario para que el precio visible coincida con la propuesta.")
                # Seguridad extra: compara con Woo actual, no solo con Supabase.
                if woo_price is None or woo_price <= 0:
                    messages.append("WARNING: WooCommerce devuelve precio actual vacio/0 para este item vendible. Se permite continuar, pero no se puede calcular porcentaje de bajada frente a Woo.")
                    if status != "ERROR":
                        status = "WARNING"
                elif new_price is not None and new_price > 0:
                    drop = ((woo_price - new_price) / woo_price) * 100 if new_price < woo_price else 0.0
                    if drop >= settings.price_drop_block_percent:
                        messages.append(f"ERROR: frente a WooCommerce actual, la bajada seria {drop:.2f}% y supera el bloqueo ({settings.price_drop_block_percent:.2f}%).")
                        status = "ERROR"
                    elif drop >= settings.price_drop_warning_percent and status != "ERROR":
                        messages.append(f"WARNING: frente a WooCommerce actual, la bajada seria {drop:.2f}% y requiere revision.")
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
            message="v11.2: preview de publicacion WooCommerce generado. WooCommerce solo fue leido; no se publico ningun cambio.",
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
                message="Fallo el preview de publicacion WooCommerce.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise


def format_woocommerce_publish_preview(result: dict[str, Any]) -> str:
    rows = result.get("rows") or []
    counts = result.get("counts") or {}
    lines = [
        "PREVIEW PUBLICACION WOOCOMMERCE",
        "=" * 44,
        f"operation_id: {result.get('operation_id')}",
        "WooCommerce solo fue leido. NO se publico ningun cambio.",
        f"Propuestas evaluadas: {len(rows)} - OK={counts.get('OK',0)} - WARNING={counts.get('WARNING',0)} - ERROR={counts.get('ERROR',0)}",
        "",
    ]
    if not rows:
        lines.append("No hay propuestas reales aprobadas para publicar.")
        return "\n".join(lines)
    for idx, row in enumerate(rows, start=1):
        lines.append(f"{idx}. {row.get('status')} - [{row.get('item_kind')}] {row.get('item_woo_id')} - {row.get('name')}")
        lines.append(f"   propuesta_id: {row.get('proposal_id')}")
        lines.append(f"   precio Woo actual: {row.get('woo_current_price')} - propuesto: {row.get('new_price')}")
        if row.get("delta_vs_woo") is not None:
            lines.append(f"   diferencia vs Woo: {row.get('delta_vs_woo'):.2f} ({row.get('delta_pct_vs_woo'):.2f}%)")
        for msg in row.get("messages") or []:
            prefix = "   - "
            lines.append(prefix + msg)
        lines.append("")
    if counts.get("ERROR", 0):
        lines.append("BLOQUEO: hay errores rojos. No se debe publicar hasta corregirlos.")
    elif counts.get("WARNING", 0):
        lines.append("AVISO: hay warnings amarillos. Revision admin obligatoria antes de publicar en una futura fase.")
    else:
        lines.append("Preview limpio: listo para preparar la fase futura de confirmacion escrita, todavia sin publicar.")
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
        f"{row.get('status')} - [{row.get('item_kind')}] {row.get('item_woo_id')} - {row.get('name')}",
        f"propuesta_id: {row.get('proposal_id')}",
        f"precio Woo actual: {row.get('woo_current_price')} - propuesto: {row.get('new_price')}",
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
    - actualiza WooCommerce con PUT solo despues de pasar esas validaciones
    - marca la propuesta como published en Supabase y actualiza el espejo cloud del precio
    """
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede publicar cambios en WooCommerce.")
    proposal_id = (proposal_id or "").strip()
    if not proposal_id:
        raise CloudAuditError("Debes indicar --proposal-id. En v11.4 solo se publica una propuesta por operacion.")
    if (confirm or "").strip().upper() != "PUBLICAR":
        raise CloudAuditError("Publicacion bloqueada. Debes repetir con --confirm PUBLICAR.")

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
            raise CloudAuditError("No se encontro una propuesta aprobada real para ese proposal_id.")
        row = rows[0]
        if row.get("status") == "ERROR":
            raise CloudAuditError("Publicacion bloqueada por errores rojos en preview:\n" + _format_publish_row_for_confirm(row))
        if row.get("status") == "WARNING" and not acknowledge_warnings:
            raise CloudAuditError(
                "Publicacion requiere confirmacion de warnings amarillos. Revisa el preview y repite con --ack-woo-warning.\n"
                + _format_publish_row_for_confirm(row)
            )

        resp = session.client.table("price_change_proposals").select("*").eq("id", proposal_id).limit(1).execute()
        proposals = getattr(resp, "data", None) or []
        if not proposals:
            raise CloudAuditError("No se encontro la propuesta en Supabase.")
        proposal = proposals[0]
        if proposal.get("status") != "approved":
            raise CloudAuditError(f"La propuesta no esta approved. Estado actual: {proposal.get('status')}")

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
            raise CloudAuditError("Precio propuesto invalido. Debe ser mayor que 0.")

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
        if kind in {"product", "pack"}:
            woo_put_response = client.update_product_pricing(woo_id, pricing_payload)
            woo_written = True
            woo_verified = _fetch_woo_item_readonly(client, session, proposal)
            mirror_table = "products"
        elif kind == "variation":
            parent_id = cloud_item.get("parent_woo_id") or (_proposal_item_snapshot(proposal) or {}).get("parent_woo_id")
            if not parent_id:
                raise CloudAuditError(f"No se pudo determinar parent_woo_id para la variacion {woo_id}.")
            woo_put_response = client.update_variation_pricing(int(parent_id), woo_id, pricing_payload)
            woo_written = True
            woo_verified = _fetch_woo_item_readonly(client, session, proposal)
            mirror_table = "product_variations"
        else:
            raise CloudAuditError("item_kind invalido para publicacion WooCommerce.")

        verified_effective_price = _effective_woo_price(woo_verified)
        if verified_effective_price is None or abs(verified_effective_price - float(new_price)) > 0.009:
            # Compensacion inmediata: intenta devolver Woo al estado anterior.
            rollback_payload = {
                "regular_price": str((woo_before or {}).get("regular_price") or ""),
                "sale_price": str((woo_before or {}).get("sale_price") or ""),
            }
            try:
                if kind in {"product", "pack"}:
                    client.update_product_pricing(woo_id, rollback_payload)
                else:
                    client.update_variation_pricing(int(parent_id), woo_id, rollback_payload)
            except Exception:
                pass
            raise CloudAuditError(
                f"WooCommerce respondio a la escritura, pero la verificacion posterior devolvio precio efectivo "
                f"{verified_effective_price!r} en vez de {new_price:.2f}. Se intento restaurar el estado anterior."
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
                "price_before_publish": _effective_woo_price(woo_before),
                "published_price": verified_effective_price,
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
            # En algunos proyectos la tabla price_change_proposals no tenia published_by todavia.
            # Si WooCommerce ya fue actualizado, no dejamos la operacion medio fantasma:
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
                message="Fallo v11.5 publicacion de precio en WooCommerce.",
                error_detail=str(exc),
            ), settings)
        except Exception:
            pass
        raise
    finally:
        if lock_acquired:
            release_system_lock(session, lock_key, status="released")


def preview_price_proposal_group_publish(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
) -> dict[str, Any]:
    """Preflight completo de una propuesta logica. Solo realiza lecturas."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede preparar una publicacion WooCommerce.")
    rows = _fetch_price_proposal_rows(session, proposal_ids)
    woo = client or WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
    result_rows: list[dict[str, Any]] = []
    targets: dict[str, list[str]] = {}

    for proposal in rows:
        source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
        canonical_key = "-"
        status = "VALIDO"
        reason = "Validacion correcta."
        target: dict[str, Any] | None = None
        woo_data: dict[str, Any] | None = None
        old_price = _safe_money(proposal.get("old_price"))
        new_price = _safe_money(proposal.get("new_price"))
        woo_price = None
        messages: list[str] = []
        try:
            kind, _woo_id, canonical_key = _proposal_canonical_identity(proposal)
            proposal_status = str(proposal.get("status") or "").strip().lower()
            if _proposal_is_deleted(proposal):
                raise CloudAuditError("La linea esta borrada.")
            if proposal_status != "pending":
                raise CloudAuditError(f"Estado no publicable: {proposal_status or '-'}.")
            if old_price is None:
                raise CloudAuditError("Falta el precio registrado en la propuesta.")
            if new_price is None or new_price <= 0:
                raise CloudAuditError("El precio nuevo debe ser numerico y mayor que 0.")
            target = _remote_target_for_proposal(session, proposal)
            targets.setdefault(str(target["remote_key"]), []).append(canonical_key)
            woo_data = _fetch_remote_target(woo, target)
            woo_price = _effective_woo_price(woo_data)
            if woo_price is None:
                raise CloudAuditError("WooCommerce no devuelve un precio efectivo.")
            if abs(float(old_price) - float(woo_price)) > 0.009:
                status = "DESACTUALIZADA"
                reason = (
                    f"Precio registrado {old_price:.2f}; "
                    f"precio Woo actual {woo_price:.2f}."
                )
            else:
                validation = _price_safety_preview(
                    target["cloud_item"],
                    kind,
                    new_price,
                    settings,
                )
                messages = list(validation.get("messages") or [])
                if validation.get("status") == "ERROR":
                    status = "NO PUBLICABLE"
                    reason = " ".join(messages)
                elif validation.get("status") == "WARNING":
                    status = "WARNING"
                    reason = " ".join(messages)
        except Exception as exc:
            status = "ERROR"
            reason = str(exc)

        result_rows.append({
            "proposal_id": str(proposal.get("id") or ""),
            "canonical_key": canonical_key,
            "item_kind": str(source.get("ui_canonical_item_kind") or proposal.get("item_kind") or ""),
            "code": str(source.get("ui_line_code") or canonical_key),
            "name": str(source.get("ui_line_name") or proposal.get("name") or canonical_key),
            "proposal_status": str(proposal.get("status") or ""),
            "old_price_proposal": old_price,
            "woo_current_price": woo_price,
            "new_price": new_price,
            "delta": (new_price - woo_price) if new_price is not None and woo_price is not None else None,
            "status": status,
            "reason": reason,
            "messages": messages,
            "target": target,
            "woo_before": _pricing_snapshot(woo_data),
            "woo_before_full": woo_data,
            "proposal": proposal,
        })

    duplicate_keys = {
        remote_key: canonical_keys
        for remote_key, canonical_keys in targets.items()
        if len(canonical_keys) > 1
    }
    if duplicate_keys:
        for row in result_rows:
            target = row.get("target") or {}
            duplicate = duplicate_keys.get(str(target.get("remote_key") or ""))
            if duplicate:
                row["status"] = "DESTINO DUPLICADO"
                row["reason"] = (
                    f"El destino {target.get('remote_key')} tambien corresponde a: "
                    + ", ".join(duplicate)
                )

    counts: dict[str, int] = {
        "total": len(result_rows),
        "valid": 0,
        "warnings": 0,
        "errors": 0,
        "stale": 0,
    }
    for row in result_rows:
        state = row["status"]
        if state == "VALIDO":
            counts["valid"] += 1
        elif state == "WARNING":
            counts["warnings"] += 1
        else:
            counts["errors"] += 1
            if state == "DESACTUALIZADA":
                counts["stale"] += 1
    return {
        "rows": result_rows,
        "counts": counts,
        "blocking": counts["errors"] > 0,
        "duplicate_targets": duplicate_keys,
    }


def publish_price_proposal_group(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    confirm: str,
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
    progress=None,
) -> dict[str, Any]:
    """Publica un lote con preflight completo y rollback compensatorio."""
    settings = settings or load_settings()
    if (confirm or "") != "PUBLICAR":
        raise CloudAuditError("Publicacion bloqueada. Escribe exactamente PUBLICAR.")
    ids = list(dict.fromkeys(str(value).strip() for value in proposal_ids if str(value).strip()))
    rows_now = _fetch_price_proposal_rows(session, ids)
    statuses = {str(row.get("status") or "").strip().lower() for row in rows_now}
    if statuses == {"published"}:
        return {"already_published": True, "operation_id": None, "published": [], "rollback": []}
    if statuses != {"pending"}:
        raise CloudAuditError("La propuesta ya no esta completamente pendiente.")

    woo = client or WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
    preflight = preview_price_proposal_group_publish(
        session,
        proposal_ids=ids,
        settings=settings,
        client=woo,
    )
    if preflight["blocking"]:
        blocked = [
            f"{row['canonical_key']}: {row['status']} - {row['reason']}"
            for row in preflight["rows"]
            if row["status"] not in {"VALIDO", "WARNING"}
        ]
        raise CloudAuditError("Publicacion bloqueada antes de escribir:\n" + "\n".join(blocked[:10]))

    operation_id = new_operation_id("WOOBATCH")
    lock_digest = sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:16]
    lock_key = f"woocommerce_publish_group:{lock_digest}"
    lock_acquired = False
    marked_ids: list[str] = []
    published: list[dict[str, Any]] = []
    rollback: list[dict[str, Any]] = []
    try:
        acquire_system_lock(
            session,
            lock_key,
            details=f"Publicacion lote Cambio de Precios ({len(ids)} lineas)",
            ttl_minutes=30,
            settings=settings,
        )
        lock_acquired = True

        # Revalidacion de estado justo antes de snapshot/escritura.
        current_rows = _fetch_price_proposal_rows(session, ids)
        if any(str(row.get("status") or "").strip().lower() != "pending" for row in current_rows):
            raise CloudAuditError("La propuesta cambio de estado durante la confirmacion.")

        snapshot_data = [{
            "canonical_key": row["canonical_key"],
            "target": row["target"],
            "woo_before": row["woo_before"],
            "old_price": row["old_price_proposal"],
            "new_price": row["new_price"],
            "proposal_id": row["proposal_id"],
        } for row in preflight["rows"]]
        _ensure_snapshot_persisted(session, OperationSnapshot(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_price_proposal_group",
            entity_type="price_proposal_group",
            entity_id=lock_digest,
            before_data=_json_safe(snapshot_data),
            reason="Snapshot completo antes de publicar una propuesta logica en WooCommerce.",
        ))

        for row_id in ids:
            response = (
                session.client.table("price_change_proposals")
                .update({"status": "publishing", "error_message": None})
                .eq("id", row_id)
                .eq("status", "pending")
                .execute()
            )
            if not (getattr(response, "data", None) or []):
                raise CloudAuditError(f"No se pudo bloquear la linea {row_id} como publishing.")
            marked_ids.append(row_id)

        total = len(preflight["rows"])
        for index, row in enumerate(preflight["rows"], start=1):
            if progress:
                progress(index, total, row["canonical_key"])
            target = row["target"]
            payload, strategy = _pricing_payload_for_effective_price(
                row.get("woo_before_full") or {},
                float(row["new_price"]),
            )
            _write_remote_target(woo, target, payload)
            verified = _fetch_remote_target(woo, target)
            verified_price = _effective_woo_price(verified)
            if verified_price is None or abs(verified_price - float(row["new_price"])) > 0.009:
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el precio {row['new_price']:.2f}."
                )
            inventory_sync = sync_woocommerce_price_inventory_state(
                session,
                operation_id=operation_id,
                proposal=row["proposal"],
                cloud_item=target["cloud_item"],
                woo_id=target["woo_id"],
                before_price=_format_price_value(row["woo_current_price"]),
                verified_price=_format_price_value(verified_price),
                action="admin_publish_price_proposal_group",
                message="Precio Woo publicado y verificado desde propuesta logica.",
                metadata={
                    "canonical_key": row["canonical_key"],
                    "remote_key": target["remote_key"],
                    "proposal_id": row["proposal_id"],
                    "pricing_strategy": strategy,
                },
            )
            published.append({
                **row,
                "pricing_payload": payload,
                "pricing_strategy": strategy,
                "woo_after": verified,
                "inventory_sync": inventory_sync,
            })

        now = datetime.now(timezone.utc).isoformat()
        for row in preflight["rows"]:
            proposal = row["proposal"]
            source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
            update = {
                "status": "published",
                "published_at": now,
                "error_message": None,
                "source_row": {
                    **source,
                    "woo_publish": True,
                    "publish_operation_id": operation_id,
                    "published_by_email": session.email,
                    "published_machine": settings.machine_name,
                    "remote_target": _json_safe(row["target"]),
                    "price_before_publish": row["woo_current_price"],
                    "published_price": row["new_price"],
                },
            }
            update_response = (
                session.client.table("price_change_proposals")
                .update(update)
                .eq("id", row["proposal_id"])
                .eq("status", "publishing")
                .execute()
            )
            if not (getattr(update_response, "data", None) or []):
                raise CloudAuditError(
                    f"No se confirmo el estado published para {row['canonical_key']}."
                )

        _ensure_audit_persisted(session, AuditEvent(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_publish_price_proposal_group",
            status="OK",
            severity="INFO",
            entity_type="price_proposal_group",
            entity_id=lock_digest,
            before_data=_json_safe(snapshot_data),
            after_data=_json_safe({
                "published_count": len(published),
                "proposal_ids": ids,
            }),
            message="Propuesta logica publicada y verificada completamente en WooCommerce.",
        ), settings)
        return {
            "operation_id": operation_id,
            "published": published,
            "rollback": [],
            "rollback_complete": False,
            "already_published": False,
        }
    except Exception as exc:
        rollback_failures: list[str] = []
        for row in reversed(published):
            target = row["target"]
            before_payload = {
                "regular_price": str((row.get("woo_before") or {}).get("regular_price") or ""),
                "sale_price": str((row.get("woo_before") or {}).get("sale_price") or ""),
            }
            try:
                _write_remote_target(woo, target, before_payload)
                restored = _fetch_remote_target(woo, target)
                restored_price = _effective_woo_price(restored)
                expected = row["woo_current_price"]
                if expected is None or restored_price is None or abs(restored_price - expected) > 0.009:
                    raise CloudAuditError(
                        f"verificacion devolvio {restored_price!r}; esperado {expected!r}"
                    )
                sync_woocommerce_price_inventory_state(
                    session,
                    operation_id=operation_id,
                    proposal=row["proposal"],
                    cloud_item=target["cloud_item"],
                    woo_id=target["woo_id"],
                    before_price=_format_price_value(row["new_price"]),
                    verified_price=_format_price_value(restored_price),
                    action="admin_publish_price_proposal_group_rollback",
                    message="Rollback compensatorio verificado.",
                    metadata={"canonical_key": row["canonical_key"], "remote_key": target["remote_key"]},
                )
                rollback.append({"canonical_key": row["canonical_key"], "restored": True})
            except Exception as rollback_exc:
                rollback_failures.append(f"{row['canonical_key']}: {rollback_exc}")
                rollback.append({"canonical_key": row["canonical_key"], "restored": False})

        rollback_complete = bool(published) and not rollback_failures
        final_status = "pending" if not rollback_failures else "error"
        if not published:
            error_message = f"Fallo antes de la primera escritura Woo: {exc}"
        elif rollback_complete:
            error_message = f"Fallo de publicacion revertido: {exc}"
        else:
            error_message = f"ERROR CRITICO: {exc}; rollback incompleto: {' | '.join(rollback_failures)}"
        for row_id in marked_ids:
            try:
                current = next((row for row in rows_now if str(row.get("id")) == row_id), {})
                source = current.get("source_row") if isinstance(current.get("source_row"), dict) else {}
                session.client.table("price_change_proposals").update({
                    "status": final_status,
                    "error_message": error_message[:500],
                    "source_row": {
                        **source,
                        "publish_operation_id": operation_id,
                        "publish_failure": str(exc),
                        "rollback_complete": rollback_complete,
                        "rollback_failures": rollback_failures,
                    },
                }).eq("id", row_id).execute()
            except Exception:
                pass
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="woocommerce_publish",
                action="admin_publish_price_proposal_group_failed",
                status="ERROR",
                severity="ERROR" if not rollback_failures else "CRITICAL",
                entity_type="price_proposal_group",
                entity_id=lock_digest,
                before_data=_json_safe(preflight),
                after_data=_json_safe({"published": published, "rollback": rollback}),
                message="Fallo la publicacion del lote; se ejecuto rollback compensatorio.",
                error_detail=error_message,
            ), settings)
        except Exception:
            pass
        raise CloudAuditError(error_message) from exc
    finally:
        if lock_acquired:
            release_system_lock(session, lock_key, status="released")


def sync_price_proposal_inventory_prices(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
) -> dict[str, Any]:
    """Sincroniza solo los destinos Woo asociados a las propuestas indicadas."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede sincronizar precios WooCommerce.")
    rows = _fetch_price_proposal_rows(session, proposal_ids)
    woo = client or WooCommerceClient(
        settings.woocommerce_url,
        settings.consumer_key,
        settings.consumer_secret,
    )
    operation_id = new_operation_id("WOOPRICESYNC")
    synced: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_targets: dict[str, str] = {}
    for proposal in rows:
        target = _remote_target_for_proposal(session, proposal)
        canonical_key = str(target["canonical_key"])
        remote_key = str(target["remote_key"])
        previous = seen_targets.get(remote_key)
        if previous and previous != canonical_key:
            raise CloudAuditError(
                f"Sincronizacion bloqueada: {previous} y {canonical_key} comparten {remote_key}."
            )
        if previous:
            skipped.append({"canonical_key": canonical_key, "reason": "duplicate_member"})
            continue
        seen_targets[remote_key] = canonical_key
        current = _fetch_remote_target(woo, target)
        effective_price = _effective_woo_price(current)
        if effective_price is None:
            raise CloudAuditError(f"{canonical_key}: WooCommerce no devuelve precio efectivo.")
        inventory_sync = sync_woocommerce_price_inventory_state(
            session,
            operation_id=operation_id,
            proposal=proposal,
            cloud_item=target["cloud_item"],
            woo_id=target["woo_id"],
            before_price=None,
            verified_price=_format_price_value(effective_price),
            action="sync_price_proposal_inventory_prices",
            message="Precio Woo sincronizado al entrar o actualizar Cambio de Precios.",
            metadata={
                "canonical_key": canonical_key,
                "remote_key": remote_key,
                "proposal_id": proposal.get("id"),
            },
        )
        synced.append({
            "canonical_key": canonical_key,
            "remote_key": remote_key,
            "woo_price": effective_price,
            "inventory_sync": inventory_sync,
        })
    return {
        "operation_id": operation_id,
        "synced": synced,
        "skipped": skipped,
        "synced_count": len(synced),
    }


def _publish_operation_id(rows: list[dict[str, Any]]) -> str:
    operation_ids = {
        str((row.get("source_row") or {}).get("publish_operation_id") or "").strip()
        for row in rows
        if isinstance(row.get("source_row"), dict)
    }
    operation_ids.discard("")
    if len(operation_ids) != 1:
        raise CloudAuditError(
            "La propuesta publicada no tiene un unico snapshot de publicacion completo."
        )
    return next(iter(operation_ids))


def _fetch_publish_group_snapshot(session, operation_id: str) -> dict[str, Any]:
    response = (
        session.client.table("operation_snapshots")
        .select("*")
        .eq("operation_id", operation_id)
        .limit(1)
        .execute()
    )
    rows = list(getattr(response, "data", None) or [])
    if not rows:
        raise CloudAuditError(
            f"No existe el snapshot de publicacion {operation_id}. Restauracion bloqueada."
        )
    snapshot = rows[0]
    if str(snapshot.get("action") or "") != "admin_publish_price_proposal_group":
        raise CloudAuditError("El snapshot no corresponde a una publicacion de propuesta logica.")
    before_data = snapshot.get("before_data")
    if not isinstance(before_data, list) or not before_data:
        raise CloudAuditError("El snapshot de publicacion no contiene lineas restaurables.")
    return snapshot


def preview_price_proposal_group_restore(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
) -> dict[str, Any]:
    """Valida una restauracion completa sin escribir en WooCommerce."""
    settings = settings or load_settings()
    if (session.role or "").lower() != "admin":
        raise CloudAuditError("Solo admin puede preparar una restauracion WooCommerce.")
    rows = _fetch_price_proposal_rows(session, proposal_ids)
    if rows and all(
        bool((row.get("source_row") if isinstance(row.get("source_row"), dict) else {}).get("rolled_back"))
        for row in rows
    ):
        return {
            "rows": [],
            "counts": {"total": 0, "valid": 0, "errors": 0, "stale": 0},
            "blocking": True,
            "already_restored": True,
        }
    statuses = {str(row.get("status") or "").strip().lower() for row in rows}
    if statuses == {"rolled_back"}:
        return {
            "rows": [],
            "counts": {"total": 0, "valid": 0, "errors": 0, "stale": 0},
            "blocking": True,
            "already_restored": True,
        }
    if statuses != {"published"}:
        raise CloudAuditError("Solo se restauran propuestas completamente publicadas.")
    operation_id = _publish_operation_id(rows)
    snapshot = _fetch_publish_group_snapshot(session, operation_id)
    snapshot_rows = {
        str(row.get("proposal_id") or ""): row
        for row in snapshot.get("before_data") or []
        if isinstance(row, dict)
    }
    missing = [str(row.get("id")) for row in rows if str(row.get("id")) not in snapshot_rows]
    if missing:
        raise CloudAuditError(
            "El snapshot no cubre todas las lineas publicadas: " + ", ".join(missing[:5])
        )

    woo = client or WooCommerceClient(
        settings.woocommerce_url,
        settings.consumer_key,
        settings.consumer_secret,
    )
    result_rows: list[dict[str, Any]] = []
    targets: dict[str, list[str]] = {}
    for proposal in rows:
        proposal_id = str(proposal.get("id"))
        snapshot_row = snapshot_rows[proposal_id]
        canonical_key = "-"
        target = None
        woo_data = None
        current_price = None
        published_price = _safe_money(proposal.get("new_price"))
        restore_price = _safe_money(snapshot_row.get("old_price"))
        status = "VALIDO"
        reason = "Restauracion disponible."
        try:
            target = _remote_target_for_proposal(session, proposal)
            canonical_key = str(target["canonical_key"])
            snapshot_target = snapshot_row.get("target") or {}
            if str(snapshot_target.get("remote_key") or "") != str(target["remote_key"]):
                raise CloudAuditError("El destino actual no coincide con el snapshot publicado.")
            targets.setdefault(str(target["remote_key"]), []).append(canonical_key)
            woo_data = _fetch_remote_target(woo, target)
            current_price = _effective_woo_price(woo_data)
            if published_price is None or published_price <= 0:
                raise CloudAuditError("Falta el precio publicado por esta propuesta.")
            if restore_price is None or restore_price <= 0:
                raise CloudAuditError("Falta el precio anterior restaurable.")
            if current_price is None:
                raise CloudAuditError("WooCommerce no devuelve un precio efectivo.")
            if abs(current_price - published_price) > 0.009:
                status = "DESACTUALIZADO"
                reason = (
                    f"Woo actual {current_price:.2f}; esta propuesta publico "
                    f"{published_price:.2f}."
                )
        except Exception as exc:
            status = "DESTINO NO ENCONTRADO" if target is None else "ERROR"
            reason = str(exc)
        source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
        result_rows.append({
            "proposal_id": proposal_id,
            "canonical_key": canonical_key,
            "item_kind": str(source.get("ui_canonical_item_kind") or proposal.get("item_kind") or ""),
            "code": str(source.get("ui_line_code") or canonical_key),
            "name": str(source.get("ui_line_name") or proposal.get("name") or canonical_key),
            "published_price": published_price,
            "woo_current_price": current_price,
            "restore_price": restore_price,
            "status": status,
            "reason": reason,
            "target": target,
            "woo_current_snapshot": _pricing_snapshot(woo_data),
            "woo_current_full": woo_data,
            "woo_restore_snapshot": snapshot_row.get("woo_before") or {},
            "proposal": proposal,
        })

    duplicate_keys = {
        remote_key: canonical_keys
        for remote_key, canonical_keys in targets.items()
        if len(canonical_keys) > 1
    }
    for row in result_rows:
        target = row.get("target") or {}
        duplicate = duplicate_keys.get(str(target.get("remote_key") or ""))
        if duplicate:
            row["status"] = "DESTINO DUPLICADO"
            row["reason"] = (
                f"El destino {target.get('remote_key')} corresponde a: "
                + ", ".join(duplicate)
            )
    errors = sum(row["status"] != "VALIDO" for row in result_rows)
    stale = sum(row["status"] == "DESACTUALIZADO" for row in result_rows)
    return {
        "publish_operation_id": operation_id,
        "snapshot": snapshot,
        "rows": result_rows,
        "counts": {
            "total": len(result_rows),
            "valid": len(result_rows) - errors,
            "errors": errors,
            "stale": stale,
        },
        "blocking": errors > 0,
        "already_restored": False,
    }


def restore_price_proposal_group(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    confirm: str,
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
    progress=None,
) -> dict[str, Any]:
    """Restaura un lote publicado y compensa en orden inverso ante fallo parcial."""
    settings = settings or load_settings()
    if confirm != "RESTAURAR":
        raise CloudAuditError("Restauracion bloqueada. Escribe exactamente RESTAURAR.")
    ids = list(dict.fromkeys(str(value).strip() for value in proposal_ids if str(value).strip()))
    current_rows = _fetch_price_proposal_rows(session, ids)
    if current_rows and all(
        bool((row.get("source_row") if isinstance(row.get("source_row"), dict) else {}).get("rolled_back"))
        for row in current_rows
    ):
        return {
            "already_restored": True,
            "operation_id": None,
            "restored": [],
            "compensation": [],
        }
    statuses = {str(row.get("status") or "").strip().lower() for row in current_rows}
    if statuses == {"rolled_back"}:
        return {
            "already_restored": True,
            "operation_id": None,
            "restored": [],
            "compensation": [],
        }
    if statuses != {"published"}:
        raise CloudAuditError("La propuesta ya no esta completamente publicada.")

    woo = client or WooCommerceClient(
        settings.woocommerce_url,
        settings.consumer_key,
        settings.consumer_secret,
    )
    preview = preview_price_proposal_group_restore(
        session,
        proposal_ids=ids,
        settings=settings,
        client=woo,
    )
    if preview["blocking"]:
        blocked = [
            f"{row['canonical_key']}: {row['status']} - {row['reason']}"
            for row in preview["rows"]
            if row["status"] != "VALIDO"
        ]
        raise CloudAuditError(
            "Restauracion bloqueada antes de escribir:\n" + "\n".join(blocked[:10])
        )

    operation_id = new_operation_id("PRICERESTORE")
    publish_operation_id = str(preview["publish_operation_id"])
    lock_digest = sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:16]
    lock_key = f"woocommerce_restore_group:{lock_digest}"
    restored: list[dict[str, Any]] = []
    compensation: list[dict[str, Any]] = []
    lock_acquired = False
    try:
        acquire_system_lock(
            session,
            lock_key,
            details=f"Restauracion lote Cambio de Precios ({len(ids)} lineas)",
            ttl_minutes=30,
            settings=settings,
        )
        lock_acquired = True
        revalidated = _fetch_price_proposal_rows(session, ids)
        if any(str(row.get("status") or "").strip().lower() != "published" for row in revalidated):
            raise CloudAuditError("La propuesta cambio de estado durante la confirmacion.")

        restore_snapshot = [{
            "proposal_id": row["proposal_id"],
            "canonical_key": row["canonical_key"],
            "target": row["target"],
            "woo_before_restore": row["woo_current_snapshot"],
            "published_price": row["published_price"],
            "restore_price": row["restore_price"],
            "source_publish_operation_id": publish_operation_id,
        } for row in preview["rows"]]
        _ensure_snapshot_persisted(session, OperationSnapshot(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_restore_price_proposal_group",
            entity_type="price_proposal_group",
            entity_id=lock_digest,
            before_data=_json_safe(restore_snapshot),
            reason="Snapshot completo antes de restaurar una propuesta publicada.",
        ))

        total = len(preview["rows"])
        for index, row in enumerate(preview["rows"], start=1):
            if progress:
                progress(index, total, row["canonical_key"])
            target = row["target"]
            restore_snapshot_price = row.get("woo_restore_snapshot") or {}
            payload = {
                "regular_price": str(restore_snapshot_price.get("regular_price") or ""),
                "sale_price": str(restore_snapshot_price.get("sale_price") or ""),
            }
            _write_remote_target(woo, target, payload)
            verified = _fetch_remote_target(woo, target)
            verified_price = _effective_woo_price(verified)
            if verified_price is None or abs(verified_price - float(row["restore_price"])) > 0.009:
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el precio restaurado "
                    f"{row['restore_price']:.2f}."
                )
            inventory_sync = sync_woocommerce_price_inventory_state(
                session,
                operation_id=operation_id,
                proposal=row["proposal"],
                cloud_item=target["cloud_item"],
                woo_id=target["woo_id"],
                before_price=_format_price_value(row["woo_current_price"]),
                verified_price=_format_price_value(verified_price),
                action="admin_restore_price_proposal_group",
                message="Precio Woo restaurado desde snapshot y verificado.",
                metadata={
                    "canonical_key": row["canonical_key"],
                    "remote_key": target["remote_key"],
                    "proposal_id": row["proposal_id"],
                    "source_publish_operation_id": publish_operation_id,
                },
            )
            restored.append({
                **row,
                "restore_payload": payload,
                "woo_after": verified,
                "inventory_sync": inventory_sync,
            })

        now = datetime.now(timezone.utc).isoformat()
        for row in preview["rows"]:
            proposal = row["proposal"]
            source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
            restored_source = {
                **source,
                "rolled_back": True,
                "rolled_back_at": now,
                "rolled_back_by_email": session.email,
                "restore_operation_id": operation_id,
                "rolled_back_from_operation_id": publish_operation_id,
                "restored_price": row["restore_price"],
            }
            try:
                response = (
                    session.client.table("price_change_proposals")
                    .update({
                        "status": "rolled_back",
                        "error_message": None,
                        "source_row": restored_source,
                    })
                    .eq("id", row["proposal_id"])
                    .eq("status", "published")
                    .execute()
                )
            except Exception as status_exc:
                status_error = str(status_exc)
                if "23514" not in status_error and "price_change_proposals_status_check" not in status_error:
                    raise
                response = (
                    session.client.table("price_change_proposals")
                    .update({
                        "status": "published",
                        "error_message": None,
                        "source_row": {
                            **restored_source,
                            "rolled_back_status_fallback": True,
                        },
                    })
                    .eq("id", row["proposal_id"])
                    .eq("status", "published")
                    .execute()
                )
            if not (getattr(response, "data", None) or []):
                raise CloudAuditError(
                    f"No se confirmo el estado rolled_back para {row['canonical_key']}."
                )

        _ensure_audit_persisted(session, AuditEvent(
            operation_id=operation_id,
            module="woocommerce_publish",
            action="admin_restore_price_proposal_group",
            status="OK",
            severity="WARNING",
            entity_type="price_proposal_group",
            entity_id=lock_digest,
            before_data=_json_safe(restore_snapshot),
            after_data=_json_safe({
                "restored_count": len(restored),
                "proposal_ids": ids,
                "source_publish_operation_id": publish_operation_id,
            }),
            message="Propuesta logica restaurada y verificada completamente en WooCommerce.",
        ), settings)
        return {
            "operation_id": operation_id,
            "publish_operation_id": publish_operation_id,
            "restored": restored,
            "compensation": [],
            "compensation_complete": False,
            "already_restored": False,
        }
    except Exception as exc:
        compensation_failures: list[str] = []
        for row in reversed(restored):
            target = row["target"]
            current_snapshot = row.get("woo_current_snapshot") or {}
            payload = {
                "regular_price": str(current_snapshot.get("regular_price") or ""),
                "sale_price": str(current_snapshot.get("sale_price") or ""),
            }
            try:
                _write_remote_target(woo, target, payload)
                verified = _fetch_remote_target(woo, target)
                verified_price = _effective_woo_price(verified)
                expected = row["woo_current_price"]
                if expected is None or verified_price is None or abs(verified_price - expected) > 0.009:
                    raise CloudAuditError(
                        f"verificacion devolvio {verified_price!r}; esperado {expected!r}"
                    )
                sync_woocommerce_price_inventory_state(
                    session,
                    operation_id=operation_id,
                    proposal=row["proposal"],
                    cloud_item=target["cloud_item"],
                    woo_id=target["woo_id"],
                    before_price=_format_price_value(row["restore_price"]),
                    verified_price=_format_price_value(verified_price),
                    action="admin_restore_price_proposal_group_compensation",
                    message="Compensacion de restauracion verificada.",
                    metadata={
                        "canonical_key": row["canonical_key"],
                        "remote_key": target["remote_key"],
                        "source_publish_operation_id": publish_operation_id,
                    },
                )
                compensation.append({"canonical_key": row["canonical_key"], "restored": True})
            except Exception as compensation_exc:
                compensation_failures.append(f"{row['canonical_key']}: {compensation_exc}")
                compensation.append({"canonical_key": row["canonical_key"], "restored": False})

        compensation_complete = bool(restored) and not compensation_failures
        if compensation_complete:
            original_by_id = {str(row.get("id")): row for row in current_rows}
            for row_id in ids:
                original = original_by_id.get(row_id) or {}
                try:
                    session.client.table("price_change_proposals").update({
                        "status": "published",
                        "error_message": None,
                        "source_row": original.get("source_row") or {},
                    }).eq("id", row_id).execute()
                except Exception:
                    pass
        if not restored:
            error_message = f"Fallo antes de la primera escritura Woo: {exc}"
        elif compensation_complete:
            error_message = f"Fallo de restauracion compensado: {exc}"
        else:
            error_message = (
                f"ERROR CRITICO: {exc}; compensacion incompleta: "
                + " | ".join(compensation_failures)
            )
        if compensation_failures:
            for row in current_rows:
                try:
                    source = row.get("source_row") if isinstance(row.get("source_row"), dict) else {}
                    session.client.table("price_change_proposals").update({
                        "status": "error",
                        "error_message": error_message[:500],
                        "source_row": {
                            **source,
                            "restore_operation_id": operation_id,
                            "restore_failure": str(exc),
                            "restore_compensation_complete": False,
                            "restore_compensation_failures": compensation_failures,
                        },
                    }).eq("id", row.get("id")).execute()
                except Exception:
                    pass
        try:
            write_audit_event(session, AuditEvent(
                operation_id=operation_id,
                module="woocommerce_publish",
                action="admin_restore_price_proposal_group_failed",
                status="ERROR",
                severity="ERROR" if not compensation_failures else "CRITICAL",
                entity_type="price_proposal_group",
                entity_id=lock_digest,
                before_data=_json_safe(preview),
                after_data=_json_safe({
                    "restored": restored,
                    "compensation": compensation,
                }),
                message="Fallo la restauracion del lote; se ejecuto compensacion.",
                error_detail=error_message,
            ), settings)
        except Exception:
            pass
        raise CloudAuditError(error_message) from exc
    finally:
        if lock_acquired:
            release_system_lock(session, lock_key, status="released")


def format_woocommerce_publish_result(result: dict[str, Any]) -> str:
    row = result.get("preview_row") or {}
    lines = [
        "PUBLICACION WOOCOMMERCE COMPLETADA",
        "=" * 44,
        f"operation_id: {result.get('operation_id')}",
        f"item: [{result.get('item_kind')}] {result.get('woo_id')} - {row.get('name')}",
        f"propuesta_id: {(result.get('proposal') or {}).get('id')}",
        f"nuevo precio efectivo verificado: {result.get('verified_effective_price'):.2f}",
        "Supabase fue actualizado y la propuesta quedo como published.",
        "Caja negra: audit_log + operation_snapshot generados.",
    ]
    if row.get("status") == "WARNING":
        lines.append("AVISO: se publico con warnings reconocidos explicitamente por admin.")
    return "\n".join(lines)



proposal_item_snapshot = _proposal_item_snapshot
fetch_cloud_item_for_proposal = _fetch_cloud_item_for_proposal
fetch_woo_item_readonly = _fetch_woo_item_readonly
fetch_approved_price_proposals = _fetch_approved_price_proposals
format_publish_row_for_confirm = _format_publish_row_for_confirm

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


class PriceProposalRevalidationRequired(CloudAuditError):
    """Signals that a draft was refreshed from live Woo data and needs review."""

    def __init__(self, message: str, *, preview: dict[str, Any], differences: list[dict[str, Any]]):
        super().__init__(message)
        self.preview = preview
        self.differences = differences




def _blackbox_record_exists(session, table: str, operation_id: str) -> bool:
    """Comprueba que la caja negra se persistio realmente, no solo que la RPC respondio."""
    try:
        resp = session.client.table(table).select("id,operation_id").eq("operation_id", operation_id).limit(1).execute()
        if bool(getattr(resp, "data", None) or []):
            return True
    except Exception:
        pass
    read_rpc_by_table = {
        "operation_snapshots": "futonhub_read_operation_snapshots",
        "audit_logs": "futonhub_read_audit_logs",
    }
    rpc_name = read_rpc_by_table.get(table)
    if not rpc_name:
        return False
    try:
        response = session.client.rpc(
            rpc_name,
            {"p_user_id": getattr(session, "user_id", None), "p_limit": 200},
        ).execute()
        rows = getattr(response, "data", None) or []
        return any(str(row.get("operation_id") or "") == str(operation_id) for row in rows if isinstance(row, dict))
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


def _authenticated_actor(session) -> dict[str, str]:
    user_id = str(getattr(session, "user_id", None) or "").strip()
    user_name = str(
        getattr(session, "user_name", None)
        or getattr(session, "display_name", None)
        or getattr(session, "email", None)
        or ""
    ).strip()
    if not user_id or not user_name:
        raise CloudAuditError("La aplicacion de precios requiere una sesion de usuario identificable.")
    return {"user_id": user_id, "user_name": user_name}

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
        "date_on_sale_from_gmt": data.get("date_on_sale_from_gmt"),
        "date_on_sale_to_gmt": data.get("date_on_sale_to_gmt"),
    }


def _pricing_restore_payload(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = snapshot or {}
    return {
        key: snapshot.get(key)
        for key in (
            "regular_price",
            "sale_price",
            "date_on_sale_from",
            "date_on_sale_to",
            "date_on_sale_from_gmt",
            "date_on_sale_to_gmt",
        )
        if key in snapshot
    }


def _pricing_payload_matches(expected: dict[str, Any], actual: dict[str, Any] | None) -> bool:
    actual = actual or {}
    for key, value in expected.items():
        actual_value = actual.get(key)
        if key in {"regular_price", "sale_price"}:
            if value in (None, "") and actual_value in (None, ""):
                continue
            expected_money = _safe_money(value)
            actual_money = _safe_money(actual_value)
            if (
                expected_money is not None
                and actual_money is not None
                and abs(expected_money - actual_money) <= 0.009
            ):
                continue
        if actual_value != value:
            return False
    return True


def _positive_int_or_none(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _live_woo_remote_kind(data: dict[str, Any] | None) -> str:
    row = data or {}
    row_type = str(row.get("type") or "").strip().lower()
    if row_type == "variation" or _positive_int_or_none(row.get("parent_id")):
        return "variation"
    return "product"


def _validate_remote_target_shape(target: dict[str, Any]) -> dict[str, Any]:
    remote_kind = str(target.get("remote_kind") or "").strip().lower()
    woo_id = _positive_int_or_none(target.get("woo_id"))
    if woo_id is None:
        raise CloudAuditError("El destino Woo no tiene woo_id positivo.")
    endpoint = str(target.get("endpoint") or "").strip()
    remote_key = str(target.get("remote_key") or "").strip()
    if remote_kind == "product":
        expected_endpoint = f"products/{woo_id}"
        expected_key = f"product:{woo_id}"
        if endpoint != expected_endpoint or remote_key != expected_key:
            raise CloudAuditError(
                f"Destino product mal formado: endpoint={endpoint or '-'} remote_key={remote_key or '-'}."
            )
        if _positive_int_or_none(target.get("parent_woo_id")) is not None:
            raise CloudAuditError("Un destino product no puede llevar parent_woo_id positivo.")
        return target
    if remote_kind == "variation":
        parent_id = _positive_int_or_none(target.get("parent_woo_id"))
        if parent_id is None:
            raise CloudAuditError("El destino variation no tiene parent_woo_id positivo.")
        expected_endpoint = f"products/{parent_id}/variations/{woo_id}"
        expected_key = f"variation:{parent_id}:{woo_id}"
        if endpoint != expected_endpoint or remote_key != expected_key:
            raise CloudAuditError(
                f"Destino variation mal formado: endpoint={endpoint or '-'} remote_key={remote_key or '-'}."
            )
        return target
    raise CloudAuditError("El destino Woo debe ser product o variation.")


def _remote_identity_revalidation_from_live(
    target: dict[str, Any] | None,
    woo_data: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not target or not woo_data:
        return None
    target_kind = str(target.get("remote_kind") or "").strip().lower()
    live_kind = _live_woo_remote_kind(woo_data)
    if target_kind == live_kind:
        return None
    live_woo_id = _positive_int_or_none(woo_data.get("id"))
    live_parent_id = _positive_int_or_none(woo_data.get("parent_id"))
    target_woo_id = _positive_int_or_none(target.get("woo_id"))
    if live_kind == "variation" and live_woo_id == target_woo_id and live_parent_id:
        return {
            "can_revalidate": True,
            "woo_item_kind": "variation",
            "woo_id": live_woo_id,
            "woo_parent_id": live_parent_id,
            "parent_woo_id": live_parent_id,
            "woo_sku": woo_data.get("sku"),
            "reason": (
                "WooCommerce devuelve una variation con parent_id para un destino "
                f"persistido como {target_kind}. El borrador debe revalidarse antes de publicar."
            ),
        }
    return {
        "can_revalidate": False,
        "reason": (
            "WooCommerce devuelve una identidad remota incompatible con el destino "
            f"persistido: esperado={target_kind or '-'} live={live_kind or '-'}."
        )
    }


def _remote_target_diagnostic(
    row: dict[str, Any],
    target: dict[str, Any],
    *,
    put_attempted: bool,
    put_confirmed: bool,
) -> str:
    return (
        "remote_target="
        f"entry_origin={row.get('entry_origin') or '-'}; "
        f"canonical_key={row.get('canonical_key') or target.get('canonical_key') or '-'}; "
        f"canonical_kind={target.get('canonical_kind') or '-'}; "
        f"remote_kind={target.get('remote_kind') or '-'}; "
        f"woo_id={target.get('woo_id') or '-'}; "
        f"parent_woo_id={target.get('parent_woo_id') or '-'}; "
        f"endpoint={target.get('endpoint') or '-'}; "
        f"put_attempted={bool(put_attempted)}; "
        f"put_confirmed={bool(put_confirmed)}"
    )


def _proposal_entry_origin(proposal: dict[str, Any]) -> str:
    source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
    return str(source.get("entry_origin") or "DIRECT_ITEM").strip().upper()


def _is_revalidatable_publish_row(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().upper()
    reason = str(row.get("reason") or "").strip().lower()
    if status in {"DESACTUALIZADA", "REMOTE_IDENTITY_REVALIDATION_REQUIRED"}:
        return True
    proposal = row.get("proposal") if isinstance(row.get("proposal"), dict) else {}
    if (
        status == "BLOCKED_MISSING_PRICE_CONTEXT"
        and _proposal_entry_origin(proposal) == "DERIVED_COMBINATION"
        and "contexto woo" in reason
    ):
        return True
    return status == "BLOCKED_INVALID_PAYLOAD" and (
        "contexto woo cambio" in reason
        or "payload recalculado" in reason
    )


def _refresh_price_proposal_group_from_live(
    session,
    rows: list[dict[str, Any]],
    *,
    actor: dict[str, str],
    settings: Settings,
) -> list[dict[str, Any]]:
    """Refreshes only a pending draft after a live divergence; never writes Woo."""
    if not rows or any(not _is_revalidatable_publish_row(row) for row in rows):
        raise CloudAuditError("La divergencia no puede recalcularse automaticamente.")
    operation_id = new_operation_id("PRICEREVALIDATE")
    now = datetime.now(timezone.utc).isoformat()
    before_rows = [dict(row.get("proposal") or {}) for row in rows]
    write_snapshot(session, OperationSnapshot(
        operation_id=operation_id,
        module="price_change_proposals",
        action="user_revalidate_price_proposal_group",
        entity_type="price_proposal_group",
        entity_id=str((rows[0].get("proposal") or {}).get("id") or "group"),
        before_data=_json_safe(before_rows),
        reason="Snapshot antes de recalcular un borrador por divergencia live de Woo.",
    ))
    differences: list[dict[str, Any]] = []
    for row in rows:
        proposal = dict(row.get("proposal") or {})
        proposal_id = str(proposal.get("id") or "")
        source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
        live_context = dict(row.get("woo_before_full") or {})
        live_price = _effective_woo_price(live_context)
        if not proposal_id or live_price is None:
            raise CloudAuditError("No se pudo identificar o valorar una linea divergente.")
        previous_old = _safe_money(proposal.get("old_price"))
        previous_new = _safe_money(proposal.get("new_price"))
        refreshed_new = previous_new
        entry_origin = _proposal_entry_origin(proposal)
        if entry_origin == "DERIVED_COMBINATION":
            component_delta = _safe_money(source.get("component_delta"))
            if component_delta is None:
                raise CloudAuditError(f"{proposal_id} no conserva el delta derivado exacto.")
            refreshed_new = float(live_price) + float(component_delta)
        if refreshed_new is None or refreshed_new <= 0:
            raise CloudAuditError(f"{proposal_id} produce un precio recalculado invalido.")
        payload, strategy = _pricing_payload_for_effective_price(live_context, float(refreshed_new))
        target = row.get("target") or {}
        identity_update = _remote_identity_revalidation_from_live(target, live_context)
        if identity_update and not identity_update.get("can_revalidate"):
            raise CloudAuditError("La identidad remota live no puede revalidarse automaticamente.")
        revalidated_parent_id = (
            identity_update.get("parent_woo_id")
            if identity_update
            else target.get("parent_woo_id")
        )
        refreshed_context = {
            **_pricing_snapshot(live_context),
            "id": live_context.get("id"),
            "parent_id": revalidated_parent_id,
            "date_modified": live_context.get("date_modified"),
            "date_modified_gmt": live_context.get("date_modified_gmt"),
        }
        item_snapshot = dict(source.get("item_snapshot") or {})
        item_snapshot.update({
            "price": float(live_price),
            "regular_price": live_context.get("regular_price"),
            "sale_price": live_context.get("sale_price"),
            "price_at_creation": float(live_price),
            "proposed_price": float(refreshed_new),
        })
        if identity_update:
            item_snapshot.update({
                "woo_id": identity_update["woo_id"],
                "woo_parent_id": identity_update["woo_parent_id"],
                "parent_woo_id": identity_update["parent_woo_id"],
                "woo_item_kind": identity_update["woo_item_kind"],
                "item_kind": identity_update["woo_item_kind"],
                "type": identity_update["woo_item_kind"],
                "sku": identity_update.get("woo_sku") or item_snapshot.get("sku"),
            })
        source_update = {
            **source,
            "workflow_state": "READY",
            "ready_at_utc": now,
            "revalidated_by_user_id": actor["user_id"],
            "revalidated_by_user_name": actor["user_name"],
            "revalidated_machine": settings.machine_name,
            "revalidation_operation_id": operation_id,
            "price_at_creation": float(live_price),
            "proposed_price": float(refreshed_new),
            "proposal_price_snapshot": {
                "price_at_creation": float(live_price),
                "proposed_price": float(refreshed_new),
                "delta": float(refreshed_new) - float(live_price),
                "source": "woo_live_revalidation",
            },
            "item_snapshot": item_snapshot,
        }
        update_payload = {
            "old_price": float(live_price),
            "new_price": float(refreshed_new),
            "delta": float(refreshed_new) - float(live_price),
            "source_row": source_update,
        }
        if identity_update:
            source_update.update({
                "ui_canonical_item_kind": identity_update["woo_item_kind"],
                "ui_canonical_woo_id": identity_update["woo_id"],
                "woo_id": identity_update["woo_id"],
                "woo_parent_id": identity_update["woo_parent_id"],
                "parent_woo_id": identity_update["parent_woo_id"],
                "woo_item_kind": identity_update["woo_item_kind"],
                "woo_sku": identity_update.get("woo_sku") or source.get("woo_sku") or "",
                "remote_identity_revalidated_from": {
                    "previous_remote_kind": target.get("remote_kind"),
                    "previous_remote_key": target.get("remote_key"),
                    "live_remote_kind": identity_update["woo_item_kind"],
                    "live_parent_woo_id": identity_update["woo_parent_id"],
                    "source": "woo_live_identity_revalidation",
                },
            })
            update_payload.update({
                "item_kind": identity_update["woo_item_kind"],
                "item_woo_id": identity_update["woo_id"],
                "local_id": identity_update["woo_id"],
            })
        if entry_origin == "DERIVED_COMBINATION":
            source_update.update({
                "derived_status": "NO_CHANGE" if abs(float(refreshed_new) - float(live_price)) <= 0.009 else "READY",
                "publication_allowed": "YES",
                "blocking_reason": "",
                "woo_price_context_at_creation": refreshed_context,
                "future_pricing_payload": dict(payload),
                "pricing_strategy": strategy,
            })
        update_response = (
            session.client.table("price_change_proposals")
            .update(update_payload)
            .eq("id", proposal_id)
            .eq("status", "pending")
            .execute()
        )
        if not (getattr(update_response, "data", None) or []):
            raise CloudAuditError(f"No se confirmo la revalidacion del borrador {proposal_id}.")
        differences.append({
            "proposal_id": proposal_id,
            "entry_origin": entry_origin,
            "canonical_key": row.get("canonical_key"),
            "code": row.get("code"),
            "name": row.get("name"),
            "previous_old_price": previous_old,
            "live_old_price": float(live_price),
            "previous_new_price": previous_new,
            "revalidated_new_price": float(refreshed_new),
            "previous_reason": row.get("reason"),
            "pricing_payload": dict(payload),
            "remote_identity_revalidated": bool(identity_update),
        })
    write_audit_event(session, AuditEvent(
        operation_id=operation_id,
        module="price_change_proposals",
        action="user_revalidate_price_proposal_group",
        status="OK",
        severity="WARNING",
        entity_type="price_proposal_group",
        entity_id=str((rows[0].get("proposal") or {}).get("id") or "group"),
        before_data=_json_safe(before_rows),
        after_data=_json_safe({
            "differences": differences,
            "revalidated_by_user_id": actor["user_id"],
            "revalidated_by_user_name": actor["user_name"],
            "revalidated_machine": settings.machine_name,
        }),
        message="Borrador recalculado tras detectar divergencias live; no se publico en Woo.",
    ), settings)
    return differences


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
        return _validate_remote_target_shape({
            "canonical_key": canonical_key,
            "canonical_kind": kind,
            "woo_id": woo_id,
            "remote_kind": "product",
            "remote_key": f"product:{woo_id}",
            "endpoint": f"products/{woo_id}",
            "cloud_item": cloud_item,
        })
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
        return _validate_remote_target_shape({
            "canonical_key": canonical_key,
            "canonical_kind": kind,
            "woo_id": woo_id,
            "parent_woo_id": parent_id,
            "remote_kind": "variation",
            "remote_key": f"variation:{parent_id}:{woo_id}",
            "endpoint": f"products/{parent_id}/variations/{woo_id}",
            "cloud_item": cloud_item,
        })
    raise CloudAuditError(f"{canonical_key} no tiene destino Woo publicable.")


def _fetch_remote_target(client: WooCommerceClient, target: dict[str, Any]) -> dict[str, Any]:
    target = _validate_remote_target_shape(dict(target))
    return client.get(str(target["endpoint"])).json()


def _write_remote_target(
    client: WooCommerceClient,
    target: dict[str, Any],
    payload: dict[str, Any],
) -> Any:
    target = _validate_remote_target_shape(dict(target))
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
    _authenticated_actor(session)
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
        lines.append("AVISO: hay warnings amarillos. Revisa sus diferencias antes de aplicar.")
    else:
        lines.append("Preview limpio: listo para revalidar y aplicar sin un paso adicional.")
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
    """Compatibilidad historica para publicar una propuesta ya aprobada.

    Seguridad:
    - requiere usuario autenticado
    - exige proposal_id concreto
    - genera preview justo antes
    - bloquea ERROR
    - WARNING exige --ack-woo-warning
    - actualiza WooCommerce con PUT solo despues de pasar esas validaciones
    - marca la propuesta como published en Supabase y actualiza el espejo cloud del precio
    """
    settings = settings or load_settings()
    _authenticated_actor(session)
    proposal_id = (proposal_id or "").strip()
    if not proposal_id:
        raise CloudAuditError("Debes indicar --proposal-id. En v11.4 solo se publica una propuesta por operacion.")
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
    rows = _fetch_price_proposal_rows(session, proposal_ids)
    woo = client or WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
    result_rows: list[dict[str, Any]] = []
    targets: dict[str, list[str]] = {}
    exclusions_by_id: dict[str, dict[str, Any]] = {}

    for proposal in rows:
        source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
        for exclusion in source.get("combination_exclusions") or []:
            if isinstance(exclusion, dict):
                key = str(exclusion.get("combination_woo_id") or exclusion.get("combination_sku") or "")
                if key:
                    exclusions_by_id[key] = dict(exclusion)

    for proposal in rows:
        source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
        modified_components = [
            component
            for component in (source.get("modified_components") or [])
            if isinstance(component, dict)
        ]
        component_summary = " | ".join(
            f"{component.get('component_sku') or component.get('component_item_id') or '-'}: "
            f"{component.get('old_price') or '-'} -> {component.get('new_price') or '-'} "
            f"(delta {component.get('weighted_delta') or component.get('unit_delta') or '-'})"
            for component in modified_components
        )
        quantity_summary = ", ".join(
            f"{component.get('component_sku') or component.get('component_item_id') or '-'} x{component.get('quantity') or '1'}"
            for component in modified_components
        )
        canonical_key = "-"
        status = "VALIDO"
        reason = "Validacion correcta."
        target: dict[str, Any] | None = None
        woo_data: dict[str, Any] | None = None
        old_price = _safe_money(proposal.get("old_price"))
        new_price = _safe_money(proposal.get("new_price"))
        woo_price = None
        messages: list[str] = []
        entry_origin = _proposal_entry_origin(proposal)
        pricing_payload: dict[str, Any] = {}
        pricing_strategy = ""
        functional_status = "READY"
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
            remote_identity_update = _remote_identity_revalidation_from_live(target, woo_data)
            if remote_identity_update:
                status = (
                    "REMOTE_IDENTITY_REVALIDATION_REQUIRED"
                    if remote_identity_update.get("can_revalidate")
                    else "BLOCKED_REMOTE_IDENTITY_MISMATCH"
                )
                functional_status = (
                    "BLOCKED_REMOTE_IDENTITY_REVALIDATION_REQUIRED"
                    if remote_identity_update.get("can_revalidate")
                    else "BLOCKED_REMOTE_IDENTITY_MISMATCH"
                )
                reason = str(remote_identity_update.get("reason") or "")
            if entry_origin == "DERIVED_COMBINATION":
                persisted_status = str(source.get("derived_status") or "").strip().upper()
                if source.get("publication_allowed") != "YES" or persisted_status not in {"READY", "NO_CHANGE"}:
                    status = persisted_status if persisted_status.startswith("BLOCKED_") else "BLOCKED_TRACEABILITY_ERROR"
                    functional_status = status
                    reason = str(source.get("blocking_reason") or "La linea derivada no esta autorizada para publicacion.")
                stored_context = source.get("woo_price_context_at_creation")
                if status.startswith("BLOCKED_"):
                    pass
                elif not isinstance(stored_context, dict):
                    status = "BLOCKED_MISSING_PRICE_CONTEXT"
                    functional_status = status
                    reason = "La combinacion derivada no conserva el contexto Woo completo de creacion."
                else:
                    required = {
                        "id", "parent_id", "price", "regular_price", "sale_price", "on_sale",
                        "date_on_sale_from", "date_on_sale_to",
                    }
                    missing = sorted(required.difference(stored_context))
                    if not stored_context.get("date_modified") and not stored_context.get("date_modified_gmt"):
                        missing.append("date_modified/date_modified_gmt")
                    if missing:
                        status = "BLOCKED_MISSING_PRICE_CONTEXT"
                        functional_status = status
                        reason = "Falta contexto Woo persistido: " + ", ".join(missing)
                    else:
                        current_context = {
                            **_pricing_snapshot(woo_data),
                            "id": woo_data.get("id"),
                            "parent_id": target.get("parent_woo_id"),
                            "date_modified": woo_data.get("date_modified"),
                            "date_modified_gmt": woo_data.get("date_modified_gmt"),
                        }
                        changed = [
                            key for key in stored_context
                            if key in current_context and stored_context.get(key) != current_context.get(key)
                        ]
                        if changed:
                            status = "BLOCKED_INVALID_PAYLOAD"
                            functional_status = status
                            reason = "El contexto Woo cambio desde el preview: " + ", ".join(sorted(changed))
            if str(status).startswith("BLOCKED_") or str(functional_status).startswith("BLOCKED_"):
                pass
            elif abs(float(old_price) - float(woo_price)) > 0.009:
                status = "DESACTUALIZADA"
                functional_status = "BLOCKED_INVALID_PAYLOAD" if entry_origin == "DERIVED_COMBINATION" else status
                reason = (
                    f"Precio registrado {old_price:.2f}; "
                    f"precio Woo actual {woo_price:.2f}."
                )
            elif abs(float(new_price) - float(woo_price)) <= 0.009:
                status = "NO_CHANGE"
                functional_status = "NO_CHANGE"
                reason = "NO_ACTION_ALREADY_CURRENT: WooCommerce ya contiene el precio solicitado."
                pricing_payload = {}
                pricing_strategy = "no_change"
            else:
                pricing_payload, pricing_strategy = _pricing_payload_for_effective_price(
                    woo_data,
                    float(new_price),
                )
                if entry_origin == "DERIVED_COMBINATION":
                    persisted_payload = source.get("future_pricing_payload")
                    if not isinstance(persisted_payload, dict) or persisted_payload != pricing_payload:
                        status = "BLOCKED_INVALID_PAYLOAD"
                        functional_status = status
                        reason = "El payload recalculado no coincide con el preview persistido."
                        raise CloudAuditError(reason)
                validation = _price_safety_preview(
                    target["cloud_item"],
                    kind,
                    new_price,
                    settings,
                )
                messages = list(validation.get("messages") or [])
                if validation.get("status") == "ERROR":
                    status = "NO PUBLICABLE"
                    functional_status = "BLOCKED_INVALID_PAYLOAD"
                    reason = " ".join(messages)
                elif validation.get("status") == "WARNING":
                    status = "READY" if entry_origin == "DERIVED_COMBINATION" else "WARNING"
                    functional_status = "READY"
                    reason = " ".join(messages)
                elif entry_origin == "DERIVED_COMBINATION":
                    status = "NO_CHANGE" if abs(float(new_price) - float(woo_price)) <= 0.009 else "READY"
                    functional_status = status
        except Exception as exc:
            if not str(status).startswith("BLOCKED_"):
                status = "ERROR"
                functional_status = "BLOCKED_TRACEABILITY_ERROR"
                reason = str(exc)

        result_rows.append({
            "proposal_id": str(proposal.get("id") or ""),
            "canonical_key": canonical_key,
            "item_kind": str(source.get("ui_canonical_item_kind") or proposal.get("item_kind") or ""),
            "code": str(source.get("ui_line_code") or canonical_key),
            "name": str(source.get("ui_line_name") or proposal.get("name") or canonical_key),
            "proposal_status": str(proposal.get("status") or ""),
            "entry_origin": entry_origin,
            "functional_status": functional_status,
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
            "pricing_payload": pricing_payload,
            "pricing_strategy": pricing_strategy,
            "component_summary": component_summary,
            "quantity_summary": quantity_summary,
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
                row["functional_status"] = "BLOCKED_TRACEABILITY_ERROR"
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
        "direct": sum(_proposal_entry_origin(row) == "DIRECT_ITEM" for row in rows),
        "derived": sum(_proposal_entry_origin(row) == "DERIVED_COMBINATION" for row in rows),
        "woo_writes": 0,
        "excluded": len(exclusions_by_id),
    }
    for row in result_rows:
        state = row["status"]
        if state in {"VALIDO", "READY", "NO_CHANGE"}:
            counts["valid"] += 1
            if state != "NO_CHANGE":
                counts["woo_writes"] += 1
        elif state == "WARNING":
            counts["warnings"] += 1
            counts["woo_writes"] += 1
        else:
            counts["errors"] += 1
            if state == "DESACTUALIZADA":
                counts["stale"] += 1
    blocked_rows = [
        row
        for row in result_rows
        if row["status"] not in {"VALIDO", "WARNING", "READY", "NO_CHANGE"}
    ]
    return {
        "rows": result_rows,
        "exclusions": list(exclusions_by_id.values()),
        "counts": counts,
        "blocking": counts["errors"] > 0,
        "revalidation_possible": bool(blocked_rows) and all(
            _is_revalidatable_publish_row(row) for row in blocked_rows
        ),
        "duplicate_targets": duplicate_keys,
    }


def publish_price_proposal_group(
    session,
    *,
    proposal_ids: list[str] | tuple[str, ...],
    confirm: str | None = None,
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
    progress=None,
) -> dict[str, Any]:
    """Publica un lote con preflight completo y rollback compensatorio."""
    settings = settings or load_settings()
    actor = _authenticated_actor(session)
    ids = list(dict.fromkeys(str(value).strip() for value in proposal_ids if str(value).strip()))
    rows_now = _fetch_price_proposal_rows(session, ids)
    statuses = {str(row.get("status") or "").strip().lower() for row in rows_now}
    if statuses == {"published"}:
        return {"already_published": True, "operation_id": None, "published": [], "rollback": []}
    if statuses != {"pending"}:
        raise CloudAuditError("La propuesta ya no esta completamente pendiente.")

    woo = client or WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)

    def require_review_after_live_refresh(candidate: dict[str, Any]) -> None:
        if not candidate.get("blocking"):
            return
        blocked_rows = [
            row
            for row in candidate.get("rows") or []
            if row.get("status") not in {"VALIDO", "WARNING", "READY", "NO_CHANGE"}
        ]
        if not blocked_rows or any(not _is_revalidatable_publish_row(row) for row in blocked_rows):
            return
        refreshed_missing_context = any(
            str(row.get("status") or "").strip().upper() == "BLOCKED_MISSING_PRICE_CONTEXT"
            for row in blocked_rows
        )
        differences = _refresh_price_proposal_group_from_live(
            session,
            blocked_rows,
            actor=actor,
            settings=settings,
        )
        refreshed = preview_price_proposal_group_publish(
            session,
            proposal_ids=ids,
            settings=settings,
            client=woo,
        )
        if refreshed.get("blocking"):
            raise CloudAuditError("La propuesta sigue bloqueada despues de recalcular el borrador.")
        difference_by_id = {str(row.get("proposal_id")): row for row in differences}
        display_rows: list[dict[str, Any]] = []
        for row in refreshed.get("rows") or []:
            difference = difference_by_id.get(str(row.get("proposal_id")))
            if not difference:
                continue
            display_rows.append({
                **row,
                "old_price_proposal": difference.get("previous_old_price"),
                "woo_current_price": difference.get("live_old_price"),
                "new_price": difference.get("revalidated_new_price"),
                "delta": (
                    float(difference["revalidated_new_price"]) - float(difference["live_old_price"])
                    if difference.get("revalidated_new_price") is not None
                    and difference.get("live_old_price") is not None
                    else None
                ),
                "reason": (
                    "El contexto Woo de esta relacion necesitaba actualizarse. "
                    "El borrador se actualizo; revisa los cambios antes de publicar."
                    if refreshed_missing_context
                    else "Borrador recalculado con el estado live. Revisa esta diferencia antes de aplicar."
                ),
            })
        refreshed.update({
            "revalidation_required": True,
            "revalidation_differences": differences,
            "display_rows": display_rows,
        })
        message = (
            "El contexto Woo de esta relacion necesita actualizarse. "
            "Se ha actualizado el borrador sin publicar; revisa los cambios antes de aplicar."
            if refreshed_missing_context
            else "La informacion cambio desde el preview. El borrador se recalculo sin publicar; revisa las diferencias."
        )
        raise PriceProposalRevalidationRequired(
            message,
            preview=refreshed,
            differences=differences,
        )

    preflight = preview_price_proposal_group_publish(
        session,
        proposal_ids=ids,
        settings=settings,
        client=woo,
    )
    require_review_after_live_refresh(preflight)
    if preflight["blocking"]:
        blocked = [
            f"{row['canonical_key']}: {row['status']} - {row['reason']}"
            for row in preflight["rows"]
            if row["status"] not in {"VALIDO", "WARNING", "READY", "NO_CHANGE"}
        ]
        raise CloudAuditError("Publicacion bloqueada antes de escribir:\n" + "\n".join(blocked[:10]))

    operation_id = new_operation_id("WOOBATCH")
    lock_digest = sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:16]
    lock_key = f"woocommerce_publish_group:{lock_digest}"
    lock_acquired = False
    marked_ids: list[str] = []
    published: list[dict[str, Any]] = []
    rollback: list[dict[str, Any]] = []
    failed_write: dict[str, Any] | None = None
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
            raise CloudAuditError("La propuesta cambio de estado durante la revalidacion.")

        locked_preflight = preview_price_proposal_group_publish(
            session,
            proposal_ids=ids,
            settings=settings,
            client=woo,
        )
        require_review_after_live_refresh(locked_preflight)
        if locked_preflight["blocking"]:
            changed = [
                f"{row['canonical_key']}: {row['status']} - {row['reason']}"
                for row in locked_preflight["rows"]
                if row["status"] not in {"VALIDO", "WARNING", "READY", "NO_CHANGE"}
            ]
            raise CloudAuditError(
                "La revalidacion detecto cambios; revisa solo estas diferencias:\n"
                + "\n".join(changed[:20])
            )
        initial_by_id = {row["proposal_id"]: row for row in preflight["rows"]}
        changed_rows: list[str] = []
        for row in locked_preflight["rows"]:
            previous = initial_by_id.get(row["proposal_id"]) or {}
            if (
                previous.get("woo_before") != row.get("woo_before")
                or previous.get("pricing_payload") != row.get("pricing_payload")
                or previous.get("new_price") != row.get("new_price")
            ):
                changed_rows.append(
                    f"{row['canonical_key']}: contexto o payload Woo cambio desde el preview."
                )
        if changed_rows:
            raise CloudAuditError(
                "La revalidacion detecto cambios; no se publico nada:\n"
                + "\n".join(changed_rows[:20])
            )
        preflight = locked_preflight

        snapshot_data = [{
            "canonical_key": row["canonical_key"],
            "target": row["target"],
            "woo_before": row["woo_before"],
            "old_price": row["old_price_proposal"],
            "new_price": row["new_price"],
            "proposal_id": row["proposal_id"],
            "entry_origin": row.get("entry_origin"),
            "pricing_payload": row.get("pricing_payload"),
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
            current = next((row for row in current_rows if str(row.get("id")) == row_id), {})
            source = current.get("source_row") if isinstance(current.get("source_row"), dict) else {}
            response = (
                session.client.table("price_change_proposals")
                .update({
                    "status": "publishing",
                    "error_message": None,
                    "source_row": {
                        **source,
                        "workflow_state": "APPLYING",
                        "applying_by_user_id": actor["user_id"],
                        "applying_by_user_name": actor["user_name"],
                        "applying_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                })
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
            payload = dict(row.get("pricing_payload") or {})
            strategy = str(row.get("pricing_strategy") or "")
            if not payload:
                payload, strategy = _pricing_payload_for_effective_price(
                    row.get("woo_before_full") or {},
                    float(row["new_price"]),
                )
            if row.get("status") == "NO_CHANGE":
                published.append({
                    **row,
                    "pricing_payload": {},
                    "pricing_strategy": "no_change",
                    "woo_after": row.get("woo_before_full") or {},
                    "inventory_sync": None,
                    "write_performed": False,
                    "put_attempted": False,
                    "put_ok": False,
                    "verify_ok": True,
                })
                continue
            put_attempted = False
            put_attempted = True
            try:
                _write_remote_target(woo, target, payload)
            except Exception as write_exc:
                failed_write = {
                    "proposal_id": row.get("proposal_id"),
                    "entry_origin": row.get("entry_origin"),
                    "canonical_key": row.get("canonical_key"),
                    "target": _json_safe(target),
                    "pricing_payload": _json_safe(payload),
                    "put_attempted": True,
                    "put_ok": False,
                    "put_confirmed": False,
                    "write_performed": False,
                    "diagnostic": _remote_target_diagnostic(
                        row,
                        target,
                        put_attempted=True,
                        put_confirmed=False,
                    ),
                }
                raise CloudAuditError(
                    f"{row['canonical_key']} fallo PUT Woo: {write_exc}. "
                    + failed_write["diagnostic"]
                ) from write_exc
            verified = _fetch_remote_target(woo, target)
            verified_price = _effective_woo_price(verified)
            if verified_price is None or abs(verified_price - float(row["new_price"])) > 0.009:
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el precio {row['new_price']:.2f}."
                )
            if not _pricing_payload_matches(payload, verified):
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el payload de precio exacto enviado."
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
                "write_performed": True,
                "put_attempted": put_attempted,
                "put_ok": True,
                "verify_ok": True,
            })

        now = datetime.now(timezone.utc).isoformat()
        published_by_id = {str(row.get("proposal_id")): row for row in published}
        for row in preflight["rows"]:
            proposal = row["proposal"]
            source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
            published_row = published_by_id.get(str(row.get("proposal_id"))) or {}
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
                    "workflow_state": "APPLIED",
                    "applied_by_user_id": actor["user_id"],
                    "applied_by_user_name": actor["user_name"],
                    "applied_at_utc": now,
                    "applied_machine": settings.machine_name,
                    "snapshot_operation_id": operation_id,
                    "entry_origin": row.get("entry_origin") or _proposal_entry_origin(proposal),
                    "remote_target": _json_safe(row["target"]),
                    "woo_before_apply": _json_safe(row.get("woo_before_full") or row.get("woo_before") or {}),
                    "pricing_payload_sent": _json_safe(published_row.get("pricing_payload") or row.get("pricing_payload") or {}),
                    "pricing_strategy_applied": published_row.get("pricing_strategy") or row.get("pricing_strategy"),
                    "woo_after_verified": _json_safe(published_row.get("woo_after") or {}),
                    "woo_write_performed": bool(published_row.get("write_performed")),
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

        line_results = [{
            "proposal_id": row.get("proposal_id"),
            "entry_origin": row.get("entry_origin"),
            "canonical_key": row.get("canonical_key"),
            "woo_id": (row.get("target") or {}).get("woo_id"),
            "parent_woo_id": (row.get("target") or {}).get("parent_woo_id"),
            "old_price": row.get("woo_current_price"),
            "new_price": row.get("new_price"),
            "pricing_payload": row.get("pricing_payload"),
            "write_performed": bool(row.get("write_performed")),
            "put_attempted": bool(row.get("put_attempted")),
            "put_ok": bool(row.get("put_ok")),
            "verify_ok": bool(row.get("verify_ok")),
            "result": "APPLIED" if row.get("write_performed") else "NO_ACTION_ALREADY_CURRENT",
        } for row in published]
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
                "direct_count": preflight.get("counts", {}).get("direct", 0),
                "derived_count": preflight.get("counts", {}).get("derived", 0),
                "woo_write_count": sum(bool(row.get("write_performed")) for row in published),
                "applied_by_user_id": actor["user_id"],
                "applied_by_user_name": actor["user_name"],
                "applied_machine": settings.machine_name,
                "proposal_ids": ids,
                "line_results": line_results,
                "exclusions": _json_safe(preflight.get("exclusions") or []),
            }),
            message="Propuesta logica publicada y verificada completamente en WooCommerce.",
        ), settings)
        return {
            "operation_id": operation_id,
            "published": published,
            "rollback": [],
            "rollback_complete": False,
            "already_published": False,
            "line_results": line_results,
            "counts": {
                "direct": preflight.get("counts", {}).get("direct", 0),
                "derived": preflight.get("counts", {}).get("derived", 0),
                "woo_writes": sum(bool(row.get("write_performed")) for row in published),
            },
        }
    except Exception as exc:
        if isinstance(exc, PriceProposalRevalidationRequired):
            raise
        rollback_failures: list[str] = []
        for row in reversed(published):
            if not row.get("write_performed", True):
                rollback.append({"canonical_key": row["canonical_key"], "restored": True, "write_performed": False})
                continue
            target = row["target"]
            before_payload = _pricing_restore_payload(row.get("woo_before") or {})
            try:
                _write_remote_target(woo, target, before_payload)
                restored = _fetch_remote_target(woo, target)
                restored_price = _effective_woo_price(restored)
                expected = row["woo_current_price"]
                if expected is None or restored_price is None or abs(restored_price - expected) > 0.009:
                    raise CloudAuditError(
                        f"verificacion devolvio {restored_price!r}; esperado {expected!r}"
                    )
                if not _pricing_payload_matches(before_payload, restored):
                    raise CloudAuditError("el rollback no confirmo el payload Woo anterior exacto")
                row["woo_after_rollback"] = restored
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
                published_row = next((row for row in published if str(row.get("proposal_id")) == row_id), {})
                rollback_context = published_row.get("woo_after_rollback")
                refreshed_context: dict[str, Any] = {}
                if _proposal_entry_origin(current) == "DERIVED_COMBINATION" and isinstance(rollback_context, dict):
                    target = published_row.get("target") or {}
                    refreshed_context = {
                        "woo_price_context_at_creation": {
                            **_pricing_snapshot(rollback_context),
                            "id": rollback_context.get("id"),
                            "parent_id": target.get("parent_woo_id"),
                            "date_modified": rollback_context.get("date_modified"),
                            "date_modified_gmt": rollback_context.get("date_modified_gmt"),
                        }
                    }
                session.client.table("price_change_proposals").update({
                    "status": final_status,
                    "error_message": error_message[:500],
                    "source_row": {
                        **source,
                        "publish_operation_id": operation_id,
                        "publish_failure": str(exc),
                        "workflow_state": "PARTIAL_FAILURE" if published else "FAILED",
                        "failed_by_user_id": actor["user_id"],
                        "failed_by_user_name": actor["user_name"],
                        "failed_at_utc": datetime.now(timezone.utc).isoformat(),
                        **refreshed_context,
                        "rollback_complete": rollback_complete,
                        "rollback_failures": rollback_failures,
                        **({"publish_failed_write": failed_write} if failed_write else {}),
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
                after_data=_json_safe({
                    "published": published,
                    "rollback": rollback,
                    "exclusions": preflight.get("exclusions") or [],
                    "failed_by_user_id": actor["user_id"],
                    "failed_by_user_name": actor["user_name"],
                    "failed_machine": settings.machine_name,
                    "failed_write": failed_write,
                }),
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
    confirm: str | None = None,
    settings: Settings | None = None,
    client: WooCommerceClient | None = None,
    progress=None,
) -> dict[str, Any]:
    """Restaura un lote publicado y compensa en orden inverso ante fallo parcial."""
    settings = settings or load_settings()
    actor = _authenticated_actor(session)
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
            payload = _pricing_restore_payload(restore_snapshot_price)
            _write_remote_target(woo, target, payload)
            verified = _fetch_remote_target(woo, target)
            verified_price = _effective_woo_price(verified)
            if verified_price is None or abs(verified_price - float(row["restore_price"])) > 0.009:
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el precio restaurado "
                    f"{row['restore_price']:.2f}."
                )
            if not _pricing_payload_matches(payload, verified):
                raise CloudAuditError(
                    f"{row['canonical_key']} no confirmo el payload historico exacto."
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
        restored_by_id = {str(row.get("proposal_id")): row for row in restored}
        for row in preview["rows"]:
            proposal = row["proposal"]
            source = proposal.get("source_row") if isinstance(proposal.get("source_row"), dict) else {}
            restored_row = restored_by_id.get(str(row.get("proposal_id"))) or {}
            restored_source = {
                **source,
                "rolled_back": True,
                "rolled_back_at": now,
                "rolled_back_by_email": session.email,
                "restore_operation_id": operation_id,
                "rolled_back_from_operation_id": publish_operation_id,
                "restored_price": row["restore_price"],
                "workflow_state": "ROLLED_BACK",
                "rolled_back_by_user_id": actor["user_id"],
                "rolled_back_by_user_name": actor["user_name"],
                "rolled_back_at_utc": now,
                "rolled_back_machine": settings.machine_name,
                "rollback_snapshot_operation_id": operation_id,
                "rollback_payload_sent": _json_safe(restored_row.get("restore_payload") or {}),
                "rollback_woo_after_verified": _json_safe(restored_row.get("woo_after") or {}),
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

        rollback_line_results = [{
            "proposal_id": row.get("proposal_id"),
            "canonical_key": row.get("canonical_key"),
            "woo_id": (row.get("target") or {}).get("woo_id"),
            "parent_woo_id": (row.get("target") or {}).get("parent_woo_id"),
            "published_price": row.get("published_price"),
            "restored_price": row.get("restore_price"),
            "restore_payload": row.get("restore_payload"),
            "result": "ROLLED_BACK",
        } for row in restored]
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
                "rolled_back_by_user_id": actor["user_id"],
                "rolled_back_by_user_name": actor["user_name"],
                "rolled_back_machine": settings.machine_name,
                "line_results": rollback_line_results,
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
            "line_results": rollback_line_results,
        }
    except Exception as exc:
        compensation_failures: list[str] = []
        for row in reversed(restored):
            target = row["target"]
            current_snapshot = row.get("woo_current_snapshot") or {}
            payload = _pricing_restore_payload(current_snapshot)
            try:
                _write_remote_target(woo, target, payload)
                verified = _fetch_remote_target(woo, target)
                verified_price = _effective_woo_price(verified)
                expected = row["woo_current_price"]
                if expected is None or verified_price is None or abs(verified_price - expected) > 0.009:
                    raise CloudAuditError(
                        f"verificacion devolvio {verified_price!r}; esperado {expected!r}"
                    )
                if not _pricing_payload_matches(payload, verified):
                    raise CloudAuditError("la compensacion no confirmo el payload exacto")
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

"""Read-only initial Woo price context for the price proposal workspace.

The module intentionally has no dependency on price publication or replica
synchronisation.  It resolves only direct physical items and reads Woo through
GET requests.  Combination reads remain demand-driven when an item is added to
a proposal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping

from futonhub.cloud.services.woocommerce_publish import _effective_woo_price


ProgressCallback = Callable[[dict[str, Any]], None]


TERMINAL_SYNC_STATUSES = frozenset({
    "READY",
    "NO_WOO_LINK",
    "ERROR_SYNC",
    "INELIGIBLE_RECORD_TYPE",
    "QUARANTINED",
    "MISSING_PHYSICAL_IDENTITY",
    "SHARED_WOO_TARGET",
    "NOT_PRICE_OPERABLE",
    "PRIVATE_WOO_ENTITY",
})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "si"}


def _same_money(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left).replace(",", ".")) == Decimal(str(right).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _physical_key(row: Mapping[str, Any]) -> str:
    source = dict(row.get("source") or {})
    return _text(
        source.get("physical_item_id")
        or source.get("item_id")
        or row.get("physical_item_id")
        or row.get("code")
    )


def _source_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(row.get("source") or {})
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
    physical_item_id = _text(source.get("physical_item_id") or source.get("item_id") or snapshot.get("item_id"))
    physical_sku = _text(
        source.get("physical_sku")
        or source.get("hub_item_code")
        or snapshot.get("hub_item_code")
        or snapshot.get("heca_reference")
        or row.get("code")
    )
    kind = _text(source.get("woo_item_kind") or source.get("item_kind") or snapshot.get("woo_item_kind")).lower()
    woo_sku = _text(source.get("woo_sku") or snapshot.get("woo_sku") or snapshot.get("sku"))
    woo_id = _text(source.get("woo_id") or snapshot.get("woo_id"))
    parent_id = _text(source.get("woo_parent_id") or source.get("parent_woo_id") or snapshot.get("woo_parent_id"))
    return {
        "physical_item_id": physical_item_id,
        "physical_sku": physical_sku,
        "woo_item_kind": kind,
        "woo_sku": woo_sku,
        "woo_id": woo_id,
        "woo_parent_id": parent_id,
        "record_type": _text(snapshot.get("item_record_type") or snapshot.get("hub_search_record_type")).lower(),
        "is_pack": _bool(snapshot.get("is_pack")) or _bool(source.get("is_pack")),
        "operational_status": _text(source.get("operational_status") or snapshot.get("operational_status")),
        "quarantine_group": _text(source.get("quarantine_group") or snapshot.get("quarantine_group")),
        "price_operable": source.get("price_operable", snapshot.get("price_operable")),
    }


def _is_physical_direct_row(row: Mapping[str, Any]) -> bool:
    source = dict(row.get("source") or {})
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
    record_type = _text(snapshot.get("item_record_type") or snapshot.get("hub_search_record_type")).lower()
    if _bool(snapshot.get("is_pack")) or _bool(source.get("is_pack")):
        return False
    return record_type not in {"alias", "component_placeholder", "woo_pack", "manual_pack"}


def _terminal_exclusion(identity: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return the terminal local state for a row that must not call Woo."""
    record_type = _text(identity.get("record_type")).lower()
    if _bool(identity.get("is_pack")) or record_type in {"alias", "component_placeholder", "woo_pack", "manual_pack"}:
        return "INELIGIBLE_RECORD_TYPE", "El tipo de registro no admite precio directo en propuestas."
    operational_status = _text(identity.get("operational_status"))
    if operational_status and operational_status != "OPERATIONAL_BASELINE":
        return "QUARANTINED", "El articulo no pertenece al baseline operativo de precios."
    if _text(identity.get("quarantine_group")):
        return "QUARANTINED", "El articulo pertenece a un grupo de cuarentena."
    if identity.get("price_operable") is not None and not _bool(identity.get("price_operable")):
        return "NOT_PRICE_OPERABLE", "El articulo esta marcado como no operable para precio directo."
    if not _text(identity.get("physical_item_id")) or not _text(identity.get("physical_sku")):
        return "MISSING_PHYSICAL_IDENTITY", "Falta item_id o SKU fisico exacto para una lectura Woo segura."
    return None


def _exact_destination_key(identity: Mapping[str, Any]) -> str:
    kind = _text(identity.get("woo_item_kind")).lower()
    woo_id = _text(identity.get("woo_id"))
    physical_sku = _text(identity.get("physical_sku"))
    woo_sku = _text(identity.get("woo_sku"))
    parent_id = _text(identity.get("woo_parent_id"))
    if kind not in {"product", "variation"} or not woo_id or not physical_sku or woo_sku != physical_sku:
        return ""
    if kind == "variation" and not parent_id:
        return ""
    return f"{kind}:{woo_id}:{parent_id}"


def _error_context(
    identity: Mapping[str, Any],
    *,
    status: str,
    error: str,
    stored_price: Any,
) -> dict[str, Any]:
    return {
        "physical_item_id": _text(identity.get("physical_item_id")),
        "physical_sku": _text(identity.get("physical_sku")),
        "woo_id": _text(identity.get("woo_id")),
        "woo_parent_id": _text(identity.get("woo_parent_id")),
        "woo_item_kind": _text(identity.get("woo_item_kind")),
        "regular_price": "",
        "sale_price": "",
        "price": "",
        "effective_price": "",
        "date_on_sale_from": "",
        "date_on_sale_to": "",
        "status": "",
        "woo_date_modified": "",
        "price_source": "WOO_LIVE_UNAVAILABLE",
        "price_read_at": "",
        "sync_status": status,
        "terminal_status": status,
        # A terminal error can remain visible in the catalog, but it must never
        # become a direct price target.
        "price_change_eligible": "NO",
        "is_terminal": True,
        "error": error,
        "stored_price": stored_price,
    }


def _response_object(response: Any) -> dict[str, Any]:
    payload = response.json() if hasattr(response, "json") else response
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], Mapping):
        return dict(payload[0])
    raise RuntimeError("Woo no devolvio un objeto unico para el enlace directo.")


def _linked_live_price_trace(identity: Mapping[str, Any], woo_client: Any) -> dict[str, Any]:
    """Read and validate the literal local Woo link through one target GET."""
    woo_id = _text(identity.get("woo_id"))
    parent_id = _text(identity.get("woo_parent_id"))
    kind = _text(identity.get("woo_item_kind")).lower()
    sku = _text(identity.get("physical_sku"))
    endpoint = f"products/{woo_id}" if kind == "product" else f"products/{parent_id}/variations/{woo_id}"
    entity = _response_object(woo_client.get(endpoint))
    if _text(entity.get("id")) != woo_id:
        raise RuntimeError("Woo devolvio un id distinto del enlace exacto solicitado.")
    if _text(entity.get("sku")) != sku:
        raise RuntimeError("Woo devolvio un SKU distinto del articulo fisico exacto.")
    if kind == "variation" and _text(entity.get("parent_id")) != parent_id:
        raise RuntimeError("Woo devolvio una variacion con parent_id distinto.")
    effective = _effective_woo_price(entity)
    if effective in (None, ""):
        raise RuntimeError("Woo no devolvio un precio efectivo calculable.")
    return {
        "status": "READY",
        "physical_item_id": _text(identity.get("physical_item_id")),
        "physical_sku": sku,
        "resolved_woo_id": int(woo_id),
        "resolved_parent_woo_id": parent_id or None,
        "resolved_item_kind": kind,
        "woo_endpoint": endpoint,
        "woo_regular_price": _text(entity.get("regular_price")),
        "woo_sale_price": _text(entity.get("sale_price")),
        "woo_effective_price": f"{Decimal(str(effective)).quantize(Decimal('0.01')):.2f}",
        "final_old_price": float(Decimal(str(effective))),
        "read_at": datetime.now(timezone.utc).isoformat(),
        "resolution_source": "LOCAL_LINK_WOO_GET_VERIFIED",
        "resolution": {
            "woo_id": int(woo_id),
            "woo_parent_id": parent_id or None,
            "woo_item_kind": kind,
            "woo_sku": sku,
            "entity": entity,
        },
    }


def sync_initial_live_prices(
    rows: Iterable[Mapping[str, Any]],
    *,
    woo_client: Any,
    session: Any | None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build a direct Woo price context without mutating Supabase or Woo.

    Each exact local Woo destination is queried once.  Rows without a literal
    physical-to-Woo link remain visible as ``NO_WOO_LINK`` and rows whose GET
    fails remain visible as ``ERROR_SYNC``.  Neither path returns a cached
    price that could be used operationally.
    """
    source_rows = [dict(row) for row in rows]
    contexts: dict[str, dict[str, Any]] = {}
    destination_rows: dict[str, list[dict[str, Any]]] = {}
    row_outcomes: list[dict[str, Any]] = []
    counts = {
        "visible": len(source_rows),
        "catalog_physical": 0,
        "physical": 0,
        "eligible": 0,
        "total": 0,
        "processed": 0,
        "updated": 0,
        "unchanged": 0,
        "no_link": 0,
        "excluded": 0,
        "errors": 0,
        "ready": 0,
        "terminal_non_ready": 0,
        "pending_after_completion": 0,
        "deduplicated": 0,
        "destinations_product": 0,
        "destinations_variation": 0,
        "private": 0,
    }

    def record_outcome(
        row: Mapping[str, Any],
        identity: Mapping[str, Any],
        *,
        sync_status: str,
        terminal_status: str,
        exclusion_reason: str = "",
        destination_key: str = "",
    ) -> None:
        row_outcomes.append({
            "row": dict(row),
            "identity": dict(identity),
            "sync_status": sync_status,
            "terminal_status": terminal_status,
            "exclusion_reason": exclusion_reason,
            "deduplicated_woo_key": destination_key,
        })

    def emit(**event: Any) -> None:
        if progress_callback is not None:
            progress_callback({"counts": dict(counts), **event})

    for position, row in enumerate(source_rows, start=1):
        identity = _source_identity(row)
        physical_key = _physical_key(row) or f"visible-row:{position}"
        record_type = _text(identity.get("record_type")).lower()
        if not _bool(identity.get("is_pack")) and record_type not in {"alias", "component_placeholder", "woo_pack", "manual_pack"}:
            # This is the physical catalogue shown by the module. It includes
            # quarantined and unlinked rows so the visible total is never
            # reduced merely to make it equal the GET candidate count.
            counts["catalog_physical"] += 1
        terminal = _terminal_exclusion(identity)
        if terminal is not None:
            status, reason = terminal
            contexts[physical_key] = _error_context(
                identity,
                status=status,
                error=reason,
                stored_price=row.get("cached_price"),
            )
            counts["excluded"] += 1
            counts["terminal_non_ready"] += 1
            record_outcome(row, identity, sync_status=status, terminal_status=status, exclusion_reason=reason)
            continue

        counts["physical"] += 1
        destination_key = _exact_destination_key(identity)
        if not destination_key:
            reason = "No existe un enlace Woo exacto y verificable para este articulo fisico."
            counts["no_link"] += 1
            counts["terminal_non_ready"] += 1
            contexts[physical_key] = _error_context(
                identity,
                status="NO_WOO_LINK",
                error=reason,
                stored_price=row.get("cached_price"),
            )
            record_outcome(row, identity, sync_status="NO_WOO_LINK", terminal_status="NO_WOO_LINK", exclusion_reason=reason)
            continue
        counts["eligible"] += 1
        destination_rows.setdefault(destination_key, []).append(row)

    counts["total"] = len(destination_rows)
    counts["deduplicated"] = max(0, counts["eligible"] - counts["total"])
    counts["destinations_product"] = sum(key.startswith("product:") for key in destination_rows)
    counts["destinations_variation"] = sum(key.startswith("variation:") for key in destination_rows)
    emit(phase="START", current_sku="", current_name="")

    for destination_key, grouped_rows in destination_rows.items():
        primary = grouped_rows[0]
        identity = _source_identity(primary)
        emit(
            phase="READING_WOO_DIRECT",
            current_sku=identity["physical_sku"],
            current_name=_text(primary.get("name")),
            destination_key=destination_key,
        )
        try:
            trace = _linked_live_price_trace(identity, woo_client)
            if trace.get("status") != "READY":
                raise RuntimeError(_text(trace.get("reason")) or "Woo no devolvio un precio efectivo.")
            resolution = dict(trace.get("resolution") or {})
            entity = dict(resolution.get("entity") or {})
            physical_keys = sorted({_physical_key(row) for row in grouped_rows if _physical_key(row)})
            shared = len(physical_keys) > 1
            is_private = _text(entity.get("status")).lower() == "private"
            terminal_status = "PRIVATE_WOO_ENTITY" if is_private else ("SHARED_WOO_TARGET" if shared else "READY")
            context_base = {
                "woo_id": resolution.get("woo_id"),
                "woo_parent_id": resolution.get("woo_parent_id") or "",
                "woo_item_kind": resolution.get("woo_item_kind") or "",
                "woo_sku": resolution.get("woo_sku") or "",
                "regular_price": _text(entity.get("regular_price")),
                "sale_price": _text(entity.get("sale_price")),
                "price": _text(entity.get("price")),
                # Preserve exact identity for traceability, but a private Woo
                # entity is never an operational price destination.
                "effective_price": "" if is_private else _text(trace.get("woo_effective_price")),
                "date_on_sale_from": entity.get("date_on_sale_from") or "",
                "date_on_sale_to": entity.get("date_on_sale_to") or "",
                "status": _text(entity.get("status")),
                "woo_date_modified": entity.get("date_modified_gmt") or entity.get("date_modified") or "",
                "price_source": "WOO_LIVE_PRIVATE_INELIGIBLE" if is_private else "WOO_LIVE",
                "price_read_at": trace.get("read_at") or "",
                "sync_status": "PRIVATE_WOO_ENTITY" if is_private else "READY",
                "terminal_status": terminal_status,
                "price_change_eligible": "NO" if is_private else "YES",
                "is_terminal": True,
                "shared_woo_target": shared,
                "shared_physical_item_ids": physical_keys,
                "deduplicated_woo_key": destination_key,
                "error": "La entidad Woo es private y queda excluida de Cambio de Precios." if is_private else "",
                "woo_endpoint": trace.get("woo_endpoint") or "",
                "price_source_trace": dict(trace),
            }
            for row in grouped_rows:
                row_identity = _source_identity(row)
                key = _physical_key(row)
                context = {
                    **context_base,
                    "physical_item_id": row_identity["physical_item_id"],
                    "physical_sku": row_identity["physical_sku"],
                    "stored_price": row.get("cached_price"),
                }
                contexts[key] = context
                record_outcome(
                    row,
                    row_identity,
                    sync_status=context["sync_status"],
                    terminal_status=terminal_status,
                    exclusion_reason=context["error"],
                    destination_key=destination_key,
                )
                if is_private:
                    counts["private"] += 1
                    counts["excluded"] += 1
                    counts["terminal_non_ready"] += 1
                else:
                    counts["ready"] += 1
                    if _same_money(context["effective_price"], row.get("cached_price")):
                        counts["unchanged"] += 1
                    else:
                        counts["updated"] += 1
        except Exception as exc:
            counts["errors"] += len(grouped_rows)
            counts["terminal_non_ready"] += len(grouped_rows)
            for row in grouped_rows:
                row_identity = _source_identity(row)
                key = _physical_key(row)
                contexts[key] = _error_context(
                    row_identity,
                    status="ERROR_SYNC",
                    error=str(exc),
                    stored_price=row.get("cached_price"),
                )
                record_outcome(row, row_identity, sync_status="ERROR_SYNC", terminal_status="ERROR_SYNC", exclusion_reason=str(exc), destination_key=destination_key)
        counts["processed"] += 1
        emit(
            phase="READ_COMPLETE",
            current_sku=identity["physical_sku"],
            current_name=_text(primary.get("name")),
            destination_key=destination_key,
        )

    counts["pending_after_completion"] = sum(
        1 for outcome in row_outcomes if outcome["sync_status"] not in TERMINAL_SYNC_STATUSES
    )
    if counts["pending_after_completion"]:
        raise RuntimeError("La sincronizacion termino con filas sin estado terminal.")
    error_keys = sorted(key for key, context in contexts.items() if context.get("sync_status") == "ERROR_SYNC")
    emit(phase="COMPLETE", current_sku="", current_name="")
    return {
        "live_price_context_by_physical_item": contexts,
        "error_physical_item_ids": error_keys,
        "row_outcomes": row_outcomes,
        "counts": counts,
        "mode": "READ_ONLY_GET_AND_SELECT",
        "writes": {"woo": 0, "supabase": 0, "sql": 0},
    }


def terminal_sync_error(rows: Iterable[Mapping[str, Any]], error: str) -> dict[str, Any]:
    """Terminalize a failed worker without falling back to stored prices.

    This is used when the Woo client itself cannot be initialized. The local
    classifier still marks packs, aliases and quarantined rows accurately; any
    otherwise eligible direct destination receives ``ERROR_SYNC``.
    """
    class _UnavailableWoo:
        def get(self, _endpoint: str) -> None:
            raise RuntimeError(error)

    return sync_initial_live_prices(rows, woo_client=_UnavailableWoo(), session=None)

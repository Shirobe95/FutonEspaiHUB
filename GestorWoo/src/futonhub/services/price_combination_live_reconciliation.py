from __future__ import annotations

"""Read-only Woo/Supabase reconciliation for price-combination previews.

This module is deliberately separated from publishing and replica synchronization.
Every Supabase query is a ``select`` and every WooCommerce request is a ``GET``.
It is safe to use for a preview, audit or draft refresh: it has no dependency on
the mutation-oriented price proposal services.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping

from futonhub.cloud.services.woocommerce_publish import _effective_woo_price
from futonhub.services.combination_price_impact import (
    CombinationPriceImpactError,
    CombinationPriceImpactService,
)


_CENT = Decimal("0.01")
_PUBLISHED_STATUSES = frozenset({"publish"})
_MUTATION_METHODS = frozenset({"insert", "update", "upsert", "delete", "rpc"})
ProgressCallback = Callable[[dict[str, Any]], None]


class ReadOnlyAccessError(RuntimeError):
    """Raised when a consumer attempts a mutation through the audit adapter."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer.") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer.")
    return parsed


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", ".")).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Woo price is not numeric: {value!r}.") from exc


def _money_text(value: Decimal | None) -> str:
    return "" if value is None else f"{value.quantize(_CENT, rounding=ROUND_HALF_UP):.2f}"


def _positive_quantity(value: Any) -> bool:
    try:
        return Decimal(str(value).replace(",", ".")) > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _response_rows(response: Any) -> list[dict[str, Any]]:
    payload = response.json() if hasattr(response, "json") else response
    if isinstance(payload, Mapping):
        return [dict(payload)]
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    return []


class _ReadOnlyQuery:
    """Allow only PostgREST read-chain methods on a wrapped query object."""

    def __init__(self, query: Any) -> None:
        self._query = query

    def __getattr__(self, name: str) -> Any:
        if name in _MUTATION_METHODS:
            raise ReadOnlyAccessError(f"Read-only reconciliation forbids Supabase.{name}().")
        attribute = getattr(self._query, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            result = attribute(*args, **kwargs)
            if name == "execute":
                return result
            return self if result is self._query else _ReadOnlyQuery(result)

        return invoke


class ReadOnlySupabaseClient:
    """Small guard that makes accidental replica writes impossible in this path."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def table(self, table_name: str) -> _ReadOnlyQuery:
        return _ReadOnlyQuery(self._client.table(table_name))

    def __getattr__(self, name: str) -> Any:
        if name in _MUTATION_METHODS:
            raise ReadOnlyAccessError(f"Read-only reconciliation forbids Supabase.{name}().")
        return getattr(self._client, name)


@dataclass(frozen=True)
class ReadOnlySession:
    """Session shape accepted by the existing read-only catalog helpers."""

    client: ReadOnlySupabaseClient


def make_read_only_session(session_or_client: Any | None) -> ReadOnlySession | None:
    if session_or_client is None:
        return None
    client = getattr(session_or_client, "client", session_or_client)
    return ReadOnlySession(client=ReadOnlySupabaseClient(client))


def _replica_exact_candidates(session: ReadOnlySession | None, sku: str) -> list[dict[str, Any]]:
    if session is None:
        return []
    candidates: list[dict[str, Any]] = []
    for table, kind in (("products", "product"), ("product_variations", "variation")):
        try:
            response = (
                session.client.table(table)
                .select("woo_id,parent_woo_id,sku,status,name,type")
                .eq("sku", sku)
                .limit(4)
                .execute()
            )
        except Exception:
            continue
        for raw in getattr(response, "data", None) or []:
            row = dict(raw)
            if _text(row.get("sku")) != sku:
                continue
            try:
                woo_id = _positive_int(row.get("woo_id"), "woo_id")
                parent_id = _text(row.get("parent_woo_id"))
                if kind == "variation":
                    parent_id = str(_positive_int(parent_id, "parent_woo_id"))
            except ValueError:
                continue
            candidates.append({
                "woo_id": woo_id,
                "woo_parent_id": parent_id,
                "woo_item_kind": kind,
                "woo_sku": sku,
                "name": _text(row.get("name")),
                "replica_status": _text(row.get("status")),
                "resolution_source": "SUPABASE_EXACT_REPLICA",
            })
    return candidates


def _woo_product_exact_candidates(woo_client: Any, sku: str) -> list[dict[str, Any]]:
    response = woo_client.get("products", params={"sku": sku, "per_page": 100, "status": "any"})
    return [
        dict(row)
        for row in _response_rows(response)
        if _text(row.get("sku")) == sku and _text(row.get("id"))
    ]


def _read_woo_entity(woo_client: Any, candidate: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    kind = _text(candidate.get("woo_item_kind"))
    woo_id = _positive_int(candidate.get("woo_id"), "woo_id")
    parent_id = _text(candidate.get("woo_parent_id"))
    if kind == "product":
        endpoint = f"products/{woo_id}"
    elif kind == "variation":
        endpoint = f"products/{_positive_int(parent_id, 'parent_woo_id')}/variations/{woo_id}"
    else:
        raise ValueError("Woo target kind must be product or variation.")
    rows = _response_rows(woo_client.get(endpoint))
    if len(rows) != 1:
        raise ValueError("Woo did not return exactly one target object.")
    entity = dict(rows[0])
    if _positive_int(entity.get("id"), "Woo id") != woo_id:
        raise ValueError("Woo returned an object with a different id.")
    if kind == "variation":
        live_parent = _positive_int(entity.get("parent_id"), "Woo parent_id")
        if live_parent != _positive_int(parent_id, "parent_woo_id"):
            raise ValueError("Woo returned a variation with a different parent_id.")
    if _text(entity.get("sku")) != _text(candidate.get("woo_sku")):
        raise ValueError("Woo returned a different literal SKU.")
    return entity, endpoint


def resolve_live_direct_identity(
    physical_item_id: Any,
    physical_sku: Any,
    *,
    session: ReadOnlySession | None,
    woo_client: Any,
) -> dict[str, Any]:
    """Resolve a physical item to one validated Woo product or variation.

    Supabase is only an exact-SKU discovery aid. The live Woo object is always
    fetched and checked before an identity becomes usable for a price preview.
    There is deliberately no fallback to an inventory price or a local fake id.
    """
    item_id = _text(physical_item_id)
    sku = _text(physical_sku)
    base = {
        "physical_item_id": item_id,
        "physical_sku": sku,
        "woo_id": None,
        "woo_parent_id": None,
        "woo_item_kind": "",
        "woo_sku": "",
        "woo_name": "",
        "woo_status": "",
        "woo_endpoint": "",
        "resolution_source": "",
    }
    if not item_id or not sku:
        return {**base, "resolution_status": "NOT_FOUND", "reason": "Falta item_id o SKU fisico exacto."}

    replica = _replica_exact_candidates(session, sku)
    product_candidates: list[dict[str, Any]] = []
    lookup_error = ""
    try:
        product_candidates = [
            {
                "woo_id": _positive_int(row.get("id"), "Woo id"),
                "woo_parent_id": "",
                "woo_item_kind": "product",
                "woo_sku": sku,
                "name": _text(row.get("name")),
                "replica_status": "",
                "resolution_source": "WOO_EXACT_SKU",
            }
            for row in _woo_product_exact_candidates(woo_client, sku)
        ]
    except Exception as exc:
        lookup_error = str(exc)

    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for candidate in [*replica, *product_candidates]:
        key = (
            _text(candidate.get("woo_item_kind")),
            int(candidate["woo_id"]),
            _text(candidate.get("woo_parent_id")),
        )
        existing = unique.get(key)
        if existing is None or candidate.get("resolution_source") == "WOO_EXACT_SKU":
            unique[key] = candidate
    if len(unique) != 1:
        if not unique:
            status = "LOOKUP_ERROR" if lookup_error else "NOT_FOUND"
            reason = lookup_error or f"No hay destino Woo exacto para SKU {sku}."
        else:
            status = "AMBIGUOUS"
            reason = f"SKU Woo exacto {sku} tiene {len(unique)} destinos posibles."
        return {**base, "resolution_status": status, "reason": reason}

    candidate = next(iter(unique.values()))
    try:
        entity, endpoint = _read_woo_entity(woo_client, candidate)
    except Exception as exc:
        return {
            **base,
            **candidate,
            "resolution_status": "LOOKUP_ERROR",
            "reason": str(exc),
        }
    return {
        **base,
        **candidate,
        "woo_id": int(candidate["woo_id"]),
        "woo_parent_id": _text(candidate.get("woo_parent_id")) or None,
        "woo_sku": _text(entity.get("sku")),
        "woo_name": _text(entity.get("name")),
        "woo_status": _text(entity.get("status")),
        "woo_endpoint": endpoint,
        "entity": entity,
        "resolution_status": "RESOLVED",
        "reason": "",
    }


def live_price_trace(
    physical_item_id: Any,
    physical_sku: Any,
    *,
    displayed_price: Any = None,
    supabase_cached_price: Any = None,
    session: ReadOnlySession | None,
    woo_client: Any,
) -> dict[str, Any]:
    """Return the exact live source trace used by a direct proposal row."""
    resolution = resolve_live_direct_identity(
        physical_item_id,
        physical_sku,
        session=session,
        woo_client=woo_client,
    )
    trace = {
        "physical_item_id": _text(physical_item_id),
        "physical_sku": _text(physical_sku),
        "read_at": datetime.now(timezone.utc).isoformat(),
        "displayed_price": displayed_price,
        "displayed_price_source": "",
        "resolved_woo_id": resolution.get("woo_id"),
        "resolved_parent_woo_id": resolution.get("woo_parent_id"),
        "resolved_item_kind": resolution.get("woo_item_kind"),
        "woo_endpoint": resolution.get("woo_endpoint"),
        "woo_regular_price": "",
        "woo_sale_price": "",
        "woo_effective_price": "",
        "supabase_cached_price": supabase_cached_price,
        "final_old_price": None,
        "resolution_status": resolution.get("resolution_status"),
        "resolution_source": resolution.get("resolution_source"),
        "reason": resolution.get("reason") or "",
    }
    if resolution.get("resolution_status") != "RESOLVED":
        trace["status"] = f"BLOCKED_DIRECT_WOO_{resolution.get('resolution_status')}"
        return {**trace, "resolution": resolution}

    entity = dict(resolution.get("entity") or {})
    if _text(entity.get("status")).lower() == "private":
        trace.update({
            "status": "PRIVATE_WOO_ENTITY",
            "reason": "La entidad Woo private conserva trazabilidad, pero no admite cambios de precio.",
        })
        return {**trace, "resolution": resolution}
    trace.update({
        "woo_regular_price": _text(entity.get("regular_price")),
        "woo_sale_price": _text(entity.get("sale_price")),
        "displayed_price_source": "WOO_LIVE",
    })
    try:
        effective = _effective_woo_price(entity)
        if effective is None:
            raise ValueError("Woo did not return an effective price.")
        final_old = _money(effective)
    except Exception as exc:
        trace.update({
            "status": "BLOCKED_LIVE_PRICE_UNAVAILABLE",
            "reason": str(exc),
        })
        return {**trace, "resolution": resolution}
    trace.update({
        "displayed_price": float(final_old),
        "woo_effective_price": _money_text(final_old),
        "final_old_price": float(final_old),
        "status": "READY",
    })
    return {**trace, "resolution": resolution}


def _fetch_inventory_names(
    session: ReadOnlySession | None,
    item_ids: Iterable[Any],
) -> dict[str, dict[str, Any]]:
    if session is None:
        return {}
    ids = sorted({_text(value) for value in item_ids if _text(value)})
    if not ids:
        return {}
    rows: list[dict[str, Any]] = []
    try:
        response = (
            session.client.table("inventory_items")
            .select("item_id,heca_reference,hub_item_code,name,item_record_type,is_pack,woo_id,woo_sku,woo_price")
            .in_("item_id", [int(value) for value in ids if value.isdigit()])
            .limit(len(ids))
            .execute()
        )
        rows = [dict(row) for row in getattr(response, "data", None) or []]
    except Exception:
        rows = []
    return {_text(row.get("item_id")): row for row in rows if _text(row.get("item_id"))}


def _decorate_component_names(
    components: Iterable[Mapping[str, Any]],
    inventory_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for raw in components:
        component = dict(raw)
        item_id = _text(component.get("component_item_id"))
        inventory = dict(inventory_by_id.get(item_id) or {})
        component_name = _text(inventory.get("name"))
        component.update({
            "component_item_id": item_id,
            "component_sku": _text(component.get("component_sku")),
            "component_name": component_name or "Nombre no disponible",
            "component_name_status": "RESOLVED" if component_name else "UNRESOLVED",
            "quantity": _text(component.get("quantity")),
            "is_modified": "YES",
        })
        decorated.append(component)
    return decorated


def _reconciliation_status(
    row: Mapping[str, Any],
    entity: Mapping[str, Any] | None,
    endpoint_error: str,
    *,
    duplicate: bool,
) -> tuple[str, str]:
    if str(row.get("excluded") or "").upper() == "YES":
        return "QUARANTINED", _text(row.get("exclusion_reason")) or "Destino excluido por cuarentena."
    if duplicate:
        return "DUPLICATE", "La misma variacion Woo aparece mas de una vez en el resultado combinado."
    if not _text(row.get("combination_woo_id")) or not _text(row.get("combination_parent_woo_id")):
        return "INVALID_COMPONENT_EDGE", "Falta identidad exacta de variacion o producto padre en el grafo."
    if not list(row.get("modified_components") or []):
        return "INVALID_COMPONENT_EDGE", "El destino no conserva componentes modificados exactos."
    if any(not _positive_quantity(component.get("quantity")) for component in row.get("modified_components") or []):
        return "INVALID_COMPONENT_EDGE", "El grafo contiene una cantidad de componente vacia o no positiva."
    if entity is None:
        if endpoint_error.startswith("WOO_NOT_FOUND"):
            return "WOO_NOT_FOUND", endpoint_error
        return "READ_ERROR", endpoint_error or "No se pudo leer la variacion Woo exacta."
    if _text(entity.get("sku")) != _text(row.get("combination_sku")):
        return "SKU_MISMATCH", "El SKU live de Woo no coincide con el SKU literal del grafo."
    try:
        if _positive_int(entity.get("parent_id"), "Woo parent_id") != _positive_int(row.get("combination_parent_woo_id"), "graph parent id"):
            return "PARENT_MISMATCH", "El parent_id live de Woo no coincide con el parent_id del grafo."
    except ValueError:
        return "PARENT_MISMATCH", "Woo no devolvio un parent_id valido para la variacion."
    if _text(entity.get("status")).lower() not in _PUBLISHED_STATUSES:
        return "NOT_PUBLISHED", f"Estado Woo no publicable: {_text(entity.get('status')) or 'vacio'}."
    if _effective_woo_price(dict(entity)) is None:
        return "PRICE_MISSING", "Woo no devolvio un precio efectivo para la variacion."
    return "VALID", "Validacion live exacta completada."


def reconcile_live_combination_plan(
    changes: Iterable[Mapping[str, Any]],
    *,
    impact_service: CombinationPriceImpactService,
    woo_client: Any,
    session: ReadOnlySession | None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Reconcile graph candidates against current Woo data without mutations."""
    change_rows = [dict(change) for change in changes]
    try:
        impact = impact_service.impact_for_changes(change_rows)
    except CombinationPriceImpactError as exc:
        return {
            "derived_lines": [],
            "blocked_lines": [{"validation_status": "INVALID_COMPONENT_EDGE", "reason": str(exc)}],
            "excluded_lines": [],
            "all_lines": [],
            "counts": {"candidates": 0, "valid": 0, "blocked": 1, "excluded": 0, "errors": 1},
        }

    all_candidates = [
        *[dict(row) for row in impact.get("included_combinations") or []],
        *[dict(row) for row in impact.get("excluded_combinations") or []],
    ]
    inventory_by_id = _fetch_inventory_names(
        session,
        (
            component.get("component_item_id")
            for candidate in all_candidates
            for component in candidate.get("modified_components") or []
        ),
    )
    destination_counts: dict[str, int] = {}
    for candidate in all_candidates:
        destination = _text(candidate.get("combination_woo_id"))
        destination_counts[destination] = destination_counts.get(destination, 0) + 1

    all_lines: list[dict[str, Any]] = []
    total_candidates = len(all_candidates)
    for position, candidate in enumerate(all_candidates, start=1):
        row = dict(candidate)
        if progress_callback is not None:
            progress_callback({
                "phase": "READING_COMBINATIONS_WOO",
                "processed": position - 1,
                "total": total_candidates,
                "combination_woo_id": _text(row.get("combination_woo_id")),
                "combination_sku": _text(row.get("combination_sku")),
            })
        row["modified_components"] = _decorate_component_names(
            row.get("modified_components") or [], inventory_by_id
        )
        endpoint = ""
        entity: dict[str, Any] | None = None
        endpoint_error = ""
        if str(row.get("excluded") or "").upper() != "YES":
            try:
                woo_id = _positive_int(row.get("combination_woo_id"), "combination_woo_id")
                parent_id = _positive_int(row.get("combination_parent_woo_id"), "combination_parent_woo_id")
                endpoint = f"products/{parent_id}/variations/{woo_id}"
                rows = _response_rows(woo_client.get(endpoint))
                if len(rows) != 1:
                    endpoint_error = "WOO_NOT_FOUND: Woo no devolvio una variation unica."
                else:
                    entity = dict(rows[0])
                    if _positive_int(entity.get("id"), "Woo variation id") != woo_id:
                        endpoint_error = "WOO_NOT_FOUND: Woo devolvio un id distinto."
                        entity = None
            except Exception as exc:
                endpoint_error = f"READ_ERROR: {exc}"
        status, reason = _reconciliation_status(
            row,
            entity,
            endpoint_error,
            duplicate=destination_counts.get(_text(row.get("combination_woo_id")), 0) > 1,
        )
        effective: Decimal | None = None
        if entity is not None:
            try:
                raw_effective = _effective_woo_price(entity)
                effective = _money(raw_effective) if raw_effective is not None else None
            except Exception:
                effective = None
        delta = None
        simulated = None
        try:
            delta = _money(row.get("component_delta"))
            if effective is not None:
                simulated = (effective + delta).quantize(_CENT, rounding=ROUND_HALF_UP)
                if simulated <= 0:
                    status = "PRICE_MISSING"
                    reason = "El nuevo precio derivado no seria positivo."
        except Exception:
            if status == "VALID":
                status = "READ_ERROR"
                reason = "No se pudo calcular el delta derivado exacto."
        row.update({
            "woo_endpoint": endpoint,
            "woo_status": _text((entity or {}).get("status")),
            "combination_sku_woo": _text((entity or {}).get("sku")),
            "regular_price": _text((entity or {}).get("regular_price")),
            "sale_price": _text((entity or {}).get("sale_price")),
            "effective_price": _money_text(effective),
            "effective_current_price": _money_text(effective),
            "simulated_effective_price": _money_text(simulated),
            "validation_status": status,
            "included_in_proposal": "YES" if status == "VALID" else "NO",
            "reason": reason,
            "status": "READY" if status == "VALID" else f"BLOCKED_{status}",
            "publication_allowed": "YES" if status == "VALID" else "NO",
            "blocking_reason": "" if status == "VALID" else reason,
            "impact_display_status": "VALID" if status == "VALID" else f"BLOCKED_{status}",
            "woo_price_context": {
                "id": (entity or {}).get("id"),
                "parent_id": (entity or {}).get("parent_id"),
                "regular_price": (entity or {}).get("regular_price"),
                "sale_price": (entity or {}).get("sale_price"),
                "price": (entity or {}).get("price"),
                "on_sale": (entity or {}).get("on_sale"),
                "date_on_sale_from": (entity or {}).get("date_on_sale_from"),
                "date_on_sale_to": (entity or {}).get("date_on_sale_to"),
                "date_modified": (entity or {}).get("date_modified"),
                "date_modified_gmt": (entity or {}).get("date_modified_gmt"),
                "status": (entity or {}).get("status"),
                "attributes": list((entity or {}).get("attributes") or []),
                "price_source": "WOO_LIVE" if entity is not None else "",
                "price_read_at": datetime.now(timezone.utc).isoformat() if entity is not None else "",
                "woo_date_modified": (entity or {}).get("date_modified_gmt") or (entity or {}).get("date_modified"),
            },
        })
        all_lines.append(row)
        if progress_callback is not None:
            progress_callback({
                "phase": "COMBINATION_READ_COMPLETE",
                "processed": position,
                "total": total_candidates,
                "combination_woo_id": _text(row.get("combination_woo_id")),
                "combination_sku": _text(row.get("combination_sku")),
            })

    valid = [row for row in all_lines if row.get("validation_status") == "VALID"]
    excluded = [row for row in all_lines if row.get("validation_status") == "QUARANTINED"]
    blocked = [row for row in all_lines if row.get("validation_status") not in {"VALID", "QUARANTINED"}]
    return {
        "derived_lines": valid,
        "blocked_lines": blocked,
        "excluded_lines": excluded,
        "all_lines": all_lines,
        "unmatched_changes": list(impact.get("unmatched_changes") or []),
        "counts": {
            # Quarantine evidence is retained for traceability but is never an
            # operational candidate nor part of the Apply count.
            "candidates": len(valid) + len(blocked),
            "valid": len(valid),
            "blocked": len(blocked),
            "excluded": len(excluded),
            "errors": sum(row.get("validation_status") == "READ_ERROR" for row in all_lines),
            "price_missing": sum(row.get("validation_status") == "PRICE_MISSING" for row in all_lines),
            "not_found": sum(row.get("validation_status") == "WOO_NOT_FOUND" for row in all_lines),
            "not_published": sum(row.get("validation_status") == "NOT_PUBLISHED" for row in all_lines),
            "duplicates": sum(row.get("validation_status") == "DUPLICATE" for row in all_lines),
            "quarantined": len(excluded),
        },
    }

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable, Mapping

from futonhub.cloud.audit import CloudAuditError
from futonhub.cloud.services.woocommerce_publish import _effective_woo_price
from futonhub.services.combination_price_impact import CombinationPriceImpactError, CombinationPriceImpactService
from futonhub.services.combination_proposal_integration import build_combination_proposal_plan
from futonhub.services.price_combination_live_reconciliation import (
    live_price_trace,
    make_read_only_session,
    reconcile_live_combination_plan,
)


_CENT = Decimal("0.01")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _positive_int(value: Any, field: str) -> int:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise CloudAuditError(f"{field} debe ser un entero positivo.") from exc
    if result <= 0:
        raise CloudAuditError(f"{field} debe ser un entero positivo.")
    return result


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", ".")).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CloudAuditError("Woo no devolvio un precio efectivo numerico.") from exc


def _physical_identity(source: Mapping[str, Any], code: str) -> dict[str, str]:
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), dict) else {}
    physical_item_id = _text(source.get("physical_item_id") or source.get("item_id") or snapshot.get("physical_item_id") or snapshot.get("item_id"))
    physical_sku = _text(source.get("physical_sku") or source.get("hub_item_code") or snapshot.get("hub_item_code") or snapshot.get("heca_reference") or code)
    if not physical_item_id or not physical_sku:
        raise CloudAuditError("Falta la identidad fisica exacta item_id/SKU para resolver el destino Woo directo.")
    return {
        "physical_item_id": physical_item_id,
        "physical_sku": physical_sku,
    }


def _source_identities(source: Mapping[str, Any], code: str) -> dict[str, Any]:
    """Compatibility helper for callers that already have a verified exact link."""
    physical = _physical_identity(source, code)
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), dict) else {}
    woo_id = _positive_int(source.get("woo_id") or snapshot.get("woo_id"), "woo_id")
    woo_item_kind = _text(source.get("woo_item_kind") or source.get("item_kind") or snapshot.get("woo_item_kind")).lower()
    if woo_item_kind not in {"product", "variation"}:
        raise CloudAuditError("woo_item_kind debe ser product o variation para leer precio Woo.")
    woo_parent_id = _text(source.get("woo_parent_id") or source.get("parent_woo_id") or snapshot.get("woo_parent_id") or snapshot.get("parent_woo_id"))
    if woo_item_kind == "variation":
        woo_parent_id = str(_positive_int(woo_parent_id, "woo_parent_id"))
    return {
        **physical,
        "woo_id": woo_id,
        "woo_parent_id": woo_parent_id,
        "woo_item_kind": woo_item_kind,
        "woo_sku": _text(source.get("woo_sku") or snapshot.get("woo_sku") or snapshot.get("sku")),
    }


def _response_rows(response: Any) -> list[dict[str, Any]]:
    payload = response.json() if hasattr(response, "json") else response
    if isinstance(payload, dict):
        return [dict(payload)]
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    return []


def _replica_exact_candidates(session: Any, physical_sku: str) -> list[dict[str, Any]]:
    """Read only exact SKU candidates; never infer from a partial identifier."""
    if session is None:
        return []
    candidates: list[dict[str, Any]] = []
    for table, kind in (("products", "product"), ("product_variations", "variation")):
        try:
            response = (
                session.client.table(table)
                .select("woo_id,parent_woo_id,sku,status,name,type")
                .eq("sku", physical_sku)
                .limit(3)
                .execute()
            )
        except Exception:
            continue
        for raw in getattr(response, "data", None) or []:
            row = dict(raw)
            if _text(row.get("sku")) != physical_sku:
                continue
            try:
                woo_id = _positive_int(row.get("woo_id"), "woo_id")
                parent_id = _text(row.get("parent_woo_id"))
                if kind == "variation":
                    parent_id = str(_positive_int(parent_id, "parent_woo_id"))
            except CloudAuditError:
                continue
            candidates.append({
                "woo_id": woo_id,
                "woo_parent_id": parent_id,
                "woo_item_kind": kind,
                "woo_sku": physical_sku,
                "resolution_source": "SUPABASE_EXACT_REPLICA",
            })
    return candidates


def resolve_direct_woo_target(
    physical_item_id: Any,
    physical_sku: Any,
    *,
    source: Mapping[str, Any] | None = None,
    session: Any | None = None,
    woo_client: Any | None = None,
) -> dict[str, Any]:
    """Resolve exactly one direct Woo target for a physical catalog item.

    Resolution is deliberately literal and ordered: an exact local graph link,
    then an exact Supabase replica row, then an exact Woo SKU query. Any absent
    or non-unique result stays blocked instead of falling back to a cached price.
    """
    item_id = _text(physical_item_id)
    sku = _text(physical_sku)
    if not item_id or not sku:
        return {"resolution_status": "NOT_FOUND", "reason": "Falta item_id o SKU fisico exacto."}
    source = dict(source or {})
    snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), dict) else {}
    try:
        local_kind = _text(source.get("woo_item_kind") or source.get("item_kind") or snapshot.get("woo_item_kind")).lower()
        local_sku = _text(source.get("woo_sku") or snapshot.get("woo_sku") or snapshot.get("sku"))
        local_id = source.get("woo_id") or snapshot.get("woo_id")
        if local_kind in {"product", "variation"} and local_sku == sku and local_id not in (None, ""):
            resolved = _source_identities(source, sku)
            return {"resolution_status": "RESOLVED", "resolution_source": "LOCAL_GRAPH_EXACT", **resolved}
    except CloudAuditError:
        pass

    replica = _replica_exact_candidates(session, sku)
    unique_replica = {
        (row["woo_item_kind"], int(row["woo_id"]), _text(row.get("woo_parent_id"))): row
        for row in replica
    }
    if len(unique_replica) == 1:
        return {"resolution_status": "RESOLVED", "physical_item_id": item_id, "physical_sku": sku, **next(iter(unique_replica.values()))}
    if len(unique_replica) > 1:
        return {"resolution_status": "AMBIGUOUS", "reason": f"SKU Woo exacto {sku} tiene {len(unique_replica)} destinos en la replica."}

    if woo_client is None:
        return {"resolution_status": "NOT_FOUND", "reason": f"No existe un destino Woo exacto para SKU {sku}."}
    try:
        candidates = [
            row for row in _response_rows(woo_client.get("products", params={"sku": sku, "per_page": 100}))
            if _text(row.get("sku")) == sku and _positive_int(row.get("id"), "Woo id") > 0
        ]
    except Exception as exc:
        return {"resolution_status": "LOOKUP_ERROR", "reason": f"No se pudo consultar Woo por SKU exacto {sku}: {exc}"}
    unique_woo = {int(row["id"]): row for row in candidates}
    if len(unique_woo) != 1:
        status = "NOT_FOUND" if not unique_woo else "AMBIGUOUS"
        return {"resolution_status": status, "reason": f"SKU Woo exacto {sku} devolvio {len(unique_woo)} productos."}
    woo_row = next(iter(unique_woo.values()))
    return {
        "resolution_status": "RESOLVED",
        "resolution_source": "WOO_EXACT_SKU",
        "physical_item_id": item_id,
        "physical_sku": sku,
        "woo_id": int(woo_row["id"]),
        "woo_parent_id": "",
        "woo_item_kind": "product",
        "woo_sku": sku,
    }


def _read_woo_target(woo_client: Any, identities: Mapping[str, Any], cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    kind = identities["woo_item_kind"]
    woo_id = int(identities["woo_id"])
    cache_key = f"{kind}:{woo_id}"
    if cache_key in cache:
        item = dict(cache[cache_key])
    else:
        endpoint = f"products/{woo_id}" if kind == "product" else f"products/{identities['woo_parent_id']}/variations/{woo_id}"
        response = woo_client.get(endpoint)
        item = response.json() if hasattr(response, "json") else response
        if not isinstance(item, dict):
            raise CloudAuditError("WooCommerce no devolvio un objeto de precio.")
        item = dict(item)
        cache[cache_key] = dict(item)
    if _positive_int(item.get("id"), "Woo id") != woo_id:
        raise CloudAuditError("Woo devolvio un item distinto del woo_id exacto solicitado.")
    reported_parent = item.get("parent_id")
    if kind == "variation" and reported_parent not in (None, ""):
        if _positive_int(reported_parent, "Woo parent_id") != int(identities["woo_parent_id"]):
            raise CloudAuditError("Woo devolvio una variation con parent_id distinto.")
    if identities["woo_sku"] and _text(item.get("sku")) != identities["woo_sku"]:
        raise CloudAuditError("Woo devolvio un SKU distinto del SKU exacto esperado.")
    return item


def _live_context(item: Mapping[str, Any], identities: Mapping[str, Any]) -> dict[str, Any]:
    effective = _effective_woo_price(dict(item))
    if effective is None:
        raise CloudAuditError("Woo no devolvio un precio efectivo calculable.")
    return {
        "effective_price": f"{_money(effective):.2f}",
        "regular_price": item.get("regular_price"),
        "sale_price": item.get("sale_price"),
        "price": item.get("price"),
        "date_on_sale_from": item.get("date_on_sale_from"),
        "date_on_sale_to": item.get("date_on_sale_to"),
        "status": item.get("status"),
        "stock_status": item.get("stock_status"),
        "manage_stock": item.get("manage_stock"),
        "stock_quantity": item.get("stock_quantity"),
        "attributes": list(item.get("attributes") or []),
        "woo_date_modified": item.get("date_modified_gmt") or item.get("date_modified"),
        "woo_id": identities["woo_id"],
        "woo_parent_id": identities["woo_parent_id"],
        "woo_item_kind": identities["woo_item_kind"],
        "woo_sku": _text(item.get("sku")),
        "price_source": "WOO_LIVE",
        "price_stale": "NO",
        "price_read_at": datetime.now(timezone.utc).isoformat(),
    }


def _impact_for_changes(
    impact_service: CombinationPriceImpactService,
    changes: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        return dict(impact_service.impact_for_changes(changes))
    except CombinationPriceImpactError as exc:
        return {
            "included_combinations": [],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "error": str(exc),
        }


def _graph_coverage_for_changes(
    impact_service: CombinationPriceImpactService,
    changes: Iterable[Mapping[str, Any]],
    impact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Check exact graph expectations before treating a zero as harmless."""
    resolver = getattr(impact_service, "affected_destinations_for_identity", None)
    if not callable(resolver):
        return []
    included = list(impact.get("included_combinations") or [])
    coverage: list[dict[str, Any]] = []
    for change in changes:
        physical_item_id = _text(change.get("physical_item_id"))
        physical_sku = _text(change.get("physical_sku"))
        expectation = dict(resolver({"physical_item_id": physical_item_id, "physical_sku": physical_sku}))
        expected_ids = {
            _text(row.get("combination_woo_id"))
            for row in expectation.get("destinations") or []
            if _text(row.get("combination_woo_id"))
        }
        returned_ids = {
            _text(row.get("combination_woo_id"))
            for row in included
            if validate_incremental_destination(row, physical_item_id, physical_sku)
        }
        expected_count = int(expectation.get("expected_count") or 0)
        status = _text(expectation.get("status"))
        if status == "NO_COMBINATIONS_BY_DESIGN":
            outcome = "NO_COMBINATIONS_BY_DESIGN"
            blocking_reason = "No participa en combinaciones Woo. Solo se modificara el articulo directo."
        elif status != "HAS_AFFECTED" or returned_ids != expected_ids or len(returned_ids) != expected_count:
            outcome = "BLOCKED_GRAPH_COVERAGE"
            blocking_reason = (
                "No se pudieron recuperar las combinaciones esperadas "
                f"para item_id={physical_item_id}, SKU={physical_sku}, esperadas={expected_count}."
            )
        else:
            outcome = "HAS_AFFECTED"
            blocking_reason = ""
        coverage.append({
            "physical_item_id": physical_item_id,
            "physical_sku": physical_sku,
            "expected_count": expected_count,
            "returned_count": len(returned_ids),
            "resolution_status": _text(expectation.get("resolution_status")),
            "status": outcome,
            "blocking_reason": blocking_reason,
        })
    return coverage


def _existing_direct_changes(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize pre-existing direct intent for incremental popup calculations."""
    result: list[dict[str, Any]] = []
    for raw in entries:
        row = dict(raw)
        physical_item_id = _text(row.get("physical_item_id"))
        physical_sku = _text(row.get("physical_sku"))
        if not physical_item_id or not physical_sku:
            raise CloudAuditError(
                "Una linea existente no conserva physical_item_id y physical_sku exactos; "
                "no se puede calcular impacto acumulado."
            )
        result.append({
            "physical_item_id": physical_item_id,
            "physical_sku": physical_sku,
            "old_price": _money(row.get("old_price")),
            "new_price": _money(row.get("new_price")),
            "proposal_key": _text(row.get("proposal_key") or physical_sku),
        })
    return result


def _impact_by_destination(impact: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("combination_woo_id")): row
        for row in impact.get("included_combinations") or []
        if row.get("combination_woo_id") not in (None, "")
    }


def _component_delta(row: Mapping[str, Any] | None) -> Decimal:
    return _money((row or {}).get("component_delta") or "0")


def validate_incremental_destination(
    destination: Mapping[str, Any],
    physical_item_id: Any,
    physical_sku: Any,
) -> bool:
    """Return whether a destination contains the literal newly added component.

    Both the physical item id and SKU must agree. This prevents an accumulated
    destination that belongs only to a previous proposal row from leaking into
    the popup for the newly selected item.
    """
    item_id = _text(physical_item_id)
    sku = _text(physical_sku)
    return any(
        _text(component.get("component_item_id")) == item_id
        and _text(component.get("component_sku")) == sku
        for component in destination.get("modified_components") or []
    )


def _decorate_plan_lines(
    lines: Iterable[dict[str, Any]],
    *,
    incremental_by_destination: Mapping[str, Mapping[str, Any]],
    prior_by_destination: Mapping[str, Mapping[str, Any]],
    combined_by_destination: Mapping[str, Mapping[str, Any]],
    sync_by_woo_id: Mapping[str, Mapping[str, Any]],
) -> None:
    for line in lines:
        destination = str(line.get("combination_woo_id"))
        incremental_delta = _component_delta(incremental_by_destination.get(destination))
        previous_delta = _component_delta(prior_by_destination.get(destination))
        combined = combined_by_destination.get(destination)
        accumulated_delta = _component_delta(combined or line)
        line["incremental_component_delta"] = f"{incremental_delta:+.2f}"
        line["previous_accumulated_delta"] = f"{previous_delta:+.2f}"
        line["new_accumulated_delta"] = f"{accumulated_delta:+.2f}"
        if combined:
            line["combined_effective_current_price"] = combined.get("effective_current_price")
            line["combined_simulated_effective_price"] = combined.get("simulated_effective_price")
        if not str(line.get("status") or "").startswith("BLOCKED"):
            if previous_delta and incremental_delta:
                line["impact_display_status"] = "UPDATED_ACCUMULATED_IMPACT"
            elif previous_delta:
                line["impact_display_status"] = "ALREADY_AFFECTED"
            else:
                line["impact_display_status"] = str(line.get("status") or "READY")
        sync_result = sync_by_woo_id.get(destination)
        if sync_result is None:
            continue
        line["sync_action"] = sync_result.get("sync_action")
        line["supabase_replica_status"] = sync_result.get("supabase_replica_status")
        if sync_result.get("proposal_line_status") == "BLOCKED_SYNC_ERROR":
            line["status"] = "BLOCKED_SYNC_ERROR"
            line["impact_display_status"] = "BLOCKED_SYNC_ERROR"
            line["publication_allowed"] = "NO"
            line["blocking_reason"] = sync_result.get("reason") or "No se pudo sincronizar la variation Woo."


def project_persisted_derived_rows(
    entries: Iterable[Mapping[str, Any]],
    *,
    impact_service: CombinationPriceImpactService,
) -> dict[str, Any]:
    """Rebuild the visible derived block from confirmed direct proposal intent.

    This is a read-only projection. It deliberately uses the Woo context that
    was captured when a direct item was confirmed, preserving the exact direct
    values through draft reopen and editor refresh.
    """
    changes: list[dict[str, Any]] = []
    persisted_by_destination: dict[str, dict[str, Any]] = {}
    for entry in entries:
        source = dict(entry.get("source") or {})
        if str(source.get("entry_origin") or "DIRECT_ITEM").upper() == "DERIVED_COMBINATION":
            continue
        line = entry.get("line")
        if line is None:
            continue
        snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), dict) else {}
        physical_item_id = _text(source.get("physical_item_id") or source.get("item_id") or snapshot.get("physical_item_id") or snapshot.get("item_id"))
        physical_sku = _text(source.get("physical_sku") or source.get("hub_item_code") or snapshot.get("physical_sku") or snapshot.get("hub_item_code"))
        if not physical_item_id or not physical_sku:
            continue
        changes.append({
            "physical_item_id": physical_item_id,
            "physical_sku": physical_sku,
            "old_price": _money(getattr(line, "old_price", "")),
            "new_price": _money(getattr(line, "new_price", "")),
            "proposal_key": _text(entry.get("key") or physical_sku),
        })
        addition_plan = source.get("combination_addition_plan")
        if not isinstance(addition_plan, Mapping):
            continue
        # A saved draft is first rendered from its validated read snapshot. It
        # must never be rebuilt solely from the local graph because that loses
        # live validation states, component names and quarantine reasons.
        for derived in addition_plan.get("all_lines") or []:
            if not isinstance(derived, Mapping):
                continue
            woo_id = _text(derived.get("combination_woo_id"))
            if not woo_id:
                continue
            persisted_by_destination.setdefault(woo_id, dict(derived))
    if persisted_by_destination:
        all_lines = list(persisted_by_destination.values())
        valid = [row for row in all_lines if row.get("validation_status") == "VALID"]
        excluded = [row for row in all_lines if row.get("validation_status") == "QUARANTINED"]
        blocked = [
            row for row in all_lines
            if row.get("validation_status") not in {"VALID", "QUARANTINED"}
        ]
        return {
            "derived_lines": valid,
            "blocked_lines": blocked,
            "excluded_lines": excluded,
            "all_lines": all_lines,
            "counts": {
                "candidates": len(valid) + len(blocked),
                "valid": len(valid),
                "blocked": len(blocked),
                "excluded": len(excluded),
            },
            "read_validation_snapshot": "PERSISTED",
        }
    return build_combination_proposal_plan(
        changes,
        impact_service=impact_service,
        woo_client=None,
        woo_context_by_id={},
    )


def project_grouped_combination_rows(
    entries: Iterable[Mapping[str, Any]],
    projection: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project the confirmed popup hierarchy over a deduplicated plan.

    Each direct entry keeps its own popup plan and therefore retains the exact
    order reviewed by the user. The operational projection remains deduplicated
    by Woo destination, so shared combinations have one accumulated delta and
    one future write while appearing below every responsible direct parent.
    """
    direct_entries = [
        dict(entry)
        for entry in entries
        if str((entry.get("source") or {}).get("entry_origin") or "DIRECT_ITEM").upper()
        != "DERIVED_COMBINATION"
    ]
    all_lines = [
        dict(row)
        for row in projection.get("all_lines") or [
            *(projection.get("derived_lines") or []),
            *(projection.get("blocked_lines") or []),
            *(projection.get("excluded_lines") or []),
        ]
        if isinstance(row, Mapping)
    ]
    operational_by_destination = {
        _text(row.get("combination_woo_id")): row
        for row in all_lines
        if _text(row.get("combination_woo_id"))
    }

    def plan_rows(plan: Mapping[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(plan, Mapping):
            return []
        return [
            dict(row)
            for row in plan.get("all_lines") or [
                *(plan.get("derived_lines") or []),
                *(plan.get("blocked_lines") or []),
                *(plan.get("excluded_lines") or []),
            ]
            if isinstance(row, Mapping)
        ]

    def responsible_keys(row: Mapping[str, Any]) -> set[str]:
        components = [
            component for component in row.get("modified_components") or []
            if isinstance(component, Mapping)
        ]
        keys = {
            _text(component.get("proposal_trace_key"))
            for component in components
            if _text(component.get("proposal_trace_key"))
        }
        keys.update(_text(value) for value in row.get("proposal_trace_keys") or [] if _text(value))
        return keys
    physical_sku_by_key: dict[str, str] = {}
    for entry in direct_entries:
        source = dict(entry.get("source") or {})
        snapshot = source.get("item_snapshot") if isinstance(source.get("item_snapshot"), Mapping) else {}
        physical_sku_by_key[_text(entry.get("key"))] = _text(
            source.get("physical_sku")
            or source.get("hub_item_code")
            or snapshot.get("hub_item_code")
            or snapshot.get("heca_reference")
        )

    groups: list[dict[str, Any]] = []
    for entry in direct_entries:
        entry_key = _text(entry.get("key"))
        line = entry.get("line")
        children: list[dict[str, Any]] = []
        source = dict(entry.get("source") or {})
        confirmed_rows = plan_rows(source.get("popup_combination_addition_plan"))
        # Drafts created before 001B.8.4 do not carry the popup plan. They
        # retain the previous deterministic grouping until edited and saved.
        child_rows = confirmed_rows or [
            row for row in all_lines
            if entry_key in responsible_keys(row)
        ]
        seen_destinations: set[str] = set()
        for popup_row in child_rows:
            woo_id = _text(popup_row.get("combination_woo_id"))
            dedupe_key = woo_id or repr(popup_row)
            if dedupe_key in seen_destinations:
                continue
            seen_destinations.add(dedupe_key)
            operational = operational_by_destination.get(woo_id, popup_row)
            components = [
                dict(component)
                for component in popup_row.get("modified_components") or []
                if isinstance(component, Mapping)
            ]
            contribution = Decimal("0.00")
            try:
                direct_delta = _money(getattr(line, "new_price", "")) - _money(getattr(line, "old_price", ""))
                for component in components:
                    if _text(component.get("proposal_trace_key")) != entry_key:
                        continue
                    contribution += direct_delta * Decimal(str(component.get("quantity") or "0").replace(",", "."))
            except (InvalidOperation, ValueError, TypeError):
                contribution = Decimal("0.00")
            operational_keys = responsible_keys(operational)
            if not operational_keys:
                operational_keys = {entry_key}
            related_skus = sorted(
                sku for key, sku in physical_sku_by_key.items()
                if key in operational_keys and sku
            )
            children.append({
                **popup_row,
                "effective_current_price": operational.get("effective_current_price") or popup_row.get("effective_current_price"),
                "simulated_effective_price": operational.get("simulated_effective_price") or popup_row.get("simulated_effective_price"),
                "component_delta": operational.get("component_delta") or popup_row.get("component_delta"),
                "validation_status": operational.get("validation_status") or popup_row.get("validation_status"),
                "impact_display_status": operational.get("impact_display_status") or popup_row.get("impact_display_status"),
                "modified_components": components,
                "parent_entry_key": entry_key,
                "contribution_from_parent_item": f"{contribution.quantize(_CENT, rounding=ROUND_HALF_UP):.2f}",
                "accumulated_combination_delta": _text(operational.get("component_delta") or popup_row.get("component_delta")),
                "shared_with_physical_skus": " | ".join(related_skus),
                "source_component_entry_ids": sorted(operational_keys),
            })
        groups.append({"entry": entry, "children": children})
    return groups


def prepare_price_addition(
    entries: Iterable[Mapping[str, Any]],
    *,
    adjustment_mode: str,
    adjustment_value: Any,
    impact_service: CombinationPriceImpactService,
    woo_client: Any,
    session: Any | None,
    reason: str = "PROPOSAL_ITEM_ADDED",
    replica_write: bool = False,
    live_cache: dict[str, dict[str, Any]] | None = None,
    existing_changes: Iterable[Mapping[str, Any]] = (),
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Prepare an add-to-proposal popup without mutating the proposal model.

    The caller decides whether a confirmed popup later inserts model lines. Woo
    data is live authority. A cache fallback remains visible only as stale and
    blocks apply; it is never labelled as a current Woo price.
    """
    if adjustment_mode not in {"percent", "amount"}:
        raise CloudAuditError("adjustment_mode debe ser percent o amount.")
    value = _money(adjustment_value)
    direct_rows: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    prior_changes = _existing_direct_changes(existing_changes)
    read_only_session = make_read_only_session(session)

    # Generators are accepted by the public API; materialize once so progress
    # never consumes a direct row.
    entry_rows = [dict(raw) for raw in entries]
    total_direct_rows = len(entry_rows)
    for position, row in enumerate(entry_rows, start=1):
        source = dict(row.get("source") or {})
        code = _text(row.get("code"))
        trace: dict[str, Any] = {}
        if progress_callback is not None:
            progress_callback({
                "phase": "RESOLVING_DIRECT_IDENTITY",
                "processed": position - 1,
                "total": total_direct_rows,
                "code": code,
                "name": _text(row.get("name")),
            })
        try:
            physical = _physical_identity(source, code)
            trace = live_price_trace(
                physical["physical_item_id"],
                physical["physical_sku"],
                displayed_price=row.get("cached_price"),
                supabase_cached_price=row.get("cached_price"),
                woo_client=woo_client,
                session=read_only_session,
            )
            resolution = dict(trace.get("resolution") or {})
            if trace.get("status") != "READY":
                raise CloudAuditError(str(trace.get("reason") or "No se pudo leer un precio Woo directo exacto."))
            identities = {
                "physical_item_id": physical["physical_item_id"],
                "physical_sku": physical["physical_sku"],
                "woo_id": resolution.get("woo_id"),
                "woo_parent_id": resolution.get("woo_parent_id") or "",
                "woo_item_kind": resolution.get("woo_item_kind"),
                "woo_sku": resolution.get("woo_sku"),
            }
            live_item = dict(resolution.get("entity") or {})
            context = _live_context(live_item, identities)
            context.update({
                "direct_resolution_source": trace.get("resolution_source"),
                "woo_endpoint": trace.get("woo_endpoint"),
                "direct_price_trace": dict(trace),
            })
            old_price = _money(trace["final_old_price"])
            new_price = (
                (old_price * (Decimal("1") + (value / Decimal("100"))))
                if adjustment_mode == "percent"
                else old_price + value
            ).quantize(_CENT, rounding=ROUND_HALF_UP)
            status = "READY"
            blocking_reason = ""
        except Exception as exc:
            try:
                identities = _physical_identity(source, code)
            except CloudAuditError:
                identities = {
                    "physical_item_id": _text(source.get("physical_item_id") or source.get("item_id")),
                    "physical_sku": _text(source.get("physical_sku") or source.get("hub_item_code") or code),
                }
            resolution = dict(trace.get("resolution") or {})
            identities.update({
                "woo_id": resolution.get("woo_id"),
                "woo_parent_id": resolution.get("woo_parent_id") or "",
                "woo_item_kind": resolution.get("woo_item_kind") or "",
                "woo_sku": resolution.get("woo_sku") or "",
            })
            stored_price = _text(row.get("cached_price") or row.get("price"))
            old_price = None
            new_price = None
            context = {
                "effective_price": "",
                "stored_price": stored_price,
                "price_source": "WOO_LIVE_UNAVAILABLE",
                "price_stale": "NO",
                "woo_id": identities["woo_id"],
                "woo_parent_id": identities["woo_parent_id"],
                "woo_item_kind": identities["woo_item_kind"],
                "woo_sku": identities["woo_sku"],
                "direct_price_trace": dict(trace),
            }
            status = _text(trace.get("status")) or "BLOCKED_LIVE_PRICE_UNAVAILABLE"
            blocking_reason = str(exc)
        direct_rows.append({
            **row,
            "source": source,
            "identities": identities,
            "old_price_value": float(old_price) if old_price is not None else None,
            "new_price_value": float(new_price) if new_price is not None else None,
            "woo_price_context": context,
            "price_source": context["price_source"],
            "price_stale": context["price_stale"],
            "price_source_trace": dict(trace),
            "price_adjustment_mode": adjustment_mode,
            "price_adjustment_value": f"{value:.2f}",
            "status": status,
            "blocking_reason": blocking_reason,
            "apply_allowed": "YES" if status == "READY" else "NO",
        })
        if status == "READY" and old_price is not None and new_price is not None:
            changes.append({
                "physical_item_id": identities["physical_item_id"],
                "physical_sku": identities["physical_sku"],
                "old_price": old_price,
                "new_price": new_price,
                "proposal_key": _text(row.get("key") or code),
            })
        if progress_callback is not None:
            progress_callback({
                "phase": "DIRECT_IDENTITY_COMPLETE",
                "processed": position,
                "total": total_direct_rows,
                "code": code,
                "name": _text(row.get("name")),
            })

    candidate_popup_impact = _impact_for_changes(impact_service, changes)
    graph_coverage = _graph_coverage_for_changes(impact_service, changes, candidate_popup_impact)
    blocked_graph_identities = {
        (_text(row.get("physical_item_id")), _text(row.get("physical_sku")))
        for row in graph_coverage
        if _text(row.get("status")) == "BLOCKED_GRAPH_COVERAGE"
    }
    if blocked_graph_identities:
        for direct in direct_rows:
            identities = dict(direct.get("identities") or {})
            identity = (_text(identities.get("physical_item_id")), _text(identities.get("physical_sku")))
            if identity not in blocked_graph_identities:
                continue
            evidence = next(row for row in graph_coverage if (
                _text(row.get("physical_item_id")), _text(row.get("physical_sku"))
            ) == identity)
            direct["status"] = "BLOCKED_GRAPH_COVERAGE"
            direct["blocking_reason"] = evidence["blocking_reason"]
            direct["apply_allowed"] = "NO"
        changes = [
            change for change in changes
            if (_text(change.get("physical_item_id")), _text(change.get("physical_sku"))) not in blocked_graph_identities
        ]

    combined_changes = [*prior_changes, *changes]
    previous_impact = _impact_for_changes(impact_service, prior_changes)
    popup_impact = _impact_for_changes(impact_service, changes)
    combined_impact = _impact_for_changes(impact_service, combined_changes)
    combined_plan = reconcile_live_combination_plan(
        combined_changes,
        impact_service=impact_service,
        woo_client=woo_client,
        session=read_only_session,
        progress_callback=progress_callback,
    ) if combined_changes else {"derived_lines": [], "blocked_lines": [], "excluded_lines": [], "all_lines": [], "counts": {}}
    popup_plan = reconcile_live_combination_plan(
        changes,
        impact_service=impact_service,
        woo_client=woo_client,
        session=read_only_session,
        progress_callback=progress_callback,
    ) if changes else {"derived_lines": [], "blocked_lines": [], "excluded_lines": [], "all_lines": [], "counts": {}}
    # Preserve the older impact payload for callers that render diagnostic
    # graph data, while the proposal itself uses only live-validated rows.
    _decorate_plan_lines(
        popup_plan.get("all_lines") or [],
        incremental_by_destination=_impact_by_destination(popup_impact),
        prior_by_destination=_impact_by_destination(previous_impact),
        combined_by_destination=_impact_by_destination(combined_impact),
        sync_by_woo_id={},
    )
    _decorate_plan_lines(
        combined_plan.get("all_lines") or [],
        incremental_by_destination=_impact_by_destination(popup_impact),
        prior_by_destination=_impact_by_destination(previous_impact),
        combined_by_destination=_impact_by_destination(combined_impact),
        sync_by_woo_id={},
    )
    incremental_filter_report: list[dict[str, Any]] = []
    for line in popup_plan.get("all_lines") or []:
        matching_changes = [
            change for change in changes
            if validate_incremental_destination(line, change["physical_item_id"], change["physical_sku"])
        ]
        included = bool(matching_changes)
        incremental_filter_report.append({
            "destination_woo_id": line.get("combination_woo_id"),
            "destination_sku": line.get("combination_sku"),
            "included_in_popup": "YES" if included else "NO",
            "reason": "EXACT_INCREMENTAL_COMPONENT_MATCH" if included else "EXCLUDED_NOT_INCREMENTAL_COMPONENT",
            "matching_physical_item_ids": "|".join(change["physical_item_id"] for change in matching_changes),
            "matching_physical_skus": "|".join(change["physical_sku"] for change in matching_changes),
            "validation_status": line.get("validation_status") or "",
            "included_in_proposal": line.get("included_in_proposal") or "NO",
        })

    return {
        "direct_rows": direct_rows,
        "combination_impact": popup_impact,
        "previous_combination_impact": previous_impact,
        "combined_combination_impact": combined_impact,
        "combination_plan": combined_plan,
        "popup_combination_plan": popup_plan,
        "incremental_filter_report": incremental_filter_report,
        "graph_coverage": graph_coverage,
        "sync": {
            "mode": "READ_ONLY_NO_REPLICA_SYNC",
            "replica_write": False,
            "counts": {"insert": 0, "update": 0, "no_change": 0, "blocked": 0},
        },
        "counts": {
            "direct_ready": sum(row["status"] == "READY" for row in direct_rows),
            "direct_blocked": sum(row["status"] != "READY" for row in direct_rows),
            "derived": int((popup_plan.get("counts") or {}).get("candidates") or 0),
            "valid": int((popup_plan.get("counts") or {}).get("valid") or 0),
            "already_affected": sum(
                row.get("impact_display_status") == "ALREADY_AFFECTED"
                for row in popup_plan.get("all_lines") or []
            ),
            "updated_accumulated": sum(
                row.get("impact_display_status") == "UPDATED_ACCUMULATED_IMPACT"
                for row in popup_plan.get("all_lines") or []
            ),
            "excluded": int((popup_plan.get("counts") or {}).get("excluded") or 0),
            "blocked": int((popup_plan.get("counts") or {}).get("blocked") or 0),
            "price_missing": int((popup_plan.get("counts") or {}).get("price_missing") or 0),
        },
    }

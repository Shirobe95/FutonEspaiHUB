from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from futonhub.cloud.services.woocommerce_publish import (
    _effective_woo_price,
    _pricing_payload_for_effective_price,
    _pricing_snapshot,
)
from futonhub.services.combination_price_impact import (
    CombinationPriceImpactError,
    CombinationPriceImpactService,
)


READY = "READY"
NO_CHANGE = "NO_CHANGE"
EXCLUDED_QUARANTINE = "EXCLUDED_QUARANTINE"
BLOCKED_MISSING_PRICE_CONTEXT = "BLOCKED_MISSING_PRICE_CONTEXT"
BLOCKED_TRACEABILITY_ERROR = "BLOCKED_TRACEABILITY_ERROR"
BLOCKED_INVALID_PAYLOAD = "BLOCKED_INVALID_PAYLOAD"

_CENT = Decimal("0.01")
_REQUIRED_CONTEXT_KEYS = frozenset({
    "id",
    "regular_price",
    "sale_price",
    "price",
    "on_sale",
    "date_on_sale_from",
    "date_on_sale_to",
})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value).replace(",", ".")).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid money value: {value!r}.") from exc


def _response_json(response: Any) -> dict[str, Any]:
    data = response.json() if hasattr(response, "json") else response
    if not isinstance(data, dict):
        raise ValueError("WooCommerce did not return an object.")
    return dict(data)


def _missing_context_fields(context: Mapping[str, Any]) -> list[str]:
    missing = sorted(key for key in _REQUIRED_CONTEXT_KEYS if key not in context)
    if "date_modified" not in context and "date_modified_gmt" not in context:
        missing.append("date_modified/date_modified_gmt")
    return missing


def build_combination_proposal_plan(
    changes: Iterable[Mapping[str, Any]],
    *,
    impact_service: CombinationPriceImpactService,
    woo_client: Any | None,
    woo_context_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a traceable direct-to-derived plan from exact Woo price context.

    ``woo_context_by_id`` is populated by the on-demand synchronization path.
    Reusing it avoids a second variation read when the same calculation needs a
    replica check and a pricing preview.
    """
    change_rows = [dict(change) for change in changes]
    try:
        impact = impact_service.impact_for_changes(change_rows)
    except CombinationPriceImpactError as exc:
        return {
            "status": BLOCKED_TRACEABILITY_ERROR,
            "publication_allowed": "NO",
            "derived_lines": [],
            "excluded_lines": [],
            "traceability_errors": [{"status": BLOCKED_TRACEABILITY_ERROR, "reason": str(exc)}],
            "counts": {"direct": len(change_rows), "derived": 0, "ready": 0, "blocked": 1, "excluded": 0},
        }

    derived: list[dict[str, Any]] = []
    for raw in impact.get("included_combinations") or []:
        row = dict(raw)
        row.update({
            "entry_origin": "DERIVED_COMBINATION",
            "source_component_entry_ids": list(row.get("proposal_trace_keys") or []),
            "physical_item_ids": sorted({
                _text(component.get("component_item_id"))
                for component in row.get("modified_components") or []
                if _text(component.get("component_item_id"))
            }),
            "physical_skus": sorted({
                _text(component.get("component_sku"))
                for component in row.get("modified_components") or []
                if _text(component.get("component_sku"))
            }),
            "status": BLOCKED_MISSING_PRICE_CONTEXT,
            "publication_allowed": "NO",
            "blocking_reason": "Current full Woo price context has not been loaded.",
            "woo_price_context": {},
            "future_pricing_payload": {},
            "pricing_strategy": "",
        })
        cached_context = (woo_context_by_id or {}).get(str(row["combination_woo_id"]))
        if cached_context is not None:
            context = dict(cached_context)
        elif woo_client is None:
            derived.append(row)
            continue
        try:
            if cached_context is None:
                endpoint = (
                    f"products/{int(row['combination_parent_woo_id'])}/variations/"
                    f"{int(row['combination_woo_id'])}"
                )
                context = _response_json(woo_client.get(endpoint))
            missing = _missing_context_fields(context)
            if missing:
                raise KeyError(", ".join(missing))
            if int(context.get("id") or 0) != int(row["combination_woo_id"]):
                row["status"] = BLOCKED_TRACEABILITY_ERROR
                row["blocking_reason"] = "Woo variation ID does not match the approved exact combination identity."
                derived.append(row)
                continue
            current_price = _effective_woo_price(context)
            if current_price is None:
                raise KeyError("effective price")
            delta = _money(row.get("component_delta"))
            new_price = (_money(current_price) + delta).quantize(_CENT, rounding=ROUND_HALF_UP)
            if new_price <= 0:
                row["status"] = BLOCKED_INVALID_PAYLOAD
                row["blocking_reason"] = "The derived effective price must be greater than zero."
                derived.append(row)
                continue
            payload, strategy = _pricing_payload_for_effective_price(context, float(new_price))
            if not payload or not set(payload).issubset({"regular_price", "sale_price"}):
                row["status"] = BLOCKED_INVALID_PAYLOAD
                row["blocking_reason"] = "The approved pricing policy returned an invalid payload."
                derived.append(row)
                continue
            row.update({
                "effective_current_price": f"{current_price:.2f}",
                "simulated_effective_price": f"{new_price:.2f}",
                "woo_price_context": {
                    **_pricing_snapshot(context),
                    "id": context.get("id"),
                    "parent_id": int(row["combination_parent_woo_id"]),
                    "date_modified": context.get("date_modified"),
                    "date_modified_gmt": context.get("date_modified_gmt"),
                },
                "future_pricing_payload": dict(payload),
                "pricing_strategy": strategy,
                "status": NO_CHANGE if delta == 0 else READY,
                "publication_allowed": "YES",
                "blocking_reason": "",
                "price_policy_reason": "Calculated with _pricing_payload_for_effective_price.",
            })
        except KeyError as exc:
            row["blocking_reason"] = f"Missing required current Woo price context: {exc}."
        except Exception as exc:
            row["status"] = BLOCKED_MISSING_PRICE_CONTEXT
            row["blocking_reason"] = f"Could not load current Woo price context: {exc}"
        derived.append(row)

    excluded = [
        {
            **dict(row),
            "entry_origin": "DERIVED_COMBINATION",
            "status": EXCLUDED_QUARANTINE,
            "publication_allowed": "NO",
        }
        for row in impact.get("excluded_combinations") or []
    ]
    # A direct proposal may legitimately have no combination relationship. The
    # adapter keeps those rows as unmatched diagnostics, not as group blockers.
    traceability_errors: list[dict[str, Any]] = []
    blocked = sum(row["status"].startswith("BLOCKED_") for row in derived)
    ready = sum(row["status"] in {READY, NO_CHANGE} for row in derived)
    return {
        **impact,
        "status": READY if blocked == 0 else "BLOCKED",
        "price_policy": "EXISTING_DIRECT_PRICE_POLICY",
        "publication_allowed": "YES" if blocked == 0 else "NO",
        "derived_lines": derived,
        "excluded_lines": excluded,
        "traceability_errors": traceability_errors,
        "counts": {
            **dict(impact.get("counts") or {}),
            "direct": len(change_rows),
            "derived": len(derived),
            "ready": ready,
            "blocked": blocked,
            "excluded": len(excluded),
        },
    }


def derived_source_row(
    row: Mapping[str, Any],
    *,
    proposal_name: str,
    save_token: str,
    source_proposal_ids: Iterable[str],
) -> dict[str, Any]:
    """Return the source_row extension used by one persisted derived line."""
    return {
        "entry_origin": "DERIVED_COMBINATION",
        "ui_proposal_name": proposal_name,
        "ui_save_token": save_token,
        "ui_line_code": _text(row.get("combination_sku")) or _text(row.get("combination_woo_id")),
        "ui_line_name": _text(row.get("combination_name")),
        "ui_canonical_item_kind": "variation",
        "ui_canonical_woo_id": int(row["combination_woo_id"]),
        "source_component_entry_ids": list(dict.fromkeys(str(value) for value in source_proposal_ids)),
        "source_component_trace_keys": list(row.get("proposal_trace_keys") or []),
        "physical_item_ids": list(row.get("physical_item_ids") or []),
        "physical_skus": list(row.get("physical_skus") or []),
        "woo_combination_id": int(row["combination_woo_id"]),
        "woo_parent_id": int(row["combination_parent_woo_id"]),
        "woo_id": int(row["combination_woo_id"]),
        "woo_item_kind": "variation",
        "woo_sku": _text(row.get("combination_sku")),
        "combination_sku": _text(row.get("combination_sku")),
        "price_at_creation": float(_money(row.get("effective_current_price"))),
        "proposed_price": float(_money(row.get("simulated_effective_price"))),
        "component_delta": _text(row.get("component_delta")),
        "incremental_component_delta": _text(row.get("incremental_component_delta")),
        "previous_accumulated_delta": _text(row.get("previous_accumulated_delta")),
        "new_accumulated_delta": _text(row.get("new_accumulated_delta")),
        "impact_display_status": _text(row.get("impact_display_status")),
        "modified_components": list(row.get("modified_components") or []),
        "inclusion_reason": _text(row.get("inclusion_reason")),
        "derived_status": _text(row.get("status")),
        "publication_allowed": _text(row.get("publication_allowed")),
        "blocking_reason": _text(row.get("blocking_reason")),
        "woo_price_context_at_creation": dict(row.get("woo_price_context") or {}),
        "price_source": _text((row.get("woo_price_context") or {}).get("price_source")) or "WOO_LIVE",
        "price_read_at": (row.get("woo_price_context") or {}).get("price_read_at"),
        "woo_date_modified": (row.get("woo_price_context") or {}).get("woo_date_modified"),
        "supabase_replica_status": _text(row.get("supabase_replica_status")),
        "sync_action": _text(row.get("sync_action")),
        "future_pricing_payload": dict(row.get("future_pricing_payload") or {}),
        "pricing_strategy": _text(row.get("pricing_strategy")),
        "price_policy_function": "_pricing_payload_for_effective_price",
        "excluded": _text(row.get("excluded")) or "NO",
    }

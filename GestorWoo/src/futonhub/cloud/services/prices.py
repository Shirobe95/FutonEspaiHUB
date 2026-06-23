from __future__ import annotations

from typing import Any


PRICE_PROPOSAL_STATUSES = {"pending", "approved", "publishing", "rejected", "published", "rolled_back", "error", "cancelled"}


def short_row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def money_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text.replace(",", "."))
    except Exception:
        return None


def current_price_from_item(item: dict[str, Any]) -> float | None:
    return money_or_none(short_row_value(item, "price", "regular_price", "sale_price"))


def product_type(item: dict[str, Any], kind: str) -> str:
    if kind == "variation":
        return "variation"
    return str(item.get("type") or "product").strip().lower()


def price_safety_preview(item: dict[str, Any], kind: str, proposed_price: float | None, settings) -> dict[str, Any]:
    current = current_price_from_item(item)
    kind = (kind or "").strip().lower()
    item_type = product_type(item, kind)
    messages: list[str] = []
    status = "OK"

    if proposed_price is not None and proposed_price <= 0:
        messages.append("ERROR: el precio propuesto debe ser mayor que 0.")
        status = "ERROR"

    if kind == "product" and item_type in {"variable", "variable-subscription"}:
        messages.append("ERROR: el producto padre variable no tiene precio vendible unico. Crea la propuesta sobre una variacion concreta.")
        status = "ERROR"
    elif current is None or current <= 0:
        if kind == "variation":
            messages.append("WARNING: la variacion no tiene precio actual valido en la base interna. La propuesta puede crearse, pero exige revision antes de publicar.")
        else:
            messages.append("WARNING: el producto no tiene precio actual valido en la base interna. La propuesta puede crearse, pero exige revision antes de publicar.")
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
                messages.append(f"ERROR: bajada de precio del {drop_percent:.2f}%, supera el bloqueo configurado ({settings.price_drop_block_percent:.2f}%).")
                status = "ERROR"
            elif drop_percent >= settings.price_drop_warning_percent and status != "ERROR":
                messages.append(f"WARNING: bajada de precio del {drop_percent:.2f}%, supera el aviso configurado ({settings.price_drop_warning_percent:.2f}%). Requiere confirmacion explicita.")
                status = "WARNING"

    if not messages:
        messages.append("OK: validacion de precio sin alertas.")

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


def format_price_safety_for_search(row: dict[str, Any]) -> str | None:
    kind = row.get("item_kind")
    item_type = row.get("type") or ("variation" if kind == "variation" else "")
    price = money_or_none(row.get("price"))
    if kind == "product" and str(item_type).lower() in {"variable", "variable-subscription"} and (price is None or price <= 0):
        return "WARNING: padre variable sin precio propio; usar variaciones."
    if kind == "variation" and (price is None or price <= 0):
        return "WARNING: variacion sin precio actual valido."
    if kind == "product" and str(item_type).lower() not in {"variable", "variable-subscription"} and (price is None or price <= 0):
        return "WARNING: producto simple sin precio actual valido."
    return None

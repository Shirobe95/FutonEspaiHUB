"""Textos de preview sin dependencias de Tk (se pueden probar)."""
from __future__ import annotations

from typing import Any


def format_quantity(value: Any) -> str:
    """12.0 -> '12'; 2.5 -> '2.5'; None/ilegible -> '-'."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "-"


def format_change(before: Any, after: Any) -> str:
    """'3 -> 5'. Sin la flecha, 3 y 5 se leen como '35'."""
    return f"{format_quantity(before)} -> {format_quantity(after)}"


def format_reception_line(line: dict[str, Any]) -> str:
    return (
        f"{line.get('item_code')} - {line.get('item_name')}: "
        f"+{format_quantity(line.get('quantity_received_now'))} "
        f"Stock tienda {format_change(line.get('store_stock_before'), line.get('store_stock_after'))} - "
        f"almacen {format_change(line.get('warehouse_stock_before'), line.get('warehouse_stock_after'))}"
    )

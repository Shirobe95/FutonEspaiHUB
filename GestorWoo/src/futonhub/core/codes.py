from __future__ import annotations

from typing import Any


def normalize_inventory_numeric_code(value: Any) -> str:
    """Return the canonical lookup form without changing alphanumeric codes."""
    text = str(value or "").strip()
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text

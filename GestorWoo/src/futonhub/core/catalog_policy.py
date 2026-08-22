from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Mapping


DISCONTINUED_COMMERCIAL_STATUSES = {
    "descatalogado",
    "discontinued",
    "retirado",
    "fuera catalogo",
    "fuera de catalogo",
}


def normalize_catalog_policy_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def is_discontinued_commercial_status(value: Any) -> bool:
    return normalize_catalog_policy_text(value) in DISCONTINUED_COMMERCIAL_STATUSES


def operational_inactive_reason(row: Mapping[str, Any] | None) -> str:
    if not isinstance(row, Mapping):
        return "INVALID_ROW"
    if is_discontinued_commercial_status(row.get("commercial_status")):
        return "DESCATALOGADO_NO_NEW_OPERATIONAL_SELECTION"
    return ""


def is_operationally_active(row: Mapping[str, Any] | None) -> bool:
    return operational_inactive_reason(row) == ""


def filter_operationally_active_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if is_operationally_active(row)]

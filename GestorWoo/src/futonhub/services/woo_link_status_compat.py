"""Compatibility interpretation for legacy ``inventory_items.woo_link_status`` values.

This is deliberately an interpretation layer.  It never writes or normalizes
the stored value, so historical/manual provenance remains intact until a
separate user-approved enum and migration exist.
"""

from __future__ import annotations

from typing import Any


LINKED = "LINKED"
UNLINKED = "UNLINKED"
NO_DIRECT_WOO = "NO_DIRECT_WOO"
TEST_TECHNICAL = "TEST_TECHNICAL"
UNKNOWN = "UNKNOWN"

_LINKED_VALUES = frozenset({
    "enlazado", "enlazado manual", "linked", "matched", "synced", "sync", "connected",
    "active", "ready", "found", "linked_by_sku", "matched_by_sku", "linked_variation",
    "variation", "parent", "simple", "variable", "woo_synced", "manual", "manual_link",
    "auto", "auto_link",
})
_UNLINKED_VALUES = frozenset({"sin enlazar", "sin woo", "unlinked", "local_only", "woo_only", "pending", "pending_link"})
_NO_DIRECT_VALUES = frozenset({"sin woo directo"})
_TEST_TECHNICAL_VALUES = frozenset({"test_no_woo"})


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def canonical_woo_link_status(value: Any) -> str:
    """Classify a stored legacy value without changing its literal text."""
    normalized = text(value).lower()
    if normalized in _LINKED_VALUES:
        return LINKED
    if normalized in _UNLINKED_VALUES or normalized in {"", "-"}:
        return UNLINKED
    if normalized in _NO_DIRECT_VALUES:
        return NO_DIRECT_WOO
    if normalized in _TEST_TECHNICAL_VALUES:
        return TEST_TECHNICAL
    return UNKNOWN


def is_known_woo_link_status(value: Any) -> bool:
    return canonical_woo_link_status(value) != UNKNOWN

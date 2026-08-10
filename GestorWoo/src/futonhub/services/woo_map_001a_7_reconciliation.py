"""Exhaustive, GET-only reconciliation for the WOO-MAP-001A.7 closure.

This module is deliberately an audit boundary.  It combines the frozen
canonical physical catalogue, the 001A.5 exact baseline, 001A.6 decisions,
the approved component graph, and a live Woo read-only index.  It never
persists a Woo relation or invokes a write client.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping


FINAL_STATUSES = frozenset({
    "ACTIVE_DIRECT_WOO_VERIFIED",
    "ACTIVE_DIRECT_WOO_SAFE_PLAN",
    "NO_DIRECT_WOO_ENTITY_SUPPORTED",
    "RETIRED_CONFIRMED_BY_USER",
    "ACTIVE_HIDDEN_WOO_ENTITY",
    "REVIEW_USER_LINK",
    "REVIEW_USER_RETIREMENT",
    "PHYSICAL_IDENTITY_REVIEW",
    "WOO_CATALOG_INCONSISTENCY",
    "WOO_ENTITY_MISSING",
    "READ_ERROR",
})

RETIRED_ITEM_IDS = frozenset({"406006", "404017"})
RETIRED_PHYSICAL_SKUS = frozenset({"0406006", "0404017"})
# The frozen UI snapshot inherited this one legacy projection error.  The
# business-approved physical code is literal ``0406006``; it is not the
# numeric item_id ``406006`` and the audit layer must never conflate them.
PHYSICAL_SKU_OVERRIDES = {"406006": "0406006"}
DEEP_SAFE_VARIATIONS = {
    "0201013": ("4556", "3657"),
    "0208001": ("4558", "3657"),
    "0216001": ("4561", "3657"),
}
TATAMI_PORTABLE_CODES = frozenset({"0201013", "0208001", "0206001", "0213001", "0216001", "0214001"})
TATAMI_SUPPORT_CODES = frozenset({"0201006", "0201007"})
LEADING_ZERO_DUO_CODES = frozenset({"0078009", "0078012", "0078013"})
COLOR_VALUES = frozenset({"azul", "crudo", "granate", "negro", "naranja", "verde", "natural", "rojo", "violeta"})

_DIMENSION_PATTERN = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[x*]\s*\d+(?:[.,]\d+)?){1,2}", re.IGNORECASE)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normal(value: Any) -> str:
    value = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _normal(value).split() if token}


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "si"}


def _dimensions(value: Any) -> set[str]:
    return {
        match.group(0).replace(" ", "").replace("*", "x").replace(",", ".").lower()
        for match in _DIMENSION_PATTERN.finditer(_text(value))
    }


def _attributes_text(raw: Mapping[str, Any]) -> str:
    values: list[str] = []
    for attribute in raw.get("attributes") or []:
        if not isinstance(attribute, Mapping):
            continue
        name = _text(attribute.get("name"))
        option = _text(attribute.get("option") or attribute.get("value"))
        options = attribute.get("options")
        if isinstance(options, list) and not option:
            option = ", ".join(_text(item) for item in options if _text(item))
        if name or option:
            values.append(f"{name}={option}".strip("="))
    return " | ".join(values)


def _categories_text(raw: Mapping[str, Any]) -> str:
    return " | ".join(
        _text(category.get("name"))
        for category in raw.get("categories") or []
        if isinstance(category, Mapping) and _text(category.get("name"))
    )


def _physical_sku(row: Mapping[str, Any]) -> str:
    """Return the literal physical SKU; item_id is never a SKU fallback."""
    item_id = _text(row.get("item_id") or row.get("physical_item_id"))
    return PHYSICAL_SKU_OVERRIDES.get(
        item_id,
        _text(row.get("hub_item_code") or row.get("heca_reference") or row.get("codigo")),
    )


def _physical_item_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("item_id") or row.get("physical_item_id"))


def _is_retired(row: Mapping[str, Any]) -> bool:
    return _physical_item_id(row) in RETIRED_ITEM_IDS or _physical_sku(row) in RETIRED_PHYSICAL_SKUS


def _parent(entity: Mapping[str, Any], woo_index: Any) -> Mapping[str, Any] | None:
    parent_id = _text(entity.get("parent_woo_id"))
    return woo_index.products_by_id.get(parent_id) if parent_id else None


def _model_requirements(row: Mapping[str, Any]) -> tuple[str, ...]:
    code = _physical_sku(row)
    family = _normal(row.get("filter_family") or row.get("family"))
    group = _normal(row.get("filter_group") or row.get("brand"))
    name = _normal(row.get("name"))
    if code in TATAMI_PORTABLE_CODES:
        return ("tatami", "plegable", "futon", "portatil")
    if code in TATAMI_SUPPORT_CODES:
        return ("tatami", "support")
    if code == "0402014":
        return ("cama", "macao")
    if "mesita" in name and "okinawa" in name:
        return ("mesita", "okinawa")
    if "sofas cama" in family and "luna" in name:
        return ("sofa", "cama", "luna")
    if "futones" in family:
        if "duo latex" in group:
            return ("futon", "duo", "latex")
        if group == "lana":
            return ("futon", "lana")
        if group == "premium":
            return ("futon", "premium")
        if group == "portatil":
            return ("futon", "portatil")
        if "algodon" in group and "latex" in group:
            return ("futon", "algodon", "latex")
        if group == "algodon":
            return ("futon", "algodon")
    if group:
        return tuple(group.split())
    return tuple(token for token in name.split() if token not in {"natural", "cm", "un"})


def _parent_text(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> str:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    values = (
        entity.get("name"), entity.get("woo_sku"), _attributes_text(raw), _categories_text(raw),
        (parent or {}).get("name"), (parent or {}).get("woo_sku"), _attributes_text(parent_raw),
        _categories_text(parent_raw), parent_raw.get("description"), parent_raw.get("short_description"),
    )
    return " ".join(_normal(value) for value in values if _text(value))


def _model_exact(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> bool:
    code = _physical_sku(row)
    text = _parent_text(entity, parent)
    required = _model_requirements(row)
    if code in TATAMI_PORTABLE_CODES:
        return _text(entity.get("parent_woo_id")) == "3657" and all(token in text for token in required)
    if code == "0402014":
        return all(token in text for token in required) and "base" not in text
    if _normal(row.get("filter_group")) == "lana":
        return all(token in text for token in required) and "duo" not in text
    return bool(required) and all(token in text for token in required)


def _observed_dimensions(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> set[str]:
    raw = dict(entity.get("raw") or {})
    values: list[Any] = [entity.get("name"), _attributes_text(raw), raw.get("description")]
    if parent is not None:
        parent_raw = dict(parent.get("raw") or {})
        values.append(parent.get("name"))
        # The documented 3657 set has a fixed tatami size and colour-only
        # children; its description is admissible evidence for that one case.
        if _physical_sku(row) in TATAMI_PORTABLE_CODES:
            values.extend((parent_raw.get("description"), parent_raw.get("short_description")))
    result: set[str] = set()
    for value in values:
        result.update(_dimensions(value))
    return result


def _variant_exact(required_value: Any, entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> bool:
    required = _normal(required_value)
    if required in {"", "no gama", "sin gama", "na", "n a"}:
        return True
    raw = dict(entity.get("raw") or {})
    # Parent option lists enumerate all variants and cannot prove a child.
    values = [entity.get("name"), entity.get("woo_sku"), _attributes_text(raw)]
    if parent is None:
        values.append(_attributes_text(raw))
    text = _normal(" ".join(_text(value) for value in values))
    if required not in text:
        return False
    if required in COLOR_VALUES:
        for suffix in ("oscuro", "claro", "marino"):
            if f"{required} {suffix}" in text and f"{required} {suffix}" != required:
                return False
        if required == "natural" and any(value in text for value in ("crudo", "wengue", "sin barniz")):
            return False
    return True


def _is_pack(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> bool:
    raw = dict(entity.get("raw") or {})
    text = _normal(" ".join((_text(entity.get("name")), _text((parent or {}).get("name")), _text(entity.get("woo_sku")), _text(raw.get("sku")))))
    return "pack" in text or "kit" in text or "|" in _text(entity.get("woo_sku"))


def _historical_signals(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[str, ...]:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    values = (
        entity.get("name"), raw.get("slug"), _categories_text(raw),
        (parent or {}).get("name"), parent_raw.get("slug"), _categories_text(parent_raw),
    )
    text = _normal(" ".join(_text(value) for value in values))
    result: list[str] = []
    status = _normal(raw.get("status") or entity.get("status"))
    visibility = _normal(raw.get("catalog_visibility"))
    if status and status != "publish":
        result.append("NON_PUBLISH_STATUS")
    if visibility and visibility != "visible":
        result.append("HIDDEN_CATALOG_VISIBILITY")
    if "outlet" in text or "unica unidad" in text:
        result.append("OUTLET_OR_CLEARANCE_SIGNAL")
    return tuple(result)


def _entity_fingerprint(entity: Mapping[str, Any]) -> str:
    raw = dict(entity.get("raw") or {})
    payload = {
        "id": _text(entity.get("woo_id")), "parent": _text(entity.get("parent_woo_id")),
        "kind": _text(entity.get("woo_item_kind")), "sku": _text(entity.get("woo_sku")),
        "name": _text(entity.get("name")), "status": _text(raw.get("status") or entity.get("status")),
        "modified": _text(entity.get("date_modified") or raw.get("date_modified_gmt") or raw.get("date_modified")),
    }
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def _physical_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        "item_id": _physical_item_id(row), "sku": _physical_sku(row), "name": _text(row.get("name")),
        "family": _text(row.get("filter_family") or row.get("family")),
        "group": _text(row.get("filter_group") or row.get("brand")),
        "size": _text(row.get("filter_size") or row.get("size")),
        "gama": _text(row.get("filter_gama") or row.get("catalog_range")),
    }
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Candidate:
    entity: Mapping[str, Any]
    parent: Mapping[str, Any] | None
    model_exact: bool
    size_exact: bool
    variant_exact: bool
    is_pack: bool
    historical_signals: tuple[str, ...]
    claimed_by: tuple[str, ...]

    @property
    def kind(self) -> str:
        return _text(self.entity.get("woo_item_kind"))

    @property
    def woo_id(self) -> str:
        return _text(self.entity.get("woo_id"))

    @property
    def parent_id(self) -> str:
        return _text(self.entity.get("parent_woo_id"))

    @property
    def is_full_exact(self) -> bool:
        return self.model_exact and self.size_exact and self.variant_exact and not self.is_pack

    @property
    def is_current_direct(self) -> bool:
        return self.is_full_exact and not self.historical_signals and not self.claimed_by

    def score(self) -> tuple[int, int, int, str]:
        return (
            1 if self.is_current_direct else 0,
            int(self.model_exact) + int(self.size_exact) + int(self.variant_exact),
            -len(self.historical_signals) - int(self.is_pack) - int(bool(self.claimed_by)),
            self.woo_id,
        )


def _candidate(row: Mapping[str, Any], entity: Mapping[str, Any], woo_index: Any, claims: Mapping[tuple[str, str, str], set[str]]) -> Candidate:
    parent = _parent(entity, woo_index)
    required_size = _text(row.get("filter_size") or row.get("size"))
    observed = _observed_dimensions(row, entity, parent)
    size_exact = bool(_dimensions(required_size)) and _dimensions(required_size).issubset(observed)
    target = (_text(entity.get("woo_item_kind")), _text(entity.get("parent_woo_id")), _text(entity.get("woo_id")))
    claimed = tuple(sorted(claims.get(target, set()) - {_physical_sku(row)}))
    return Candidate(
        entity=entity, parent=parent, model_exact=_model_exact(row, entity, parent), size_exact=size_exact,
        variant_exact=_variant_exact(row.get("filter_gama") or row.get("catalog_range"), entity, parent),
        is_pack=_is_pack(entity, parent) and _physical_sku(row) not in TATAMI_PORTABLE_CODES,
        historical_signals=_historical_signals(entity, parent), claimed_by=claimed,
    )


def _all_candidates(row: Mapping[str, Any], woo_index: Any, claims: Mapping[tuple[str, str, str], set[str]]) -> list[Candidate]:
    code = _physical_sku(row)
    by_key: dict[tuple[str, str, str], Candidate] = {}
    entities = list(woo_index.products_by_id.values()) + list(woo_index.variations_by_id.values())
    for entity in entities:
        parent = _parent(entity, woo_index)
        candidate = _candidate(row, entity, woo_index, claims)
        # Exact SKU must always be retained.  Other entries must have a real
        # model token intersection, an exact size, or an exact variant; this
        # produces an exhaustive but non-fuzzy research universe.
        entity_text = _parent_text(entity, parent)
        model_overlap = set(_model_requirements(row)).intersection(_tokens(entity_text))
        exact_sku = _text(entity.get("woo_sku")) == code
        if exact_sku or candidate.size_exact or candidate.variant_exact or model_overlap:
            by_key[(candidate.kind, candidate.parent_id, candidate.woo_id)] = candidate
    return sorted(by_key.values(), key=lambda item: item.score(), reverse=True)


def _build_indexes(woo_index: Any) -> dict[str, Any]:
    """Materialise required global lookup facets, strictly as candidate aids."""
    products_by_model_tokens: dict[str, list[str]] = defaultdict(list)
    products_by_normalized_name: dict[str, list[str]] = defaultdict(list)
    variations_by_dimension_signature: dict[str, list[str]] = defaultdict(list)
    variations_by_variant_signature: dict[str, list[str]] = defaultdict(list)
    variations_by_full_attribute_signature: dict[str, list[str]] = defaultdict(list)
    products_by_category: dict[str, list[str]] = defaultdict(list)
    products_by_status: dict[str, list[str]] = defaultdict(list)
    for product in woo_index.products_by_id.values():
        raw = dict(product.get("raw") or {})
        product_id = _text(product.get("woo_id"))
        products_by_normalized_name[_normal(product.get("name"))].append(product_id)
        for token in _tokens(product.get("name")):
            products_by_model_tokens[token].append(product_id)
        for category in _categories_text(raw).split(" | "):
            if category:
                products_by_category[_normal(category)].append(product_id)
        products_by_status[_normal(raw.get("status") or product.get("status"))].append(product_id)
    for variation in woo_index.variations_by_id.values():
        raw = dict(variation.get("raw") or {})
        variation_id = _text(variation.get("woo_id"))
        dimensions = sorted(_dimensions(" ".join((_text(variation.get("name")), _attributes_text(raw)))))
        variants = _normal(_attributes_text(raw))
        for dimension in dimensions:
            variations_by_dimension_signature[dimension].append(variation_id)
        if variants:
            variations_by_variant_signature[variants].append(variation_id)
        variations_by_full_attribute_signature[f"{'|'.join(dimensions)}::{variants}"].append(variation_id)
    return {
        "products_by_id": len(woo_index.products_by_id),
        "variations_by_id": len(woo_index.variations_by_id),
        "products_by_exact_sku": len(woo_index.products_by_exact_sku),
        "variations_by_exact_sku": len(woo_index.variations_by_exact_sku),
        "variations_by_parent": len(woo_index.variations_by_parent),
        "products_by_model_tokens": len(products_by_model_tokens),
        "products_by_normalized_name": len(products_by_normalized_name),
        "variations_by_dimension_signature": len(variations_by_dimension_signature),
        "variations_by_variant_signature": len(variations_by_variant_signature),
        "variations_by_full_attribute_signature": len(variations_by_full_attribute_signature),
        "products_by_category": len(products_by_category),
        "products_by_status": len(products_by_status),
    }


def _component_evidence(graph: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
    for raw in graph.get("composition_edges") or []:
        edge = dict(raw)
        if _text(edge.get("operational_status_001a3")) not in {"", "INCLUDED_EXACT"}:
            continue
        item_id = _text(edge.get("component_item_id") or edge.get("physical_item_id"))
        if not item_id:
            continue
        evidence[item_id].append({
            "woo_id": _text(edge.get("combination_woo_id")),
            "parent_id": _text(edge.get("combination_parent_woo_id")),
            "sku": _text(edge.get("combination_sku")),
            "name": _text(edge.get("combination_name")),
            "quantity": _text(edge.get("quantity")),
        })
    return evidence


def _entity_fields(entity: Mapping[str, Any] | None) -> dict[str, str]:
    if entity is None:
        return {key: "" for key in ("woo_id", "woo_parent_id", "woo_kind", "woo_sku", "woo_name", "woo_status")}
    raw = dict(entity.get("raw") or {})
    return {
        "woo_id": _text(entity.get("woo_id")), "woo_parent_id": _text(entity.get("parent_woo_id")),
        "woo_kind": _text(entity.get("woo_item_kind")), "woo_sku": _text(entity.get("woo_sku")),
        "woo_name": _text(entity.get("name")), "woo_status": _text(raw.get("status") or entity.get("status")),
    }


def _master_row(
    row: Mapping[str, Any], *, status: str, entity: Mapping[str, Any] | None, source: str,
    reason: str, safe: bool = False, review: bool = False, direct: bool = False,
    component_edges: Iterable[Mapping[str, Any]] = (), historical_entity: Mapping[str, Any] | None = None,
    historical_reason: str = "",
) -> dict[str, str]:
    physical_sku = _physical_sku(row)
    item_id = _physical_item_id(row)
    components = list(component_edges)
    current = _entity_fields(entity)
    historical = _entity_fields(historical_entity)
    return {
        "physical_item_id": item_id,
        "physical_sku": physical_sku,
        "canonical_name": _text(row.get("name")),
        "family": _text(row.get("filter_family") or row.get("family")),
        "group": _text(row.get("filter_group") or row.get("brand")),
        "size": _text(row.get("filter_size") or row.get("size")),
        "gama": _text(row.get("filter_gama") or row.get("catalog_range")),
        "commercial_status": "RETIRED_CONFIRMED_BY_USER" if status == "RETIRED_CONFIRMED_BY_USER" else "ACTIVE_OR_UNCONFIRMED",
        "woo_resolution_status": status,
        **current,
        "direct_entity": "YES" if direct else "NO",
        "component_only": "YES" if status == "NO_DIRECT_WOO_ENTITY_SUPPORTED" else "NO",
        "affected_combination_count": str(len(components)),
        "resolution_source": source,
        "resolution_reason": reason,
        "safe_to_persist": "YES" if safe else "NO",
        "requires_user_review": "YES" if review else "NO",
        "price_change_eligible": "YES" if safe else "NO",
        "historical_woo_id": historical["woo_id"],
        "historical_reason": historical_reason,
        "physical_identity_sha256": _physical_fingerprint(row),
        "woo_identity_sha256": _entity_fingerprint(entity) if entity is not None else "",
    }


def _review_row(master: Mapping[str, str], candidates: Iterable[Candidate]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rank, candidate in enumerate(list(candidates)[:3], start=1):
        raw = dict(candidate.entity.get("raw") or {})
        parent_raw = dict((candidate.parent or {}).get("raw") or {})
        rows.append({
            "physical_item_id": master["physical_item_id"], "physical_sku": master["physical_sku"],
            "canonical_name": master["canonical_name"], "woo_resolution_status": master["woo_resolution_status"],
            "candidate_rank": str(rank), "woo_id": candidate.woo_id, "woo_parent_id": candidate.parent_id,
            "woo_kind": candidate.kind, "woo_sku": _text(candidate.entity.get("woo_sku")),
            "woo_name": _text(candidate.entity.get("name")),
            "woo_parent_name": _text((candidate.parent or {}).get("name")),
            "woo_status": _text(raw.get("status") or candidate.entity.get("status")),
            "catalog_visibility": _text(raw.get("catalog_visibility") or parent_raw.get("catalog_visibility")),
            "attributes": _attributes_text(raw), "categories": _categories_text(raw) or _categories_text(parent_raw),
            "evidence_for": " | ".join(name for name, value in (("MODEL_EXACT", candidate.model_exact), ("SIZE_EXACT", candidate.size_exact), ("VARIANT_EXACT", candidate.variant_exact)) if value),
            "evidence_against": " | ".join(
                (["PACK_INSTEAD_OF_DIRECT"] if candidate.is_pack else []) +
                list(candidate.historical_signals) +
                ([f"CLAIMED_BY={','.join(candidate.claimed_by)}"] if candidate.claimed_by else [])
            ),
            "resolution_reason": master["resolution_reason"],
        })
    if not rows:
        rows.append({
            "physical_item_id": master["physical_item_id"], "physical_sku": master["physical_sku"],
            "canonical_name": master["canonical_name"], "woo_resolution_status": master["woo_resolution_status"],
            "candidate_rank": "0", "woo_id": "", "woo_parent_id": "", "woo_kind": "", "woo_sku": "",
            "woo_name": "", "woo_parent_name": "", "woo_status": "", "catalog_visibility": "", "attributes": "",
            "categories": "", "evidence_for": "", "evidence_against": "", "resolution_reason": master["resolution_reason"],
        })
    return rows


def _candidate_for_identity(woo_index: Any, *, kind: str, woo_id: str, parent_id: str = "") -> Mapping[str, Any] | None:
    if kind == "product":
        return woo_index.products_by_id.get(woo_id)
    value = woo_index.variations_by_id.get(woo_id)
    return value if value is not None and _text(value.get("parent_woo_id")) == parent_id else None


def reconcile_exhaustive(
    physical_rows: Iterable[Mapping[str, Any]], *, safe_rows: Iterable[Mapping[str, Any]],
    graph: Mapping[str, Any], woo_index: Any,
) -> dict[str, Any]:
    """Classify every canonical physical row without making any write call."""
    rows = [dict(row) for row in physical_rows]
    safe_by_item = {_text(row.get("item_id")): dict(row) for row in safe_rows}
    if len(rows) != 254 or len({_physical_item_id(row) for row in rows}) != 254:
        raise RuntimeError("001A.7 requires exactly 254 unique canonical physical item IDs.")
    if len(safe_by_item) != 174:
        raise RuntimeError("001A.7 requires the frozen 174-row safe baseline.")

    index_facets = _build_indexes(woo_index)
    component_by_item = _component_evidence(graph)
    claims: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for safe in safe_by_item.values():
        claims[(_text(safe.get("woo_item_kind")), _text(safe.get("woo_parent_id")), _text(safe.get("woo_id")))].add(_physical_sku(safe))
    for code, (woo_id, parent_id) in DEEP_SAFE_VARIATIONS.items():
        claims[("variation", parent_id, woo_id)].add(code)

    master: list[dict[str, str]] = []
    baseline: list[dict[str, str]] = []
    residual_review: list[dict[str, str]] = []
    component_only: list[dict[str, str]] = []
    for row in rows:
        item_id = _physical_item_id(row)
        code = _physical_sku(row)
        candidates: list[Candidate] = []
        if not item_id or not code:
            record = _master_row(row, status="READ_ERROR", entity=None, source="CANONICAL_SNAPSHOT", reason="Missing canonical item_id or physical_sku.", review=True)
        elif item_id in safe_by_item:
            safe = safe_by_item[item_id]
            entity = _candidate_for_identity(woo_index, kind=_text(safe.get("woo_item_kind")), woo_id=_text(safe.get("woo_id")), parent_id=_text(safe.get("woo_parent_id")))
            if entity is None:
                record = _master_row(row, status="READ_ERROR", entity=None, source="WOO_MAP_001A_5_SAFE_BASELINE", reason="Frozen exact Woo destination was not readable in the live GET index.", review=True)
            else:
                record = _master_row(row, status="ACTIVE_DIRECT_WOO_VERIFIED", entity=entity, source="WOO_MAP_001A_5_SAFE_BASELINE", reason="Frozen exact baseline revalidated by Woo GET.", safe=True, direct=True)
        elif code in DEEP_SAFE_VARIATIONS:
            woo_id, parent_id = DEEP_SAFE_VARIATIONS[code]
            entity = _candidate_for_identity(woo_index, kind="variation", woo_id=woo_id, parent_id=parent_id)
            if entity is None:
                record = _master_row(row, status="READ_ERROR", entity=None, source="WOO_MAP_001A_6_DEEP_REVIEW", reason="Approved deep-review variation was not readable in the live GET index.", review=True)
            else:
                record = _master_row(row, status="ACTIVE_DIRECT_WOO_SAFE_PLAN", entity=entity, source="WOO_MAP_001A_6_DEEP_REVIEW", reason="Exact parent, fixed size, and child variant revalidated by Woo GET; relation remains unpersisted.", safe=True, direct=True)
        elif _is_retired(row):
            # Retired commercial items keep traceability only.  A prior human
            # decision, not a non-publish status, establishes retirement.
            historical = None
            for entity in list(woo_index.products_by_id.values()) + list(woo_index.variations_by_id.values()):
                parent = _parent(entity, woo_index)
                if all(token in _parent_text(entity, parent) for token in _model_requirements(row)):
                    historical = entity
                    break
            record = _master_row(row, status="RETIRED_CONFIRMED_BY_USER", entity=None, source="USER_DECISION_001A_6", reason="Confirmed retired by user. No replacement search is permitted.", historical_entity=historical, historical_reason="Woo retained only as historical trace; price changes are not eligible.")
        else:
            candidates = _all_candidates(row, woo_index, claims)
            exact = [candidate for candidate in candidates if candidate.is_current_direct]
            structural = [candidate for candidate in candidates if candidate.is_full_exact]
            component_edges = component_by_item.get(item_id, [])
            if code in LEADING_ZERO_DUO_CODES:
                record = _master_row(row, status="PHYSICAL_IDENTITY_REVIEW", entity=None, source="LEADING_ZERO_IDENTITY_CONTROL", reason="Leading-zero physical SKU is not merged with a different 078... SKU without documented identity evidence.", review=True)
            elif code == "0402014":
                record = _master_row(row, status="WOO_CATALOG_INCONSISTENCY", entity=None, source="GLOBAL_WOO_INDEX", reason="Cama Macao is not represented by Base para Tatami Macao or its variations.", review=True)
            elif code == "0206001" and structural:
                record = _master_row(row, status="ACTIVE_HIDDEN_WOO_ENTITY", entity=structural[0].entity, source="GLOBAL_WOO_INDEX", reason="Exact structural variation exists but is hidden or non-publish; retirement is not inferred automatically.", review=True, direct=True)
            elif len(exact) == 1:
                # A global signature can discover a real candidate outside the
                # old research universe, but it cannot silently expand the
                # frozen 177-safe baseline without a separately documented
                # identity decision.  It is therefore concrete review
                # evidence, not an automatic persistence candidate.
                record = _master_row(row, status="REVIEW_USER_LINK", entity=None, source="GLOBAL_WOO_INDEX", reason="One strict direct candidate was discovered outside the prior research universe; it requires an explicit identity decision before entering the SAFE baseline.", review=True)
            elif len(exact) > 1:
                record = _master_row(row, status="REVIEW_USER_LINK", entity=None, source="GLOBAL_WOO_INDEX", reason="Several direct Woo entities satisfy the strict signature; choose only with user evidence.", review=True)
            elif structural and any(candidate.historical_signals for candidate in structural):
                record = _master_row(row, status="REVIEW_USER_RETIREMENT", entity=structural[0].entity, source="GLOBAL_WOO_INDEX", reason="Only exact Woo evidence has historical, outlet, hidden, or non-publish signals; retirement requires user decision.", review=True)
            elif component_edges:
                examples = ", ".join(_text(edge.get("woo_id")) for edge in component_edges[:3] if _text(edge.get("woo_id")))
                record = _master_row(row, status="NO_DIRECT_WOO_ENTITY_SUPPORTED", entity=None, source="APPROVED_COMPONENT_GRAPH", reason=f"No direct Woo entity; supported as a component in {len(component_edges)} approved combinations ({examples}).", component_edges=component_edges)
            elif candidates:
                record = _master_row(row, status="REVIEW_USER_LINK", entity=None, source="GLOBAL_WOO_INDEX", reason="Nearby Woo evidence exists but fails at least one exact identity control.", review=True)
            else:
                record = _master_row(row, status="WOO_ENTITY_MISSING", entity=None, source="GLOBAL_WOO_INDEX", reason="No direct Woo entity or supporting component evidence exists in the complete GET index.")

        master.append(record)
        if record["woo_resolution_status"] in {"ACTIVE_DIRECT_WOO_VERIFIED", "ACTIVE_DIRECT_WOO_SAFE_PLAN"}:
            baseline.append({
                "physical_item_id": record["physical_item_id"], "physical_sku": record["physical_sku"], "woo_id": record["woo_id"],
                "woo_parent_id": record["woo_parent_id"], "woo_kind": record["woo_kind"], "woo_sku": record["woo_sku"],
                "woo_name": record["woo_name"], "resolution_source": record["resolution_source"], "resolution_status": record["woo_resolution_status"],
            })
        if record["requires_user_review"] == "YES":
            residual_review.extend(_review_row(record, candidates))
        if record["woo_resolution_status"] == "NO_DIRECT_WOO_ENTITY_SUPPORTED":
            edges = component_by_item.get(item_id, [])
            component_only.append({
                "physical_sku": record["physical_sku"], "name": record["canonical_name"], "family": record["family"],
                "component_usage_count": str(len(edges)),
                "example_woo_destinations": " | ".join(f"{_text(edge.get('woo_id'))}:{_text(edge.get('name'))}" for edge in edges[:3]),
                "reason_no_direct_entity": record["resolution_reason"],
            })

    claims_by_target: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for record in master:
        if record["safe_to_persist"] == "YES":
            claims_by_target[(record["woo_kind"], record["woo_parent_id"], record["woo_id"])].append(record)
    incompatible = [records for records in claims_by_target.values() if len(records) > 1]
    if incompatible:
        codes = "; ".join(",".join(record["physical_sku"] for record in records) for records in incompatible)
        raise RuntimeError(f"Incompatible safe Woo destinations: {codes}")
    if len(baseline) != 177 or len({record["physical_sku"] for record in baseline}) != 177:
        raise RuntimeError("The safe baseline must contain exactly 177 unique physical SKUs.")
    if len(master) != 254 or len({record["physical_item_id"] for record in master}) != 254:
        raise RuntimeError("The final master must contain exactly 254 unique physical rows.")
    if any(record["woo_resolution_status"] not in FINAL_STATUSES for record in master):
        raise RuntimeError("The final master emitted an unsupported status.")

    safe_persistence = [
        {
            "physical_item_id": record["physical_item_id"], "physical_sku": record["physical_sku"], "woo_id": record["woo_id"],
            "woo_parent_id": record["woo_parent_id"], "woo_kind": record["woo_kind"], "woo_sku": record["woo_sku"],
            "woo_name": record["woo_name"], "resolution_status": record["woo_resolution_status"],
            "physical_identity_sha256": record["physical_identity_sha256"], "woo_identity_sha256": record["woo_identity_sha256"],
            "apply_status": "PLAN_ONLY_NO_APPLY",
        }
        for record in master if record["safe_to_persist"] == "YES"
    ]
    counts = Counter(record["woo_resolution_status"] for record in master)
    return {
        "master": master,
        "safe_baseline": baseline,
        "safe_persistence": safe_persistence,
        "component_only": component_only,
        "residual_review": residual_review,
        "summary": {
            "physical_total": len(master), "unclassified": 0,
            "status_counts": dict(sorted(counts.items())), "safe_total": len(safe_persistence),
            "retired_total": counts["RETIRED_CONFIRMED_BY_USER"], "residual_review_physical_total": len({row["physical_item_id"] for row in residual_review}),
            "component_only_total": len(component_only), "safe_destination_conflicts": 0,
            "woo_index_counts": dict(woo_index.counts), "index_facets": index_facets,
            "writes": {"woo": 0, "supabase": 0, "sql": 0, "relationships": 0, "prices": 0, "stock": 0},
        },
    }

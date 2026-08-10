"""Read-only, exact reconciliation for the physical catalogue and Woo.

The module deliberately separates evidence discovery from any future relation
apply. It consumes a frozen canonical catalogue, an approved historical graph
and a Woo GET-only index. It never calls a persistence client.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable, Mapping


SAFE_RESULTS = frozenset({
    "SAFE_DIRECT_PRODUCT",
    "SAFE_DIRECT_VARIATION",
    "SAFE_HISTORICAL_LINK_RECOVERED",
})
REVIEW_RESULTS = frozenset({
    "REVIEW_USER_SINGLE_CANDIDATE",
    "REVIEW_USER_MULTIPLE_CANDIDATES",
    "CONFLICT",
    "READ_ERROR",
})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normal(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {part for part in _normal(value).split() if part}


def _bool(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "si"}


def _attributes(raw: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for attribute in raw.get("attributes") or []:
        if not isinstance(attribute, Mapping):
            continue
        key = _normal(attribute.get("name"))
        value = _text(attribute.get("option") or attribute.get("value"))
        if key and value:
            values[key] = value
    return values


def _categories(raw: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(category.get("name"))
        for category in raw.get("categories") or []
        if isinstance(category, Mapping) and _text(category.get("name"))
    )


_DIMENSION_PATTERN = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[x*]\s*\d+(?:[.,]\d+)?){1,2}", re.IGNORECASE)


def _dimension_keys(value: Any) -> set[str]:
    return {
        match.group(0).replace(" ", "").replace("*", "x").replace(",", ".").lower()
        for match in _DIMENSION_PATTERN.finditer(_text(value))
    }


def _entity_dimension_keys(entity: Mapping[str, Any], parent: Mapping[str, Any] | None = None) -> set[str]:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    values = [
        entity.get("name"), raw.get("slug"), " ".join(_attributes(raw).values()),
        parent.get("name") if parent else "", parent_raw.get("slug"), " ".join(_attributes(parent_raw).values()),
    ]
    result: set[str] = set()
    for value in values:
        result.update(_dimension_keys(value))
    return result


def _entity_haystack(entity: Mapping[str, Any], parent: Mapping[str, Any] | None = None) -> str:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    values = [
        entity.get("name"),
        entity.get("woo_sku"),
        raw.get("slug"),
        " ".join(_categories(raw)),
        " ".join(_attributes(raw).values()),
        parent.get("name") if parent else "",
        parent_raw.get("slug"),
        " ".join(_categories(parent_raw)),
        " ".join(_attributes(parent_raw).values()),
    ]
    return " ".join(_normal(value) for value in values if _text(value))


def _lookup_live_entity(woo_index: Any, kind: str, woo_id: str, parent_id: str = "") -> dict[str, Any] | None:
    if kind == "product":
        return woo_index.products_by_id.get(woo_id)
    if kind == "variation":
        entity = woo_index.variations_by_id.get(woo_id)
        if entity is not None and _text(entity.get("parent_woo_id")) == parent_id:
            return entity
    return None


def approved_historical_links(graph: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Expose only effective approved graph links, never superseded fields."""
    woo_nodes = {
        _text(node.get("node_id")): dict(node)
        for node in graph.get("woo_nodes") or []
        if isinstance(node, Mapping)
    }
    evidence_by_item: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for raw_edge in graph.get("composition_edges") or []:
        edge = dict(raw_edge)
        item_id = _text(edge.get("physical_item_id") or edge.get("component_item_id"))
        if item_id:
            evidence_by_item[item_id].append((
                _text(edge.get("new_edge_status") or edge.get("edge_status")),
                _text(edge.get("new_resolution_status") or edge.get("resolution_status")),
            ))
    links: dict[str, dict[str, str]] = {}
    for raw in graph.get("physical_nodes") or []:
        node = dict(raw)
        item_id = _text(node.get("canonical_item_id") or node.get("item_id"))
        woo = woo_nodes.get(_text(node.get("woo_node_id")))
        if not item_id or woo is None or _text(node.get("map_status")) != "MAPPED_EXACT":
            continue
        effective_edges = evidence_by_item.get(item_id, [])
        links[item_id] = {
            "woo_id": _text(woo.get("woo_id")),
            "woo_parent_id": _text(woo.get("parent_woo_id")),
            "woo_item_kind": _text(woo.get("item_kind")),
            "woo_sku": _text(woo.get("sku")),
            "map_status": _text(node.get("map_status")),
            "resolution_confidence": _text(node.get("resolution_confidence")) or "HIGH",
            "effective_edge_status": " | ".join(sorted({status for status, _ in effective_edges if status})),
            "effective_resolution_status": " | ".join(sorted({status for _, status in effective_edges if status})),
        }
    return links


@dataclass(frozen=True)
class WooCandidate:
    item_id: str
    code: str
    woo_id: str
    parent_woo_id: str
    kind: str
    woo_sku: str
    woo_name: str
    evidence: str
    model_evidence: str
    size_evidence: str
    variant_evidence: str
    contradictions: str
    safe_skuless: bool

    def as_row(self) -> dict[str, str]:
        return {
            "item_id": self.item_id,
            "codigo": self.code,
            "candidate_woo_id": self.woo_id,
            "candidate_parent_woo_id": self.parent_woo_id,
            "candidate_kind": self.kind,
            "candidate_woo_sku": self.woo_sku,
            "candidate_woo_name": self.woo_name,
            "sku_evidence": self.evidence,
            "model_evidence": self.model_evidence,
            "size_evidence": self.size_evidence,
            "variant_evidence": self.variant_evidence,
            "contradictions": self.contradictions,
            "sku_less_safe_signature": "YES" if self.safe_skuless else "NO",
        }


def _physical_code(row: Mapping[str, Any]) -> str:
    return _text(row.get("hub_item_code") or row.get("heca_reference"))


def _candidate_from_entity(row: Mapping[str, Any], entity: Mapping[str, Any], *, evidence: str, parent: Mapping[str, Any] | None = None) -> WooCandidate:
    code = _physical_code(row)
    item_id = _text(row.get("item_id"))
    group = _normal(row.get("filter_group") or row.get("brand"))
    size_value = _text(row.get("filter_size") or row.get("size"))
    size = _normal(size_value)
    gama = _normal(row.get("filter_gama") or row.get("catalog_range"))
    haystack = _entity_haystack(entity, parent)
    model_match = bool(group) and all(token in _tokens(haystack) for token in _tokens(group))
    requested_dimensions = _dimension_keys(size_value)
    observed_dimensions = _entity_dimension_keys(entity, parent)
    size_match = bool(size) and bool(requested_dimensions) and requested_dimensions.issubset(observed_dimensions)
    variant_match = not gama or all(token in _tokens(haystack) for token in _tokens(gama))
    contradictions: list[str] = []
    if group and not model_match:
        contradictions.append("MODEL_NOT_EVIDENCED")
    if size and not size_match:
        contradictions.append("SIZE_NOT_EVIDENCED")
    if gama and not variant_match:
        contradictions.append("VARIANT_NOT_EVIDENCED")
    return WooCandidate(
        item_id=item_id,
        code=code,
        woo_id=_text(entity.get("woo_id")),
        parent_woo_id=_text(entity.get("parent_woo_id")),
        kind=_text(entity.get("woo_item_kind")),
        woo_sku=_text(entity.get("woo_sku")),
        woo_name=_text(entity.get("name")),
        evidence=evidence,
        model_evidence="MATCH" if model_match else "NOT_PROVEN",
        size_evidence="MATCH" if size_match else "NOT_PROVEN",
        variant_evidence="MATCH" if variant_match else "NOT_PROVEN",
        contradictions=" | ".join(contradictions),
        safe_skuless=bool(
            _text(entity.get("woo_item_kind")) == "variation"
            and not _text(entity.get("woo_sku"))
            and group and size and model_match and size_match and variant_match and not contradictions
        ),
    )


def _skuless_variation_candidates(row: Mapping[str, Any], woo_index: Any) -> list[WooCandidate]:
    candidates: list[WooCandidate] = []
    for parent_id, variations in woo_index.variations_by_parent.items():
        parent = woo_index.products_by_id.get(parent_id)
        if parent is None:
            continue
        for variation in variations:
            if _text(variation.get("woo_sku")):
                continue
            candidate = _candidate_from_entity(row, variation, evidence="SKU_LESS_VARIATION_ATTRIBUTE_CANDIDATE", parent=parent)
            # Named tokens remain a research lead only. Keep candidates with at
            # least model or size evidence; no partial candidate can be safe.
            if candidate.model_evidence == "MATCH" or candidate.size_evidence == "MATCH":
                candidates.append(candidate)
    return candidates


def _named_candidates(row: Mapping[str, Any], woo_index: Any) -> list[WooCandidate]:
    useful = _tokens(row.get("filter_group") or row.get("brand") or row.get("name"))
    useful -= {"futon", "funda", "cama", "tatami", "natural", "cm", "un"}
    if not useful:
        return []
    candidates: list[WooCandidate] = []
    entities = list(woo_index.products_by_id.values()) + list(woo_index.variations_by_id.values())
    for entity in entities:
        parent = woo_index.products_by_id.get(_text(entity.get("parent_woo_id")))
        overlap = useful.intersection(_tokens(_entity_haystack(entity, parent)))
        if len(overlap) >= min(2, len(useful)):
            candidates.append(_candidate_from_entity(row, entity, evidence="NAME_TOKEN_RESEARCH_ONLY", parent=parent))
    return candidates


def _dedupe(candidates: Iterable[WooCandidate]) -> list[WooCandidate]:
    seen: set[tuple[str, str, str]] = set()
    result: list[WooCandidate] = []
    for candidate in candidates:
        key = (candidate.kind, candidate.parent_woo_id, candidate.woo_id)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _special_check(row: Mapping[str, Any]) -> str:
    family = _normal(row.get("filter_family") or row.get("family"))
    group = _text(row.get("filter_group") or row.get("brand"))
    if _normal(group) == "macao" and _physical_code(row) == "0402014":
        return "CAMA_MACAO_180X200_NATURAL_MANDATORY"
    if "funda" in family:
        return "FUNDA_PARENT_SIZE_COLOR_REQUIRED"
    if "futon" in family:
        return "FUTON_CONSTRUCTION_SIZE_GAMA_REQUIRED"
    if "cama" in family:
        return "CAMA_MODEL_SIZE_FINISH_REQUIRED"
    if "tatami" in family:
        return "TATAMI_DIRECT_PLEGABLE_SUPPORT_PACK_DISTINCTION"
    if "sofa" in family:
        return "SOFA_CAMA_MODEL_SIZE_FINISH_REQUIRED"
    if "complement" in family:
        return "COMPLEMENT_INDIVIDUAL_IDENTITY_REQUIRED"
    return "GENERAL_EXACT_IDENTITY_REQUIRED"


def reconcile_master(
    physical_rows: Iterable[Mapping[str, Any]],
    *,
    woo_index: Any,
    graph: Mapping[str, Any],
) -> dict[str, Any]:
    """Return 254 final classifications without mutating Woo or Supabase."""
    historical = approved_historical_links(graph)
    master: list[dict[str, str]] = []
    research: list[dict[str, str]] = []
    for raw in physical_rows:
        row = dict(raw)
        item_id = _text(row.get("item_id"))
        code = _physical_code(row)
        result = "NO_DIRECT_WOO_ENTITY_CANDIDATE"
        reason = "No hay entidad Woo directa con evidencia exacta suficiente."
        candidates: list[WooCandidate] = []
        historical_link = historical.get(item_id)
        if not item_id or not code:
            result, reason = "READ_ERROR", "La identidad física canónica no contiene item_id o código literal."
        elif _bool(row.get("is_pack")) or _text(row.get("item_record_type")).lower() in {"alias", "component_placeholder"}:
            reason = "Registro excluido de relación Woo directa por su tipo físico no operable."
        else:
            direct = _dedupe(
                _candidate_from_entity(row, entity, evidence="EXACT_LITERAL_SKU")
                for entity in woo_index.woo_entities_by_exact_literal_sku.get(code, ())
            )
            if len(direct) == 1:
                candidate = direct[0]
                candidates = direct
                result = "SAFE_DIRECT_PRODUCT" if candidate.kind == "product" else "SAFE_DIRECT_VARIATION"
                reason = "SKU literal exacto único verificado contra Woo live."
            elif len(direct) > 1:
                candidates = direct
                result, reason = "CONFLICT", "El SKU literal exacto apunta a más de una entidad Woo."
            elif historical_link:
                entity = _lookup_live_entity(
                    woo_index,
                    historical_link["woo_item_kind"],
                    historical_link["woo_id"],
                    historical_link["woo_parent_id"],
                )
                if entity is not None and _text(entity.get("woo_sku")) == historical_link["woo_sku"]:
                    candidates = [_candidate_from_entity(row, entity, evidence="APPROVED_HISTORICAL_EFFECTIVE_EDGE")]
                    result, reason = "SAFE_HISTORICAL_LINK_RECOVERED", "Enlace histórico aprobado y entidad Woo literal verificados."
                else:
                    result, reason = "CONFLICT", "El enlace histórico aprobado no coincide con el objeto Woo live."
            else:
                skuless = _skuless_variation_candidates(row, woo_index)
                # Named similarities are research leads only. Once an actual
                # SKU-less variation signature exists, do not add its parent
                # or unrelated name matches to the exact signature decision.
                candidates = _dedupe(skuless if skuless else _named_candidates(row, woo_index))
                safe_skuless = [candidate for candidate in candidates if candidate.safe_skuless]
                if len(safe_skuless) == 1 and len(candidates) == 1:
                    candidate = safe_skuless[0]
                    result, reason = "SAFE_DIRECT_VARIATION", "Variación sin SKU única con firma modelo/tamaño/variante completa."
                elif len(candidates) == 1:
                    result, reason = "REVIEW_USER_SINGLE_CANDIDATE", "Existe un candidato Woo, pero la evidencia no autoriza promoción automática."
                elif len(candidates) > 1:
                    result, reason = "REVIEW_USER_MULTIPLE_CANDIDATES", "Existen varios candidatos Woo sin desambiguación exacta."

        for candidate in candidates or [None]:
            evidence_row = candidate.as_row() if candidate else {
                "item_id": item_id, "codigo": code, "candidate_woo_id": "", "candidate_parent_woo_id": "", "candidate_kind": "", "candidate_woo_sku": "", "candidate_woo_name": "", "sku_evidence": "NO_DIRECT_CANDIDATE", "model_evidence": "", "size_evidence": "", "variant_evidence": "", "contradictions": "", "sku_less_safe_signature": "NO",
            }
            research.append({
                **evidence_row,
                "physical_name": _text(row.get("name")),
                "physical_family": _text(row.get("filter_family") or row.get("family")),
                "physical_group": _text(row.get("filter_group") or row.get("brand")),
                "physical_size": _text(row.get("filter_size") or row.get("size")),
                "physical_gama": _text(row.get("filter_gama") or row.get("catalog_range")),
                "special_check": _special_check(row),
                "preliminary_result": result,
                "resolution_reason": reason,
            })
        selected = candidates[0] if len(candidates) == 1 else None
        master.append({
            "item_id": item_id,
            "codigo": code,
            "name": _text(row.get("name")),
            "family": _text(row.get("filter_family") or row.get("family")),
            "filter_group": _text(row.get("filter_group") or row.get("brand")),
            "filter_size": _text(row.get("filter_size") or row.get("size")),
            "filter_gama": _text(row.get("filter_gama") or row.get("catalog_range")),
            "item_record_type": _text(row.get("item_record_type")),
            "is_pack": _text(row.get("is_pack")),
            "final_result": result,
            "resolution_reason": reason,
            "special_check": _special_check(row),
            "woo_id": selected.woo_id if selected else "",
            "woo_parent_id": selected.parent_woo_id if selected else "",
            "woo_item_kind": selected.kind if selected else "",
            "woo_sku": selected.woo_sku if selected else "",
            "woo_name": selected.woo_name if selected else "",
            "historical_effective_edge_status": (historical_link or {}).get("effective_edge_status", ""),
            "historical_effective_resolution_status": (historical_link or {}).get("effective_resolution_status", ""),
            "candidate_count": str(len(candidates)),
            "apply_status": "PLAN_ONLY_NO_APPLY" if result in SAFE_RESULTS else "NO_APPLY",
        })

    claims: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in master:
        if row["final_result"] in SAFE_RESULTS and row["woo_id"]:
            claims[(row["woo_item_kind"], row["woo_parent_id"], row["woo_id"])].append(row)
    for target, rows in claims.items():
        if len(rows) > 1:
            codes = ", ".join(sorted(row["codigo"] for row in rows))
            for row in rows:
                row["final_result"] = "CONFLICT"
                row["resolution_reason"] = f"La entidad Woo {target[0]}:{target[1]}:{target[2]} está reclamada por {codes}."
                row["apply_status"] = "NO_APPLY"

    counts = Counter(row["final_result"] for row in master)
    safe_plan = [row for row in master if row["final_result"] in SAFE_RESULTS]
    review = [row for row in master if row["final_result"] in REVIEW_RESULTS]
    return {
        "master": master,
        "research": research,
        "safe_plan": safe_plan,
        "review": review,
        "summary": {
            "physical_total": len(master),
            "final_result_counts": dict(sorted(counts.items())),
            "safe_total": len(safe_plan),
            "review_total": len(review),
            "no_direct_candidate_total": counts["NO_DIRECT_WOO_ENTITY_CANDIDATE"],
            "conflict_total": counts["CONFLICT"],
            "woo_index_products": int(woo_index.counts.get("products") or 0),
            "woo_index_variations": int(woo_index.counts.get("variations") or 0),
            "writes": {"woo": 0, "supabase": 0, "sql": 0},
        },
    }

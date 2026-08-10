"""Strict residual Woo candidate engine for WOO-MAP-001A.7.1.

The 001A.7 SAFE baseline is immutable here.  This module only re-evaluates
the 70 residual physical identities through mandatory family, model, kind,
size, and variant gates.  It is a read-only planning boundary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from futonhub.services.woo_map_001a_7_reconciliation import (
    FINAL_STATUSES,
    LEADING_ZERO_DUO_CODES,
    TATAMI_PORTABLE_CODES,
    _attributes_text,
    _categories_text,
    _dimensions,
    _entity_fields,
    _entity_fingerprint,
    _historical_signals,
    _normal,
    _parent,
    _physical_fingerprint,
    _physical_item_id,
    _physical_sku,
    _text,
    _tokens,
)


FROZEN_STATUSES = frozenset({
    "ACTIVE_DIRECT_WOO_VERIFIED",
    "ACTIVE_DIRECT_WOO_SAFE_PLAN",
    "RETIRED_CONFIRMED_BY_USER",
    "NO_DIRECT_WOO_ENTITY_SUPPORTED",
})
RESIDUAL_STATUSES = frozenset({
    "REVIEW_USER_SINGLE_STRONG_CANDIDATE",
    "REVIEW_USER_MULTIPLE_STRONG_CANDIDATES",
    "REVIEW_USER_BUSINESS_EQUIVALENCE",
    "REVIEW_USER_RETIREMENT",
    "ACTIVE_HIDDEN_WOO_ENTITY",
    "PHYSICAL_IDENTITY_REVIEW",
    "WOO_CATALOG_INCONSISTENCY",
    "WOO_ENTITY_MISSING",
    "NO_DIRECT_WOO_ENTITY_SUPPORTED",
    "READ_ERROR",
})

_NON_SEMANTIC_VARIANTS = frozenset({"", "no gama", "sin gama", "na", "n a", "none"})
_CONTROLLED_VARIANT_EQUIVALENTS = {
    "amarilla": "AMARILLO", "amarillo": "AMARILLO",
    "negra": "NEGRO", "negro": "NEGRO",
    "roja": "ROJO", "rojo": "ROJO",
    "cruda": "CRUDO", "crudo": "CRUDO",
    "crudo sin barniz": "CRUDO_SIN_BARNIZ",
    "verde oscuro": "VERDE_OSCURO", "verde": "VERDE",
    "azul marino": "AZUL_MARINO", "azul": "AZUL",
    "gris jaspeado": "GRIS_JASPEADO", "gris": "GRIS",
    "beige jaspeado": "BEIGE_JASPEADO", "beige": "BEIGE",
    "violeta": "VIOLETA", "morado": "MORADO",
    "natural": "NATURAL", "granate": "GRANATE", "naranja": "NARANJA", "marron": "MARRON",
}
_CONTROLLED_VARIANT_PHRASES = tuple(sorted(_CONTROLLED_VARIANT_EQUIVALENTS, key=lambda value: (-len(value), value)))


@dataclass(frozen=True)
class EffectivePhysicalVariant:
    value: str
    source: str
    canonical: str


def _semantic_variant(value: Any) -> str:
    text = _text(value)
    return "" if _normal(text) in _NON_SEMANTIC_VARIANTS else text


def canonical_variant(value: Any) -> str:
    """Normalize only documented linguistic equivalents; unknown values stay literal."""
    normalized = _normal(value)
    if normalized in _NON_SEMANTIC_VARIANTS:
        return ""
    return _CONTROLLED_VARIANT_EQUIVALENTS.get(normalized, f"LITERAL:{normalized}")


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _controlled_variants_in_text(value: Any) -> set[str]:
    normalized = _normal(value)
    selected: list[str] = []
    for phrase in _CONTROLLED_VARIANT_PHRASES:
        if not _contains_phrase(normalized, phrase):
            continue
        # The longer controlled phrase owns its shorter component: Verde
        # oscuro is not evidence for Verde, nor Azul marino for Azul.
        if any(_contains_phrase(existing, phrase) for existing in selected):
            continue
        selected.append(phrase)
    return {_CONTROLLED_VARIANT_EQUIVALENTS[phrase] for phrase in selected}


def _explicit_name_variant(value: Any) -> str:
    variants = _controlled_variants_in_text(value)
    return next(iter(variants)) if len(variants) == 1 else ""


def resolve_effective_physical_variant(row: Mapping[str, Any]) -> EffectivePhysicalVariant:
    """Resolve the required physical variant without treating placeholders as evidence."""
    filter_gama = _semantic_variant(row.get("filter_gama"))
    if filter_gama:
        return EffectivePhysicalVariant(filter_gama, "FILTER_GAMA", canonical_variant(filter_gama))
    catalog_range = _semantic_variant(row.get("catalog_range"))
    if catalog_range:
        return EffectivePhysicalVariant(catalog_range, "CATALOG_RANGE", canonical_variant(catalog_range))
    name_variant = _explicit_name_variant(row.get("canonical_name") or row.get("name"))
    if name_variant:
        return EffectivePhysicalVariant(name_variant, "CANONICAL_NAME_EXPLICIT", name_variant)
    return EffectivePhysicalVariant("", "NOT_REQUIRED", "")


def _candidate_text(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> str:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    values = (
        entity.get("name"), entity.get("woo_sku"), _attributes_text(raw), _categories_text(raw),
        (parent or {}).get("name"), _attributes_text(parent_raw), _categories_text(parent_raw),
    )
    return _normal(" ".join(_text(value) for value in values if _text(value)))


def _family_key(row: Mapping[str, Any]) -> str:
    family = _normal(row.get("filter_family") or row.get("family"))
    if "funda" in family:
        return "COVER"
    if "sofa" in family:
        return "SOFA_BED"
    if "cama" in family or "bases" in family:
        return "BED"
    if "tatami" in family:
        return "TATAMI"
    if "futon" in family:
        return "FUTON"
    if "complement" in family:
        return "ACCESSORY"
    return "UNKNOWN"


def _model_spec(row: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    code = _physical_sku(row)
    group = _normal(row.get("filter_group") or row.get("brand"))
    name = _normal(row.get("name"))
    family = _family_key(row)
    if code in TATAMI_PORTABLE_CODES:
        return "Tatami plegable + futon portatil", ("tatami", "plegable", "futon", "portatil")
    if code in {"0201006", "0201007"}:
        return "Tatami support", ("tatami", "support")
    if code == "0402014":
        return "Cama Macao", ("cama", "macao")
    if "okinawa" in name and "mesita" in name:
        return "Mesita Okinawa", ("mesita", "okinawa")
    if family == "SOFA_BED" and "luna" in name:
        return "Sofa cama Luna", ("sofa", "cama", "luna")
    if family == "BED" and "eko bed" in group:
        return "Cama Eko-bed", ("eko", "bed")
    if family == "BED" and "yoko bed" in group:
        return "Cama Yoko-bed", ("yoko", "bed")
    if family == "COVER" and "funda futon" in group:
        return "Funda para futon", ("funda", "futon")
    if family == "COVER" and "funda almohada" in group:
        return "Funda de almohada o cojin", ("funda",)
    if family == "FUTON" and group == "algodon":
        return "Futon de algodon", ("futon", "algodon")
    if family == "FUTON" and "algodon" in group and "latex" in group:
        latex = "4" if "1" in group else "8" if "2" in group else "latex"
        return "Futon algodon con latex", ("futon", "algodon", "latex", latex)
    if family == "FUTON" and group == "lana":
        return "Futon de lana", ("futon", "lana")
    if family == "FUTON" and group == "premium":
        return "Futon Premium", ("futon", "premium")
    if family == "FUTON" and group == "portatil":
        return "Futon portatil", ("futon", "portatil")
    if family == "FUTON" and "duo latex" in group:
        return "Futon Duo Latex", ("futon", "duo", "latex")
    if group:
        return _text(row.get("filter_group") or row.get("brand")), tuple(group.split())
    return "", ()


def _family_gate(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> str:
    text = _candidate_text(entity, parent)
    family = _family_key(row)
    if family == "COVER":
        return "PASS" if "funda" in text else "FAIL"
    if family == "BED":
        if any(token in text for token in ("funda", "sofa", "tatami", "futon")):
            return "FAIL"
        spec_name, spec = _model_spec(row)
        return "PASS" if ("cama" in text or any(token in text for token in spec)) else "FAIL"
    if family == "SOFA_BED":
        return "PASS" if "sofa" in text and "cama" in text else "FAIL"
    if family == "TATAMI":
        return "PASS" if "tatami" in text and "sofa" not in text else "FAIL"
    if family == "FUTON":
        return "PASS" if "futon" in text and not any(token in text for token in ("funda", "sofa", "tatami")) else "FAIL"
    if family == "ACCESSORY":
        return "PASS" if "mesita" in text else "FAIL"
    return "INSUFFICIENT"


def _model_gate(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None, family_gate: str) -> tuple[str, str]:
    if family_gate != "PASS":
        return "MODEL_GATE_FAIL", "MODEL_FAMILY_MISMATCH"
    label, required = _model_spec(row)
    if not required:
        return "MODEL_GATE_INSUFFICIENT", "MODEL_FAMILY_ONLY"
    text_tokens = _tokens(_candidate_text(entity, parent))
    if all(token in text_tokens for token in required):
        return "MODEL_GATE_PASS", ""
    # Family-compliant but no exact model is explicitly not enough.
    return "MODEL_GATE_INSUFFICIENT", "MODEL_FAMILY_ONLY"


def _kind_gate(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[str, str]:
    raw = dict(entity.get("raw") or {})
    kind = _text(entity.get("woo_item_kind"))
    raw_type = _normal(raw.get("type"))
    code = _physical_sku(row)
    if kind == "product" and raw_type.startswith("variable"):
        return "FAIL", "CONTEXT_PARENT"
    if kind not in {"product", "variation"}:
        return "FAIL", "WRONG_PRODUCT_KIND"
    sku = _text(entity.get("woo_sku"))
    combined = _candidate_text(entity, parent)
    pack = ("pack" in combined or "kit" in combined or "|" in sku) and code not in TATAMI_PORTABLE_CODES
    if pack:
        return "FAIL", "PACK_INSTEAD_OF_DIRECT"
    return "PASS", ""


def _entity_dimensions(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[set[str], str]:
    raw = dict(entity.get("raw") or {})
    values = (entity.get("name"), _attributes_text(raw), raw.get("description"))
    observed: set[str] = set()
    for value in values:
        observed.update(_dimensions(value))
    if observed:
        return observed, "ENTITY_DIMENSION"
    if _physical_sku(row) in TATAMI_PORTABLE_CODES and parent is not None:
        parent_raw = dict(parent.get("raw") or {})
        for value in (parent_raw.get("description"), parent_raw.get("short_description")):
            observed.update(_dimensions(value))
        if observed:
            return observed, "FIXED_PARENT_CONTEXT_DIMENSION"
    return observed, "INSUFFICIENT_ENTITY_DIMENSION"


def _size_gate(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[str, str]:
    required = _dimensions(row.get("filter_size") or row.get("size"))
    if not required:
        return "NOT_REQUIRED", ""
    observed, source = _entity_dimensions(row, entity, parent)
    if not observed:
        return "INSUFFICIENT", source
    return ("PASS", source) if required.issubset(observed) else ("FAIL", source)


def _candidate_variant(entity: Mapping[str, Any], required: EffectivePhysicalVariant) -> str:
    raw = dict(entity.get("raw") or {})
    values = (entity.get("name"), entity.get("woo_sku"), _attributes_text(raw))
    text = _normal(" ".join(_text(value) for value in values if _text(value)))
    variants = _controlled_variants_in_text(text)
    if required.canonical.startswith("LITERAL:"):
        literal = required.canonical.removeprefix("LITERAL:")
        if _contains_phrase(text, literal):
            variants.add(required.canonical)
    return " | ".join(sorted(variants))


def _variant_gate(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[str, EffectivePhysicalVariant, str]:
    del parent  # Parent variation option lists are never direct variant evidence.
    required = resolve_effective_physical_variant(row)
    if required.source == "NOT_REQUIRED":
        return "NOT_REQUIRED", required, ""
    candidate_variant = _candidate_variant(entity, required)
    candidates = set(candidate_variant.split(" | ")) if candidate_variant else set()
    return ("PASS" if required.canonical in candidates else "FAIL"), required, candidate_variant


@dataclass(frozen=True)
class CandidateAssessment:
    entity: Mapping[str, Any]
    parent: Mapping[str, Any] | None
    family_gate: str
    model_gate: str
    model_note: str
    kind_gate: str
    kind_note: str
    size_gate: str
    size_source: str
    variant_gate: str
    effective_variant: str
    effective_variant_source: str
    candidate_variant: str
    historical_signals: tuple[str, ...]
    claimed_by: tuple[str, ...]

    @property
    def identity_gates_pass(self) -> bool:
        return (
            self.family_gate == "PASS" and self.model_gate == "MODEL_GATE_PASS" and self.kind_gate == "PASS"
            and self.size_gate in {"PASS", "NOT_REQUIRED"} and self.variant_gate in {"PASS", "NOT_REQUIRED"}
        )

    @property
    def business_equivalence_candidate(self) -> bool:
        return (
            self.family_gate == "PASS" and self.model_gate == "MODEL_GATE_PASS" and self.kind_gate == "PASS"
            and self.size_gate in {"PASS", "NOT_REQUIRED"} and self.variant_gate == "FAIL"
        )

    @property
    def rank(self) -> tuple[int, int, int, str]:
        return (
            int(self.identity_gates_pass),
            int(self.business_equivalence_candidate),
            -len(self.historical_signals) - int(bool(self.claimed_by)),
            _text(self.entity.get("woo_id")),
        )


def evaluate_candidate(row: Mapping[str, Any], entity: Mapping[str, Any], *, woo_index: Any, claims: Mapping[tuple[str, str, str], set[str]]) -> CandidateAssessment:
    parent = _parent(entity, woo_index)
    family_gate = _family_gate(row, entity, parent)
    model_gate, model_note = _model_gate(row, entity, parent, family_gate)
    kind_gate, kind_note = _kind_gate(row, entity, parent)
    size_gate, size_source = _size_gate(row, entity, parent)
    variant_gate, effective_variant, candidate_variant = _variant_gate(row, entity, parent)
    target = (_text(entity.get("woo_item_kind")), _text(entity.get("parent_woo_id")), _text(entity.get("woo_id")))
    claimed = tuple(sorted(claims.get(target, set()) - {_physical_sku(row)}))
    return CandidateAssessment(
        entity=entity, parent=parent, family_gate=family_gate, model_gate=model_gate, model_note=model_note,
        kind_gate=kind_gate, kind_note=kind_note, size_gate=size_gate, size_source=size_source,
        variant_gate=variant_gate, effective_variant=effective_variant.value,
        effective_variant_source=effective_variant.source, candidate_variant=candidate_variant,
        historical_signals=_historical_signals(entity, parent), claimed_by=claimed,
    )


def _audit_relevant(row: Mapping[str, Any], assessment: CandidateAssessment) -> bool:
    code = _physical_sku(row)
    entity = assessment.entity
    if _text(entity.get("woo_sku")) == code:
        return True
    if assessment.family_gate == "PASS" or assessment.model_gate == "MODEL_GATE_PASS":
        return True
    if assessment.size_gate == "PASS" or assessment.variant_gate == "PASS":
        return True
    return bool(set(_model_spec(row)[1]).intersection(_tokens(_candidate_text(entity, assessment.parent))))


def _all_assessments(row: Mapping[str, Any], *, woo_index: Any, claims: Mapping[tuple[str, str, str], set[str]]) -> list[CandidateAssessment]:
    items = list(woo_index.products_by_id.values()) + list(woo_index.variations_by_id.values())
    assessments = [evaluate_candidate(row, entity, woo_index=woo_index, claims=claims) for entity in items]
    return sorted((item for item in assessments if _audit_relevant(row, item)), key=lambda item: item.rank, reverse=True)


def _missing_evidence(assessment: CandidateAssessment) -> list[str]:
    missing: list[str] = []
    if assessment.family_gate != "PASS":
        missing.append("FAMILY_GATE")
    if assessment.model_gate != "MODEL_GATE_PASS":
        missing.append("MODEL_EVIDENCE")
    if assessment.kind_gate != "PASS":
        missing.append("KIND_GATE")
    if assessment.size_gate not in {"PASS", "NOT_REQUIRED"}:
        missing.append("ENTITY_SIZE_EVIDENCE")
    if assessment.variant_gate not in {"PASS", "NOT_REQUIRED"}:
        missing.append("VARIANT_EVIDENCE")
    return missing


def _rejection_reason(assessment: CandidateAssessment, *, code: str, allow_business_equivalence: bool = False) -> str:
    if code in LEADING_ZERO_DUO_CODES:
        return "CONFLICTING_HISTORICAL_EVIDENCE: leading-zero identity requires manual evidence."
    if assessment.family_gate != "PASS":
        return "FAMILY_GATE_FAIL"
    if assessment.model_gate == "MODEL_GATE_FAIL":
        return "MODEL_GATE_FAIL"
    if assessment.model_gate == "MODEL_GATE_INSUFFICIENT":
        return assessment.model_note or "MODEL_GATE_INSUFFICIENT"
    if assessment.kind_gate != "PASS":
        return assessment.kind_note or "KIND_GATE_FAIL"
    if assessment.size_gate != "PASS" and assessment.size_gate != "NOT_REQUIRED":
        return "SIZE_GATE_FAIL"
    if assessment.variant_gate != "PASS" and assessment.variant_gate != "NOT_REQUIRED":
        return "REQUIRES_BUSINESS_EQUIVALENCE" if allow_business_equivalence else "VARIANT_GATE_FAIL"
    if assessment.claimed_by:
        return f"CONFLICTING_HISTORICAL_EVIDENCE: claimed by {','.join(assessment.claimed_by)}"
    if assessment.historical_signals:
        return "HISTORICAL_OR_HIDDEN_EVIDENCE"
    return ""


def _audit_row(row: Mapping[str, Any], assessment: CandidateAssessment, *, accepted: bool, allow_business_equivalence: bool = False) -> dict[str, str]:
    entity = assessment.entity
    parent = assessment.parent
    raw = dict(entity.get("raw") or {})
    missing = _missing_evidence(assessment)
    reason = _rejection_reason(assessment, code=_physical_sku(row), allow_business_equivalence=allow_business_equivalence)
    return {
        "physical_item_id": _physical_item_id(row), "physical_sku": _physical_sku(row), "physical_name": _text(row.get("name")),
        "candidate_woo_id": _text(entity.get("woo_id")), "candidate_parent_id": _text(entity.get("parent_woo_id")),
        "candidate_kind": _text(entity.get("woo_item_kind")), "candidate_name": _text(entity.get("name")),
        "candidate_parent_name": _text((parent or {}).get("name")), "candidate_sku": _text(entity.get("woo_sku")),
        "candidate_status": _text(raw.get("status") or entity.get("status")),
        "family_gate": assessment.family_gate, "model_gate": assessment.model_gate, "model_note": assessment.model_note,
        "kind_gate": assessment.kind_gate, "kind_note": assessment.kind_note,
        "size_gate": assessment.size_gate, "size_evidence_source": assessment.size_source,
        "variant_gate": assessment.variant_gate, "effective_variant": assessment.effective_variant,
        "effective_variant_source": assessment.effective_variant_source, "candidate_variant": assessment.candidate_variant,
        "missing_required_evidence": " | ".join(missing),
        "historical_signals": " | ".join(assessment.historical_signals), "claimed_by": ", ".join(assessment.claimed_by),
        "accepted_for_human_review": "YES" if accepted else "NO", "rejection_reason": reason,
    }


def _review_row(master: Mapping[str, str], assessment: CandidateAssessment | None, rank: int, decision_required: str) -> dict[str, str]:
    if assessment is None:
        return {
            "physical_item_id": master["physical_item_id"], "physical_sku": master["physical_sku"],
            "canonical_name": master["canonical_name"], "woo_resolution_status": master["woo_resolution_status"],
            "candidate_rank": "0", "candidate_woo_id": "", "candidate_parent_id": "", "candidate_kind": "",
            "candidate_sku": "", "candidate_name": "", "candidate_parent_name": "", "candidate_status": "",
            "evidence_for": "", "evidence_against": "", "decision_required": decision_required,
        }
    raw = dict(assessment.entity.get("raw") or {})
    positive = ["FAMILY_GATE_PASS", "MODEL_GATE_PASS", "KIND_GATE_PASS"]
    if assessment.size_gate == "PASS":
        positive.append("SIZE_EXACT")
    if assessment.variant_gate == "PASS":
        positive.append("VARIANT_EXACT")
    negative: list[str] = []
    if assessment.variant_gate == "FAIL":
        negative.append("VARIANT_DIFFERENCE_REQUIRES_BUSINESS_DECISION")
    negative.extend(assessment.historical_signals)
    if assessment.claimed_by:
        negative.append(f"CLAIMED_BY={','.join(assessment.claimed_by)}")
    return {
        "physical_item_id": master["physical_item_id"], "physical_sku": master["physical_sku"],
        "canonical_name": master["canonical_name"], "woo_resolution_status": master["woo_resolution_status"],
        "candidate_rank": str(rank), "candidate_woo_id": _text(assessment.entity.get("woo_id")),
        "candidate_parent_id": _text(assessment.entity.get("parent_woo_id")), "candidate_kind": _text(assessment.entity.get("woo_item_kind")),
        "candidate_sku": _text(assessment.entity.get("woo_sku")), "candidate_name": _text(assessment.entity.get("name")),
        "candidate_parent_name": _text((assessment.parent or {}).get("name")),
        "candidate_status": _text(raw.get("status") or assessment.entity.get("status")),
        "evidence_for": " | ".join(positive), "evidence_against": " | ".join(negative),
        "decision_required": decision_required,
    }


def _residual_master(
    previous: Mapping[str, str], row: Mapping[str, Any], *, status: str, entity: Mapping[str, Any] | None,
    reason: str, resolution_source: str, direct: bool = False,
) -> dict[str, str]:
    result = dict(previous)
    result.update({
        "physical_item_id": _physical_item_id(row), "physical_sku": _physical_sku(row), "canonical_name": _text(row.get("name")),
        "family": _text(row.get("filter_family") or row.get("family")), "group": _text(row.get("filter_group") or row.get("brand")),
        "size": _text(row.get("filter_size") or row.get("size")), "gama": _text(row.get("filter_gama") or row.get("catalog_range")),
        "commercial_status": "ACTIVE_OR_UNCONFIRMED", "woo_resolution_status": status,
        "direct_entity": "YES" if direct else "NO", "component_only": "NO", "affected_combination_count": "0",
        "resolution_source": resolution_source, "resolution_reason": reason,
        "safe_to_persist": "NO", "requires_user_review": "YES", "price_change_eligible": "NO",
        "historical_woo_id": "", "historical_reason": "", "physical_identity_sha256": _physical_fingerprint(row),
        "woo_identity_sha256": _entity_fingerprint(entity) if entity is not None else "",
    })
    result.update(_entity_fields(entity))
    return result


def _claims_from_master(master_rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str, str], set[str]]:
    claims: dict[tuple[str, str, str], set[str]] = {}
    for row in master_rows:
        if _text(row.get("safe_to_persist")) != "YES":
            continue
        key = (_text(row.get("woo_kind")), _text(row.get("woo_parent_id")), _text(row.get("woo_id")))
        claims.setdefault(key, set()).add(_text(row.get("physical_sku")))
    return claims


def reconcile_residual_candidates(
    physical_rows: Iterable[Mapping[str, Any]], *, previous_master_rows: Iterable[Mapping[str, Any]], woo_index: Any,
    resolution_source: str = "WOO_MAP_001A_7_1_STRICT_CANDIDATE_ENGINE",
) -> dict[str, Any]:
    """Reclassify only the 70 residuals; frozen 001A.7 rows are copied unchanged."""
    physical = {_physical_item_id(row): dict(row) for row in physical_rows}
    prior = {_text(row.get("physical_item_id")): dict(row) for row in previous_master_rows}
    if len(physical) != 254 or len(prior) != 254 or set(physical) != set(prior):
        raise RuntimeError("001A.7.1 requires matching 254-row canonical and previous master inputs.")
    frozen = [row for row in prior.values() if _text(row.get("woo_resolution_status")) in FROZEN_STATUSES]
    residual_ids = [item_id for item_id, row in prior.items() if _text(row.get("woo_resolution_status")) not in FROZEN_STATUSES]
    if len(frozen) != 184 or len(residual_ids) != 70:
        raise RuntimeError("001A.7.1 must preserve 184 frozen rows and reprocess exactly 70 residual rows.")
    claims = _claims_from_master(frozen)
    master_by_id = dict(prior)
    audit_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    display_counts: Counter[int] = Counter()

    for item_id in residual_ids:
        row = physical[item_id]
        previous = prior[item_id]
        code = _physical_sku(row)
        assessments = _all_assessments(row, woo_index=woo_index, claims=claims)
        accepted: list[CandidateAssessment] = []
        business_equivalence: list[CandidateAssessment] = []
        for assessment in assessments:
            allow_business = code == "0902005" and _text(assessment.entity.get("woo_id")) == "11838"
            is_accepted = (
                assessment.identity_gates_pass and not assessment.claimed_by
                or allow_business and assessment.business_equivalence_candidate
            )
            audit_rows.append(_audit_row(row, assessment, accepted=is_accepted, allow_business_equivalence=allow_business))
            if is_accepted:
                (business_equivalence if allow_business else accepted).append(assessment)

        selected: Mapping[str, Any] | None = None
        decision_required = "Confirm whether Woo entity is commercially valid for this physical identity."
        if code in LEADING_ZERO_DUO_CODES:
            status = "PHYSICAL_IDENTITY_REVIEW"
            reason = "Leading-zero physical SKU remains separate from 078... until historical identity evidence is supplied."
            review_candidates: list[CandidateAssessment] = []
            decision_required = "Provide historical evidence: distinct physical identity, legacy alias, or canonical duplicate."
        elif code == "0402014":
            status = "WOO_CATALOG_INCONSISTENCY"
            reason = "Cama Macao has no compatible Cama Macao entity; Base para Tatami Macao is excluded by the hard model gate."
            review_candidates = []
            decision_required = "Correct or create the Woo commercial entity for Cama Macao; do not use Base Macao."
        elif code == "0206001":
            hidden = next((candidate for candidate in accepted if _text(candidate.entity.get("woo_id")) == "4557"), None)
            if hidden is None:
                status, reason, review_candidates = "READ_ERROR", "Expected private Granate variation 4557 was not verified in the live index.", []
                decision_required = "Retry GET-only validation before any business decision."
            else:
                status = "ACTIVE_HIDDEN_WOO_ENTITY"
                selected = hidden.entity
                reason = "Woo 4557 under parent 3657 is structurally exact but private; it is not automatically retired."
                review_candidates = [hidden]
                decision_required = "Decide whether this exact private variation is commercially operable."
        elif business_equivalence:
            status = "REVIEW_USER_BUSINESS_EQUIVALENCE"
            selected = business_equivalence[0].entity
            reason = "Same Mesita Okinawa baja variation and entity dimensions; Natural versus Crudo sin barniz requires a business-equivalence decision."
            review_candidates = business_equivalence
            decision_required = "Confirm or reject Natural <-> Crudo sin barniz as a commercial filter equivalence."
        elif accepted:
            active = [candidate for candidate in accepted if not candidate.historical_signals]
            historical = [candidate for candidate in accepted if candidate.historical_signals]
            if active:
                status = "REVIEW_USER_SINGLE_STRONG_CANDIDATE" if len(active) == 1 else "REVIEW_USER_MULTIPLE_STRONG_CANDIDATES"
                review_candidates = active
                selected = active[0].entity if len(active) == 1 else None
                reason = "Strict family, model, kind, size, and variant gates passed; user confirmation is required before any relation is persisted."
            else:
                status = "REVIEW_USER_RETIREMENT"
                review_candidates = historical
                selected = historical[0].entity
                reason = "Only same-model strong Woo evidence has outlet, hidden, or non-publish signals; retirement cannot be inferred automatically."
                decision_required = "Decide whether related historical/outlet evidence means retired, retained, or still commercial."
        else:
            status = "WOO_ENTITY_MISSING"
            reason = "No Woo candidate passed the mandatory family, model, kind, size, and variant gates."
            review_candidates = []
            decision_required = "No compatible direct Woo entity was found. Confirm absence or create/correct a Woo entity in a separate approved cut."

        current = _residual_master(
            previous, row, status=status, entity=selected, reason=reason, resolution_source=resolution_source,
            direct=status == "ACTIVE_HIDDEN_WOO_ENTITY",
        )
        master_by_id[item_id] = current
        shown = review_candidates[:3]
        display_counts[len(shown)] += 1
        if shown:
            review_rows.extend(_review_row(current, candidate, rank, decision_required) for rank, candidate in enumerate(shown, start=1))
        else:
            review_rows.append(_review_row(current, None, 0, decision_required))

    master = [master_by_id[_physical_item_id(row)] for row in physical_rows]
    if len(master) != 254 or len({_text(row.get("physical_item_id")) for row in master}) != 254:
        raise RuntimeError("Strict reconciliation must retain 254 unique master rows.")
    statuses = Counter(_text(row.get("woo_resolution_status")) for row in master)
    if statuses["ACTIVE_DIRECT_WOO_VERIFIED"] != 174 or statuses["ACTIVE_DIRECT_WOO_SAFE_PLAN"] != 3:
        raise RuntimeError("The 177 SAFE rows changed during residual-only reconciliation.")
    if statuses["RETIRED_CONFIRMED_BY_USER"] != 2 or statuses["NO_DIRECT_WOO_ENTITY_SUPPORTED"] != 5:
        raise RuntimeError("Frozen retired or component-only classifications changed.")
    if any(_text(row.get("woo_resolution_status")) not in FINAL_STATUSES | RESIDUAL_STATUSES for row in master):
        raise RuntimeError("Strict reconciliation emitted an unsupported status.")
    if any(
        audit["accepted_for_human_review"] == "YES"
        and (audit["family_gate"] != "PASS" or audit["model_gate"] != "MODEL_GATE_PASS" or audit["kind_gate"] != "PASS")
        for audit in audit_rows
    ):
        raise RuntimeError("A candidate that failed a mandatory identity gate reached human review.")
    if any(sum(1 for audit in review_rows if audit["physical_item_id"] == item_id) > 3 for item_id in residual_ids):
        raise RuntimeError("Human review exceeds three candidates for a physical item.")

    rejected = Counter()
    for audit in audit_rows:
        if audit["accepted_for_human_review"] == "YES":
            continue
        if audit["family_gate"] == "FAIL":
            rejected["family"] += 1
        if audit["model_gate"] != "MODEL_GATE_PASS":
            rejected["model"] += 1
        if audit["kind_gate"] != "PASS":
            rejected["kind"] += 1
        if audit["size_gate"] not in {"PASS", "NOT_REQUIRED"}:
            rejected["size"] += 1
        if audit["variant_gate"] not in {"PASS", "NOT_REQUIRED"}:
            rejected["variant"] += 1
    return {
        "master": master,
        "candidate_audit": audit_rows,
        "residual_review": review_rows,
        "summary": {
            "residual_total": 70,
            "candidate_rows_before": len(audit_rows),
            "candidate_rows_after": sum(1 for row in audit_rows if row["accepted_for_human_review"] == "YES"),
            "physical_with_zero_candidate": display_counts[0],
            "physical_with_one_candidate": display_counts[1],
            "physical_with_two_candidates": display_counts[2],
            "physical_with_three_candidates": display_counts[3],
            "candidates_rejected_family_gate": rejected["family"],
            "candidates_rejected_model_gate": rejected["model"],
            "candidates_rejected_kind_gate": rejected["kind"],
            "candidates_rejected_size_gate": rejected["size"],
            "candidates_rejected_variant_gate": rejected["variant"],
            "status_counts": dict(sorted(statuses.items())),
            "unclassified": 0,
            "writes": {"woo": 0, "supabase": 0, "sql": 0, "prices": 0, "stock": 0, "relationships": 0},
        },
    }

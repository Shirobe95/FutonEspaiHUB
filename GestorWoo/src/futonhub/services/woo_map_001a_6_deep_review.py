"""Read-only deep review of the unresolved WOO-MAP-001A.5 identities.

The service is intentionally a planning boundary.  It only consumes the
frozen physical review rows, the prior research leads, the 174 safe claims,
and a Woo index built by GET.  It never persists an association or calls a
write client.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable, Mapping


FINAL_STATUSES = frozenset({
    "READY_SAFE_AFTER_DEEP_REVIEW",
    "READY_USER_APPROVAL_SINGLE",
    "MULTIPLE_REAL_CANDIDATES",
    "NO_MATCH_AFTER_DEEP_REVIEW",
    "NO_DIRECT_WOO_ENTITY_SUPPORTED",
    "PHYSICAL_IDENTITY_DUPLICATE_OR_LEGACY_REVIEW",
    "POSSIBLE_RETIRED_OR_LEGACY_ENTITY",
    "RETIRED_CONFIRMED_BY_USER",
    "WOO_CATALOG_INCONSISTENCY",
    "CONFLICT",
    "READ_ERROR",
})

RETIRED_ITEM_IDS = frozenset({"406006", "404017"})
RETIRED_CODES = frozenset({"0406006", "406006", "0404017"})
TATAMI_PORTABLE_CODES = frozenset({"0201013", "0208001", "0206001", "0213001", "0216001", "0214001"})
TATAMI_SUPPORT_CODES = frozenset({"0201006", "0201007"})
LEADING_ZERO_DUO_CODES = frozenset({"0078009", "0078012", "0078013"})
MANUAL_COLOR_CODES = frozenset({"0214001"})

_DIMENSION_PATTERN = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[x*]\s*\d+(?:[.,]\d+)?){1,2}", re.IGNORECASE)
_BASIC_COLORS = frozenset({"azul", "crudo", "granate", "negro", "naranja", "verde", "natural", "rojo", "violeta"})


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normal(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _normal(value).split() if token}


def _dimensions(value: Any) -> set[str]:
    return {
        match.group(0).replace(" ", "").replace("*", "x").replace(",", ".").lower()
        for match in _DIMENSION_PATTERN.finditer(_text(value))
    }


def _attribute_text(raw: Mapping[str, Any]) -> str:
    values: list[str] = []
    for attribute in raw.get("attributes") or []:
        if not isinstance(attribute, Mapping):
            continue
        name = _text(attribute.get("name"))
        option = _text(attribute.get("option") or attribute.get("value"))
        options = attribute.get("options")
        if isinstance(options, list):
            option = option or ", ".join(_text(value) for value in options if _text(value))
        if name or option:
            values.append(f"{name}={option}".strip("="))
    return " | ".join(values)


def _categories_text(raw: Mapping[str, Any]) -> str:
    return " | ".join(
        _text(category.get("name"))
        for category in raw.get("categories") or []
        if isinstance(category, Mapping) and _text(category.get("name"))
    )


def _parent_for(entity: Mapping[str, Any], woo_index: Any) -> dict[str, Any] | None:
    parent_id = _text(entity.get("parent_woo_id"))
    return woo_index.products_by_id.get(parent_id) if parent_id else None


def _physical_code(row: Mapping[str, Any]) -> str:
    return _text(row.get("codigo") or row.get("hub_item_code") or row.get("heca_reference"))


def _is_retired_by_user(row: Mapping[str, Any]) -> bool:
    return _text(row.get("item_id")) in RETIRED_ITEM_IDS or _physical_code(row) in RETIRED_CODES


def _is_no_gama(value: Any) -> bool:
    return _normal(value) in {"", "no gama", "sin gama", "n a", "na"}


def _is_exact_variant(required: str, candidate_text: str) -> bool:
    required_normal = _normal(required)
    candidate_normal = _normal(candidate_text)
    if not required_normal:
        return True
    if required_normal not in candidate_normal:
        return False
    # A basic colour may not be silently promoted to a derived shade.  For
    # example, verde is deliberately different from verde oscuro.
    if required_normal in _BASIC_COLORS:
        for suffix in ("oscuro", "claro", "marino"):
            if f"{required_normal} {suffix}" in candidate_normal:
                return False
    return True


def _model_requirement(row: Mapping[str, Any]) -> tuple[str, ...]:
    code = _physical_code(row)
    family = _normal(row.get("family"))
    group = _normal(row.get("filter_group"))
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
        if "algodon 1 latex" in group:
            return ("futon", "algodon", "latex")
        if "algodon 2 latex" in group:
            return ("futon", "algodon", "latex")
        if group == "algodon":
            return ("futon", "algodon")
    if group:
        return tuple(group.split())
    return tuple(token for token in name.split() if token not in {"natural", "cm"})


def _model_is_correct(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> bool:
    code = _physical_code(row)
    parent_text = _normal((parent or entity).get("name"))
    requested = _model_requirement(row)
    if code in TATAMI_PORTABLE_CODES:
        return _text(entity.get("parent_woo_id")) == "3657" and all(token in parent_text for token in requested)
    if code in TATAMI_SUPPORT_CODES:
        return all(token in parent_text for token in requested)
    if code == "0402014":
        return all(token in parent_text for token in requested) and "base" not in parent_text
    if _normal(row.get("filter_group")) == "lana":
        return all(token in parent_text for token in requested) and "duo" not in parent_text
    if "futones" in _normal(row.get("family")) and "algodon" in requested:
        return all(token in parent_text for token in requested) and "sofa" not in parent_text
    return all(token in parent_text for token in requested)


def _candidate_dimensions(row: Mapping[str, Any], entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> set[str]:
    values = [entity.get("name"), _attribute_text(dict(entity.get("raw") or {}))]
    if parent is not None:
        # Parent-level option lists usually enumerate every variation. They
        # cannot prove the size of one specific child variation.  The parent
        # name may still contain a fixed size and is therefore retained.
        values.append(parent.get("name"))
        if _physical_code(row) in TATAMI_PORTABLE_CODES:
            parent_raw = dict(parent.get("raw") or {})
            # This parent has one documented tatami dimension in its product
            # description while the variation varies only by futon colour.
            values.extend((parent_raw.get("description"), parent_raw.get("short_description")))
    result: set[str] = set()
    for value in values:
        result.update(_dimensions(value))
    return result


def _variant_source(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> str:
    raw = dict(entity.get("raw") or {})
    values = [entity.get("name"), _attribute_text(raw), raw.get("sku")]
    # A simple product has its variant at product level.  For a variation,
    # parent options are intentionally excluded so that a parent with every
    # colour cannot falsely prove the child colour.
    if parent is None:
        values.append(_attribute_text(raw))
    return " ".join(_text(value) for value in values if _text(value))


def _historical_signals(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> tuple[str, ...]:
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    combined = " ".join(_normal(value) for value in (
        entity.get("name"), raw.get("slug"), _categories_text(raw),
        (parent or {}).get("name"), parent_raw.get("slug"), _categories_text(parent_raw),
    ))
    result: list[str] = []
    status = _normal(raw.get("status") or entity.get("status"))
    visibility = _normal(raw.get("catalog_visibility"))
    if status and status != "publish":
        result.append("NON_PUBLISH_STATUS")
    if visibility and visibility != "visible":
        result.append("HIDDEN_CATALOG_VISIBILITY")
    if "outlet" in combined or "unica unidad" in combined:
        result.append("OUTLET_OR_CLEARANCE_SIGNAL")
    date_created = _text(raw.get("date_created_gmt") or raw.get("date_created"))
    if date_created[:4].isdigit() and int(date_created[:4]) <= 2020:
        result.append("OLD_CREATION_DATE")
    return tuple(result)


def _candidate_is_pack(entity: Mapping[str, Any], parent: Mapping[str, Any] | None) -> bool:
    raw = dict(entity.get("raw") or {})
    sku = _text(entity.get("woo_sku") or raw.get("sku"))
    text = _normal(" ".join((_text(entity.get("name")), _text((parent or {}).get("name")), sku)))
    return "pack" in text or "kit" in text or "|" in sku


@dataclass(frozen=True)
class DeepCandidate:
    woo_id: str
    parent_woo_id: str
    parent_name: str
    kind: str
    woo_sku: str
    woo_name: str
    status: str
    catalog_visibility: str
    attributes: str
    variation_attributes: str
    categories: str
    price: str
    date_created: str
    date_modified: str
    slug: str
    permalink: str
    image_url: str
    evidence_for: tuple[str, ...]
    evidence_against: tuple[str, ...]
    already_claimed_by: str
    historical_signals: tuple[str, ...]
    live_read_ok: bool

    @property
    def eligible(self) -> bool:
        return self.live_read_ok and not self.evidence_against

    @property
    def rank_score(self) -> tuple[int, int, int, str]:
        return (
            1 if self.eligible else 0,
            len(self.evidence_for),
            -len(self.evidence_against),
            self.woo_id,
        )


def _safe_claims(safe_rows: Iterable[Mapping[str, Any]]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    by_id: dict[str, set[str]] = defaultdict(set)
    by_sku: dict[str, set[str]] = defaultdict(set)
    for raw in safe_rows:
        row = dict(raw)
        code = _physical_code(row)
        woo_id = _text(row.get("woo_id"))
        woo_sku = _text(row.get("woo_sku"))
        if code and woo_id:
            by_id[woo_id].add(code)
        if code and woo_sku:
            by_sku[woo_sku].add(code)
    return by_id, by_sku


def _expand_candidate(
    source: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    woo_index: Any,
    claims_by_id: Mapping[str, set[str]],
    claims_by_sku: Mapping[str, set[str]],
) -> DeepCandidate:
    kind = _text(source.get("candidate_kind"))
    woo_id = _text(source.get("candidate_woo_id"))
    entity: Mapping[str, Any] | None = None
    if kind == "product":
        entity = woo_index.products_by_id.get(woo_id)
    elif kind == "variation":
        entity = woo_index.variations_by_id.get(woo_id)
    if entity is None:
        return DeepCandidate(
            woo_id=woo_id, parent_woo_id=_text(source.get("candidate_parent_woo_id")), parent_name="", kind=kind,
            woo_sku=_text(source.get("candidate_woo_sku")), woo_name=_text(source.get("candidate_woo_name")),
            status="", catalog_visibility="", attributes="", variation_attributes="", categories="", price="",
            date_created="", date_modified="", slug="", permalink="", image_url="", evidence_for=(),
            evidence_against=("READ_ERROR",), already_claimed_by="", historical_signals=(), live_read_ok=False,
        )

    entity = dict(entity)
    parent = _parent_for(entity, woo_index)
    raw = dict(entity.get("raw") or {})
    parent_raw = dict((parent or {}).get("raw") or {})
    code = _physical_code(row)
    required_size = _text(row.get("filter_size") or row.get("size"))
    required_gama = _text(row.get("filter_gama"))
    observed_dimensions = _candidate_dimensions(row, entity, parent)
    required_dimensions = _dimensions(required_size)
    against: list[str] = []
    for_evidence: list[str] = []

    if _model_is_correct(row, entity, parent):
        for_evidence.append("MODEL_PARENT_CONFIRMED")
    else:
        against.append("WRONG_PARENT" if code in TATAMI_PORTABLE_CODES else "MODEL_MISMATCH")
    if required_dimensions and required_dimensions.issubset(observed_dimensions):
        for_evidence.append("SIZE_EXACT")
    else:
        against.append("SIZE_MISMATCH")
    if not _is_no_gama(required_gama):
        variant_text = _variant_source(entity, parent)
        if _is_exact_variant(required_gama, variant_text):
            for_evidence.append("VARIANT_EXACT")
        elif _normal(required_gama) == "natural" and any(token in _normal(variant_text) for token in ("crudo", "sin barniz")):
            against.append("FINISH_MISMATCH")
        elif _normal(required_gama) in _BASIC_COLORS:
            against.append("COLOR_MISMATCH")
        else:
            against.append("VARIANT_MISMATCH")
    if code in MANUAL_COLOR_CODES and "COLOR_MISMATCH" not in against:
        against.append("COLOR_MISMATCH")
    if _candidate_is_pack(entity, parent) and code not in TATAMI_PORTABLE_CODES:
        against.append("PACK_INSTEAD_OF_DIRECT")
    if _text(entity.get("woo_item_kind")) == "product" and _normal(raw.get("type")) in {"variable", "variable subscription"} and required_dimensions:
        # A variable parent describes a range. A physical item with a concrete
        # size can only use a concrete variation as a future direct target.
        against.append("WRONG_PRODUCT_KIND")
    if code == "0402014" and "base" in _normal((parent or entity).get("name")):
        against.append("WRONG_PRODUCT_KIND")

    claims = sorted((claims_by_id.get(_text(entity.get("woo_id")), set()) | claims_by_sku.get(_text(entity.get("woo_sku")), set())) - {code})
    already_claimed = ", ".join(claims)
    # A SAFE claim blocks promotion only after the candidate itself passed all
    # identity checks. It must not mask a wrong parent, a base, or a pack.
    if claims and not against:
        against.append("ALREADY_CLAIMED_BY_OTHER_PHYSICAL")
    signals = _historical_signals(entity, parent)
    if "OUTLET_OR_CLEARANCE_SIGNAL" in signals:
        against.append("OUTLET_HISTORICAL_MISMATCH")

    image_url = ""
    images = raw.get("images") or parent_raw.get("images") or []
    if images and isinstance(images[0], Mapping):
        image_url = _text(images[0].get("src"))
    parent_attributes = _attribute_text(parent_raw)
    child_attributes = _attribute_text(raw)
    attributes = " | ".join(part for part in (f"variation: {child_attributes}" if child_attributes else "", f"parent: {parent_attributes}" if parent_attributes else "") if part)
    regular = _text(entity.get("regular_price"))
    sale = _text(entity.get("sale_price"))
    effective = _text(entity.get("effective_price"))
    price = f"regular={regular}; sale={sale}; effective={effective}"
    return DeepCandidate(
        woo_id=_text(entity.get("woo_id")),
        parent_woo_id=_text(entity.get("parent_woo_id")),
        parent_name=_text((parent or {}).get("name")),
        kind=_text(entity.get("woo_item_kind")),
        woo_sku=_text(entity.get("woo_sku")),
        woo_name=_text(entity.get("name")),
        status=_text(raw.get("status") or entity.get("status")),
        catalog_visibility=_text(raw.get("catalog_visibility")),
        attributes=attributes,
        variation_attributes=child_attributes,
        categories=_categories_text(raw) or _categories_text(parent_raw),
        price=price,
        date_created=_text(raw.get("date_created_gmt") or raw.get("date_created")),
        date_modified=_text(raw.get("date_modified_gmt") or raw.get("date_modified") or entity.get("date_modified")),
        slug=_text(raw.get("slug")),
        permalink=_text(raw.get("permalink") or parent_raw.get("permalink")),
        image_url=image_url,
        evidence_for=tuple(sorted(set(for_evidence))),
        evidence_against=tuple(sorted(set(against))),
        already_claimed_by=already_claimed,
        historical_signals=signals,
        live_read_ok=True,
    )


def _status_for(row: Mapping[str, Any], candidates: list[DeepCandidate], source_count: int) -> str:
    code = _physical_code(row)
    if _is_retired_by_user(row):
        return "RETIRED_CONFIRMED_BY_USER"
    eligible = [candidate for candidate in candidates if candidate.eligible]
    if eligible and any(candidate.historical_signals for candidate in eligible):
        return "POSSIBLE_RETIRED_OR_LEGACY_ENTITY"
    if len(eligible) == 1:
        return "READY_SAFE_AFTER_DEEP_REVIEW" if code in TATAMI_PORTABLE_CODES else "READY_USER_APPROVAL_SINGLE"
    if len(eligible) > 1:
        return "MULTIPLE_REAL_CANDIDATES"
    if candidates and all(not candidate.live_read_ok for candidate in candidates):
        return "READ_ERROR"
    if code == "0402014":
        return "WOO_CATALOG_INCONSISTENCY"
    if any("ALREADY_CLAIMED_BY_OTHER_PHYSICAL" in candidate.evidence_against for candidate in candidates):
        return "PHYSICAL_IDENTITY_DUPLICATE_OR_LEGACY_REVIEW"
    if source_count:
        return "NO_MATCH_AFTER_DEEP_REVIEW"
    return "NO_DIRECT_WOO_ENTITY_SUPPORTED"


def _recommended_action(status: str) -> str:
    return {
        "RETIRED_CONFIRMED_BY_USER": "KEEP_HISTORY_ONLY",
        "READY_SAFE_AFTER_DEEP_REVIEW": "PLAN_ONLY_PENDING_RELATIONSHIP_CUT",
        "READY_USER_APPROVAL_SINGLE": "USER_APPROVAL_REQUIRED",
        "MULTIPLE_REAL_CANDIDATES": "CHOOSE_ONE_EXACT_CANDIDATE_OR_KEEP_UNLINKED",
        "POSSIBLE_RETIRED_OR_LEGACY_ENTITY": "KEEP_HISTORY_AND_REVIEW_USER",
        "PHYSICAL_IDENTITY_DUPLICATE_OR_LEGACY_REVIEW": "KEEP_SEPARATE_IDENTITIES_REVIEW",
        "WOO_CATALOG_INCONSISTENCY": "INVESTIGATE_WOO_CATALOG_GAP",
        "READ_ERROR": "RETRY_READ_ONLY_WOO_GET",
    }.get(status, "KEEP_UNLINKED")


def _business_status(row: Mapping[str, Any]) -> str:
    return "RETIRED_CONFIRMED_BY_USER" if _is_retired_by_user(row) else "ACTIVE_OR_UNCONFIRMED"


def _select_candidates(status: str, candidates: list[DeepCandidate]) -> list[DeepCandidate]:
    ordered = sorted(candidates, key=lambda candidate: candidate.rank_score, reverse=True)
    if status == "RETIRED_CONFIRMED_BY_USER":
        model_first = [candidate for candidate in ordered if "MODEL_PARENT_CONFIRMED" in candidate.evidence_for]
        return (model_first or ordered)[:1]
    return ordered[:3]


def _row_without_candidate(row: Mapping[str, Any], status: str) -> dict[str, str]:
    return {
        "physical_sku": _physical_code(row),
        "physical_name": _text(row.get("name")),
        "family": _text(row.get("family")),
        "size": _text(row.get("filter_size") or row.get("size")),
        "gama": _text(row.get("filter_gama")),
        "business_status": _business_status(row),
        "current_commercial_eligibility": "NO" if _is_retired_by_user(row) else "UNCONFIRMED",
        "price_change_eligible": "NO",
        "decision_status": status,
        "candidate_rank": "0",
        "woo_id": "",
        "parent_woo_id": "",
        "parent_name": "",
        "woo_kind": "",
        "woo_sku": "",
        "woo_name": "",
        "woo_status": "",
        "catalog_visibility": "",
        "attributes": "",
        "variation_attributes": "",
        "categories": "",
        "price": "",
        "date_created": "",
        "date_modified": "",
        "woo_slug": "",
        "permalink": "",
        "image_url": "",
        "historical_woo_entity": "NO",
        "historical_woo_id": "",
        "historical_parent_woo_id": "",
        "historical_reason": "",
        "evidence_for": "No direct Woo entity retained after deep review.",
        "evidence_against": "",
        "already_claimed_by": "",
        "recommended_action": _recommended_action(status),
    }


def deep_review(
    review_rows: Iterable[Mapping[str, Any]],
    research_rows: Iterable[Mapping[str, Any]],
    safe_rows: Iterable[Mapping[str, Any]],
    *,
    woo_index: Any,
) -> dict[str, Any]:
    """Classify exactly the 39 review rows without mutating any system."""
    research_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in research_rows:
        item = dict(raw)
        research_by_item[_text(item.get("item_id"))].append(item)
    claims_by_id, claims_by_sku = _safe_claims(safe_rows)

    decisions: list[dict[str, Any]] = []
    human_rows: list[dict[str, str]] = []
    for raw in review_rows:
        row = dict(raw)
        sources = research_by_item.get(_text(row.get("item_id")), [])
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for source in sources:
            kind = _text(source.get("candidate_kind"))
            woo_id = _text(source.get("candidate_woo_id"))
            if woo_id:
                deduped.setdefault((kind, woo_id), source)
        candidates = [
            _expand_candidate(source, row, woo_index=woo_index, claims_by_id=claims_by_id, claims_by_sku=claims_by_sku)
            for source in deduped.values()
        ]
        status = _status_for(row, candidates, len(deduped))
        selected = _select_candidates(status, candidates)
        if not selected:
            human_rows.append(_row_without_candidate(row, status))
        for rank, candidate in enumerate(selected, start=1):
            retired = _is_retired_by_user(row)
            is_history = retired and candidate.live_read_ok
            human_rows.append({
                "physical_sku": _physical_code(row),
                "physical_name": _text(row.get("name")),
                "family": _text(row.get("family")),
                "size": _text(row.get("filter_size") or row.get("size")),
                "gama": _text(row.get("filter_gama")),
                "business_status": _business_status(row),
                "current_commercial_eligibility": "NO" if retired else "UNCONFIRMED",
                "price_change_eligible": "NO",
                "decision_status": status,
                "candidate_rank": str(rank),
                "woo_id": candidate.woo_id,
                "parent_woo_id": candidate.parent_woo_id,
                "parent_name": candidate.parent_name,
                "woo_kind": candidate.kind,
                "woo_sku": candidate.woo_sku,
                "woo_name": candidate.woo_name,
                "woo_status": candidate.status,
                "catalog_visibility": candidate.catalog_visibility,
                "attributes": candidate.attributes,
                "variation_attributes": candidate.variation_attributes,
                "categories": candidate.categories,
                "price": candidate.price,
                "date_created": candidate.date_created,
                "date_modified": candidate.date_modified,
                "woo_slug": candidate.slug,
                "permalink": candidate.permalink,
                "image_url": candidate.image_url,
                "historical_woo_entity": "YES" if is_history else "NO",
                "historical_woo_id": candidate.woo_id if is_history else "",
                "historical_parent_woo_id": candidate.parent_woo_id if is_history else "",
                "historical_reason": "Confirmed retired by user; Woo evidence retained only for traceability." if is_history else "",
                "evidence_for": " | ".join(candidate.evidence_for + candidate.historical_signals),
                "evidence_against": " | ".join(candidate.evidence_against),
                "already_claimed_by": candidate.already_claimed_by,
                "recommended_action": _recommended_action(status),
            })
        decisions.append({
            "item_id": _text(row.get("item_id")),
            "codigo": _physical_code(row),
            "name": _text(row.get("name")),
            "family": _text(row.get("family")),
            "decision_status": status,
            "candidate_source_count": len(deduped),
            "candidate_selected_count": len(selected),
        })

    counts = Counter(decision["decision_status"] for decision in decisions)
    family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for decision in decisions:
        family_counts[decision["family"]][decision["decision_status"]] += 1
    if any(decision["decision_status"] not in FINAL_STATUSES for decision in decisions):
        raise RuntimeError("The deep review emitted an unsupported final status.")
    if any(sum(1 for item in human_rows if item["physical_sku"] == decision["codigo"]) > 3 for decision in decisions):
        raise RuntimeError("A human review case exceeds the three-candidate cap.")
    return {
        "decisions": decisions,
        "human_rows": human_rows,
        "summary": {
            "review_total": len(decisions),
            "decision_counts": dict(sorted(counts.items())),
            "active_total": sum(counts[key] for key in ("READY_SAFE_AFTER_DEEP_REVIEW", "READY_USER_APPROVAL_SINGLE")),
            "retired_total": counts["RETIRED_CONFIRMED_BY_USER"],
            "uncertain_total": len(decisions) - sum(counts[key] for key in ("READY_SAFE_AFTER_DEEP_REVIEW", "READY_USER_APPROVAL_SINGLE", "RETIRED_CONFIRMED_BY_USER")),
            "family_breakdown": {family: dict(sorted(values.items())) for family, values in sorted(family_counts.items())},
            "writes": {"woo": 0, "supabase": 0, "sql": 0, "relationships": 0},
        },
    }

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re
import unicodedata

from futonhub.core.config import load_settings
from gestorwoo.woocommerce import WooCommerceClient


SAFE_SUPABASE_FILL_FIELDS = {
    "family",
    "subgroup",
    "size",
    "materials",
    "commercial_status",
    "is_pack",
    "woo_item_kind",
    "woo_id",
    "woo_parent_id",
    "woo_sku",
    "woo_name",
    "woo_type",
    "woo_price",
    "woo_categories",
    "woo_link_status",
    "woo_link_notes",
}

NEVER_AUTO_UPDATE_FIELDS = {
    "primary_supplier_price",
    "pascal_price",
    "weighted_average_cost",
    "store_stock",
    "warehouse_stock",
    "rotation_c",
    "packages",
}


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        text = str(value or "").strip().replace(",", ".")
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def normalize_key(value: Any) -> str:
    text = normalize_text(str(value or ""))
    text = re.sub(r"[^0-9a-z]+", "", text)
    return text


def normalize_sku(value: Any) -> str:
    """Normaliza un SKU para comparaciones internas estables.

    Usa la misma regla canónica que los índices de inventario: minúsculas,
    sin acentos, espacios ni separadores. Un SKU formado solo por signos
    queda vacío y no participa en comparaciones padre/variación.
    """
    return normalize_key(value)


def sku_keys(value: Any) -> list[str]:
    raw = str(value or "").strip()
    keys: set[str] = set()
    if raw:
        keys.add(normalize_key(raw))
        digits = re.sub(r"\D+", "", raw)
        if digits:
            keys.add(digits)
            try:
                keys.add(str(int(digits)))
            except Exception:
                pass
    return [k for k in keys if k]


def extract_attributes(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for attr in item.get("attributes") or []:
        if isinstance(attr, dict):
            name = _safe_text(attr.get("name"))
            options = attr.get("options")
            if isinstance(options, list):
                value = " ".join(_safe_text(x) for x in options)
            else:
                value = _safe_text(attr.get("option") or options)
            if name or value:
                parts.append(f"{name}: {value}".strip(": "))
    return " ".join(parts)


def category_names(item: dict[str, Any]) -> str:
    names: list[str] = []
    for cat in item.get("categories") or []:
        if isinstance(cat, dict) and cat.get("name"):
            names.append(str(cat.get("name")))
    return ", ".join(names)


def clean_dimension(value: str) -> str:
    value = str(value or "").strip().replace(",", ".")
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def extract_size_from_text(text: str) -> str:
    normalized = normalize_text(text).replace(",", ".")
    full = re.search(
        r"(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{1,2}(?:\.\d+)?)",
        normalized,
    )
    if full:
        return "x".join(clean_dimension(part) for part in full.groups())

    base = re.search(
        r"(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{2,3}(?:\.\d+)?)",
        normalized,
    )
    thickness = re.search(
        r"(?:grosor|espesor|altura|alto)\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)",
        normalized,
    )
    if base and thickness:
        return "x".join(
            [
                clean_dimension(base.group(1)),
                clean_dimension(base.group(2)),
                clean_dimension(thickness.group(1)),
            ]
        )
    if base:
        return "x".join(clean_dimension(part) for part in base.groups())
    return ""


def count_distinct_sizes(text: str) -> int:
    normalized = normalize_text(text).replace(",", ".")
    matches = re.findall(
        r"(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{2,3}(?:\.\d+)?)(?:\s*[x*×]\s*(\d{1,2}(?:\.\d+)?))?",
        normalized,
    )
    normalized_sizes: set[str] = set()
    for match in matches:
        parts = [clean_dimension(part) for part in match if part]
        if len(parts) >= 2:
            normalized_sizes.add("x".join(parts))
    return len(normalized_sizes)


def _has_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _has_negated_component(text: str, component_patterns: tuple[str, ...]) -> bool:
    for pattern in component_patterns:
        if re.search(rf"\bsin\s+{pattern}\b", text):
            return True
    return False


def _component_present(text: str, positive_tokens: tuple[str, ...], negation_patterns: tuple[str, ...]) -> bool:
    if _has_negated_component(text, negation_patterns):
        return False
    return any(token in text for token in positive_tokens)


def _first_size_source(name_text_raw: str, attr_text_raw: str, item_kind: str, woo_type: str) -> str:
    """Name wins. Attributes are support, not steering wheel."""
    name_size = extract_size_from_text(name_text_raw)
    if name_size:
        return name_size
    attr_size = extract_size_from_text(attr_text_raw)
    if item_kind == "product" and woo_type == "variable" and count_distinct_sizes(attr_text_raw) > 1:
        return ""
    return attr_size


def classify_woo_item(woo: dict[str, Any]) -> dict[str, Any]:
    name_raw = _safe_text(woo.get("name"))
    categories_raw = _safe_text(woo.get("categories"))
    attr_raw = _safe_text(woo.get("attributes_text"))
    sku_raw = _safe_text(woo.get("sku"))
    type_raw = _safe_text(woo.get("type"))

    name_text = normalize_text(name_raw)
    categories_text = normalize_text(categories_raw)
    attr_text = normalize_text(attr_raw)
    main_text = " ".join([name_text, categories_text]).strip()
    support_text = " ".join([name_text, categories_text, attr_text, normalize_text(sku_raw), normalize_text(type_raw)]).strip()

    item_kind = _safe_text(woo.get("item_kind"))
    woo_type = type_raw

    status = "Normal"
    if "outlet" in main_text or "outlet" in attr_text:
        status = "Outlet"
    elif "oferta" in main_text or "rebaja" in main_text:
        status = "Oferta"

    # Name-level signals: these decide the main family.
    name_has_futon = "futon" in name_text
    name_has_funda = _component_present(name_text, ("funda", "fundas", "cover", "covers"), ("fundas?", "covers?"))
    name_has_cojin = _component_present(name_text, ("cojin", "cojines", "almohada", "almohadas"), ("cojines?", "almohadas?"))
    name_has_topper = _component_present(name_text, ("topper",), ("topper",))
    name_has_tatami = "tatami" in name_text or "tatamis" in name_text
    name_has_sofa = "sofa cama" in name_text or "sofacama" in name_text or "sofa" in name_text
    name_has_cama = "cama japonesa" in name_text or "camas japonesas" in name_text or ("cama" in name_text and "madera" in main_text)
    name_has_mesita = "mesita" in name_text
    name_has_base = "base" in name_text and "tatami" in main_text

    main_has_futon = "futon" in main_text
    main_has_tatami = "tatami" in main_text or "tatamis" in main_text

    is_cover_for_futon = bool(re.search(r"\bfundas?\s+(?:de\s+|para\s+)?futones?\b", name_text)) or bool(re.search(r"\bcovers?\s+(?:de\s+|para\s+)?futones?\b", name_text))
    starts_like_cover = bool(re.match(r"^\s*(solo\s+\d+\s+unidades?\s*-\s*)?fundas?\b", name_text))
    only_cover_product = (starts_like_cover or is_cover_for_futon) and not re.search(r"\+\s*fut[oó]n| con\s+fut[oó]n", name_text)
    explicit_pack_words = _has_any(name_text, ("combinacion", "composicion", "pack", "combo", "conjunto"))
    plus_component = bool(re.search(r"(\+| con | incluye | y ).*(fundas?|cojines?|almohadas?|tatamis?)", name_text))
    name_has_real_futon_product = name_has_futon and not only_cover_product
    tatami_futon_combo = name_has_tatami and name_has_real_futon_product
    bundle_futon_components = name_has_real_futon_product and plus_component and (name_has_funda or name_has_cojin or name_has_tatami)
    bundle_tatami_futon = tatami_futon_combo and (explicit_pack_words or plus_component or "oferta" in categories_text or name_has_funda or name_has_cojin)
    bundle_product = (explicit_pack_words or bundle_futon_components or bundle_tatami_futon) and not only_cover_product

    is_pack = 1 if bundle_product else 0

    family = "Otros / Sin clasificar"
    subgroup = ""
    classification_kind = "single_item"

    # Main family priority. Attributes must not hijack this.
    if only_cover_product:
        family = "Complementos"
        subgroup = "Funda futón"
        classification_kind = "single_item"
        is_pack = 0
    elif bundle_product:
        family = "Ofertas / Packs"
        classification_kind = "pack_or_composition"
        if name_has_tatami and name_has_real_futon_product:
            subgroup = "Pack tatami + futón"
        elif name_has_real_futon_product and name_has_funda and name_has_cojin:
            subgroup = "Pack futón + funda + cojines"
        elif name_has_real_futon_product and name_has_funda:
            subgroup = "Pack futón + funda"
        elif name_has_real_futon_product and name_has_cojin:
            subgroup = "Pack futón + cojines"
        elif name_has_cojin and "pack" in name_text and not name_has_real_futon_product and not name_has_tatami:
            family = "Complementos"
            subgroup = "Cojines"
            classification_kind = "single_item"
            is_pack = 0
        else:
            subgroup = "Pack"
    elif name_has_sofa:
        family = "Sofás Cama"
        subgroup = "Sofá cama"
    elif name_has_mesita:
        family = "Complementos"
        subgroup = "Mesita"
    elif name_has_topper:
        family = "Complementos"
        subgroup = "Topper"
    elif name_has_funda:
        family = "Complementos"
        subgroup = "Funda futón"
    elif name_has_cojin:
        family = "Complementos"
        subgroup = "Cojines"
    elif name_has_cama or name_has_base:
        family = "Camas Japonesas"
        subgroup = "Base tatami" if name_has_base else "Cama japonesa"
    elif name_has_tatami and not name_has_real_futon_product:
        family = "Tatamis"
        subgroup = "Tatami"
    elif name_has_real_futon_product:
        family = "Futones"
        subgroup = "Futón"
    elif "sofás cama" in categories_text or "sofas cama" in categories_text:
        family = "Sofás Cama"
        subgroup = "Sofá cama"
    elif "camas japonesas" in categories_text or "bases para tatami" in categories_text:
        family = "Camas Japonesas"
        subgroup = "Cama japonesa"
    elif "tatami" in categories_text and not main_has_futon:
        family = "Tatamis"
        subgroup = "Tatami"
    elif "futones" in categories_text:
        family = "Futones"
        subgroup = "Futón"
    elif "fundas" in categories_text:
        family = "Complementos"
        subgroup = "Funda futón"
    elif "topper" in categories_text:
        family = "Complementos"
        subgroup = "Topper"
    elif "complementos" in categories_text:
        family = "Complementos"
        subgroup = "Complemento"

    materials: list[str] = []
    material_rules = [
        ("Algodón", ("algodon", "cotton")),
        ("Látex", ("latex",)),
        ("Lana", ("lana", "wool", "duo")),
        ("Coco", ("coco", "coir")),
        ("Bambú", ("bambu", "bamboo")),
        ("Madera", ("madera", "wood")),
    ]

    material_text = support_text
    if family in {"Sofás Cama", "Camas Japonesas"}:
        # Furniture material: do not absorb optional futon material lines.
        material_text = " ".join([name_text, categories_text])
        structure_match = re.search(r"(acabado|estructura|madera)[^:]*:\s*([^:]+)", attr_text)
        if structure_match:
            material_text += " " + structure_match.group(0)
    for label, tokens in material_rules:
        if any(token in material_text for token in tokens):
            materials.append(label)

    size = family_aware_size(name_raw, attr_raw, family, subgroup, item_kind, woo_type)
    multiple_sizes = count_distinct_sizes(attr_raw) > 1
    if item_kind == "product" and woo_type == "variable" and multiple_sizes and not extract_size_from_text(name_raw):
        size = ""

    confidence = "Alta"
    reasons: list[str] = []
    if family == "Otros / Sin clasificar":
        confidence = "Baja"
        reasons.append("No se pudo detectar familia.")
    if not size and not (item_kind == "product" and woo_type == "variable" and multiple_sizes):
        reasons.append("No se detectó medida.")
    if item_kind == "product" and woo_type == "variable" and multiple_sizes:
        reasons.append("Producto padre variable con múltiples medidas; la medida debe venir de la variación.")
    if family == "Futones" and not materials:
        reasons.append("No se detectó material.")
    if classification_kind == "pack_or_composition":
        reasons.append("Composición/pack detectado; revisar antes de aplicar.")
    if attr_text and (("funda" in attr_text or "cojin" in attr_text) and family in {"Futones", "Sofás Cama"}):
        reasons.append("Atributos contienen complementos; no se usaron para cambiar la familia principal.")
    if _has_negated_component(name_text, ("cojines?", "almohadas?", "fundas?")):
        reasons.append("Nombre contiene negación de complemento; se ignoró para clasificar familia.")

    return {
        "family": family,
        "subgroup": subgroup,
        "size": size,
        "materials": ", ".join(dict.fromkeys(materials)),
        "commercial_status": status,
        "is_pack": is_pack,
        "confidence": confidence,
        "classification_reasons": reasons,
        "multiple_sizes_detected": multiple_sizes,
        "classification_kind": classification_kind,
    }


def extract_labeled_size(attr_text_raw: str, labels: tuple[str, ...]) -> str:
    text = str(attr_text_raw or "")
    for label in labels:
        pattern = rf"{re.escape(label)}\s*:\s*([^:\n\r]+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            size = extract_size_from_text(match.group(1))
            if size:
                return size
    return ""


def family_aware_size(name_raw: str, attr_raw: str, family: str, subgroup: str, item_kind: str, woo_type: str) -> str:
    name_size = extract_size_from_text(name_raw)
    if name_size:
        return name_size

    if family == "Sofás Cama":
        return extract_labeled_size(attr_raw, ("Medidas sofá", "Medidas estructura", "Medida Interior"))
    if family == "Camas Japonesas":
        return extract_labeled_size(attr_raw, ("Medidas estructura", "Medida estructura", "Medida Interior"))
    if family == "Tatamis":
        return extract_labeled_size(attr_raw, ("Medidas estructura", "Medidas tatami"))
    if subgroup == "Funda futón":
        return extract_labeled_size(attr_raw, ("Medidas funda",))
    if subgroup in {"Cojines", "Mesita", "Topper"}:
        return extract_labeled_size(attr_raw, ("Medidas estructura", "Medidas sofá"))
    if family == "Futones":
        return extract_labeled_size(attr_raw, ("Medidas futón",))
    if family == "Ofertas / Packs":
        # Packs stay conservative: name size if present, otherwise leave blank for manual review.
        return ""

    attr_size = extract_size_from_text(attr_raw)
    if item_kind == "product" and woo_type == "variable" and count_distinct_sizes(attr_raw) > 1:
        return ""
    return attr_size



def flatten_woo_product(product: dict[str, Any], *, item_kind: str = "product", parent: dict[str, Any] | None = None) -> dict[str, Any]:
    parent = parent or {}
    woo_id = product.get("id")
    parent_id = parent.get("id") if parent else product.get("parent_id")
    name = _safe_text(product.get("name")) or _safe_text(parent.get("name"))
    sku = _safe_text(product.get("sku")) or _safe_text(parent.get("sku"))
    woo_type = _safe_text(product.get("type")) or ("variation" if item_kind == "variation" else "")
    categories = category_names(parent if item_kind == "variation" and parent else product)
    attributes_text = " ".join([extract_attributes(parent), extract_attributes(product)]).strip()
    price = _safe_text(product.get("regular_price") or product.get("price"))
    stock_quantity = product.get("stock_quantity")
    raw = {
        "item_kind": item_kind,
        "woo_id": woo_id,
        "parent_woo_id": parent_id,
        "sku": sku,
        "name": name,
        "type": woo_type,
        "price": price,
        "stock_quantity": stock_quantity,
        "categories": categories,
        "attributes_text": attributes_text,
        "status": product.get("status"),
        "permalink": product.get("permalink") or parent.get("permalink"),
    }
    raw.update(classify_woo_item(raw))
    return raw


def load_woocommerce_items(limit_products: int | None = None) -> list[dict[str, Any]]:
    settings = load_settings()
    client = WooCommerceClient(settings.woocommerce_url, settings.consumer_key, settings.consumer_secret)
    items: list[dict[str, Any]] = []
    variable_products: list[dict[str, Any]] = []
    count = 0
    for product in client.iter_products():
        items.append(flatten_woo_product(product, item_kind="product"))
        count += 1
        if product.get("type") == "variable":
            variable_products.append(product)
        if limit_products and count >= limit_products:
            break
    for product in variable_products:
        for variation in client.iter_product_variations(int(product["id"])):
            items.append(flatten_woo_product(variation, item_kind="variation", parent=product))
    return items


def load_inventory_items(session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 1000
    select_cols = (
        "item_id,name,family,subgroup,size,materials,commercial_status,is_pack,"
        "heca_reference,woo_item_kind,woo_id,woo_parent_id,woo_sku,woo_name,woo_type,woo_price,"
        "woo_categories,woo_link_status,woo_link_notes,primary_supplier_price,pascal_price,"
        "weighted_average_cost,store_stock,warehouse_stock,rotation_c,packages"
    )
    while True:
        resp = session.client.table("inventory_items").select(select_cols).range(start, start + page_size - 1).execute()
        batch = list(getattr(resp, "data", None) or [])
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def build_inventory_indexes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_item_id: dict[str, dict[str, Any]] = {}
    by_woo_id: dict[str, list[dict[str, Any]]] = {}
    by_sku: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item_id = row.get("item_id")
        if item_id not in (None, ""):
            by_item_id[str(item_id)] = row
            for key in sku_keys(item_id):
                by_sku.setdefault(key, []).append(row)
        if row.get("heca_reference"):
            for key in sku_keys(row.get("heca_reference")):
                by_sku.setdefault(key, []).append(row)
        if row.get("woo_sku"):
            for key in sku_keys(row.get("woo_sku")):
                by_sku.setdefault(key, []).append(row)
        if row.get("woo_id") not in (None, ""):
            by_woo_id.setdefault(str(row.get("woo_id")), []).append(row)
    return {"by_item_id": by_item_id, "by_woo_id": by_woo_id, "by_sku": by_sku}


def is_woo_already_linked(woo: dict[str, Any], indexes: dict[str, Any]) -> bool:
    woo_id = woo.get("woo_id")
    if woo_id in (None, ""):
        return False
    return bool(indexes.get("by_woo_id", {}).get(str(woo_id)))


def manual_link_candidate(woo: dict[str, Any], match_method: str, indexes: dict[str, Any]) -> dict[str, Any]:
    """Describe whether this Woo row can be offered for manual Supabase linking later."""
    if match_method.endswith("conflict"):
        return {
            "available": False,
            "reason": "Woo tiene conflicto de enlace; resolver duplicados antes de enlazar manualmente.",
        }
    if is_woo_already_linked(woo, indexes):
        return {
            "available": False,
            "reason": "Este Woo ya está enlazado con otro item Supabase.",
        }
    if _safe_text(woo.get("item_kind")) == "product" and _safe_text(woo.get("type")) == "variable" and not _safe_text(woo.get("sku")):
        return {
            "available": False,
            "reason": "Producto padre variable sin SKU; normalmente se enlazan variaciones o un item creado manualmente con revisión.",
        }
    return {
        "available": True,
        "reason": "Woo no enlazado; candidato para enlace manual con item Supabase sin Woo.",
        "woo_id": woo.get("woo_id"),
        "woo_sku": woo.get("sku"),
        "woo_name": woo.get("name"),
    }


def find_inventory_match(woo: dict[str, Any], indexes: dict[str, Any]) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
    woo_id = woo.get("woo_id")
    if woo_id not in (None, ""):
        matches = indexes["by_woo_id"].get(str(woo_id), [])
        if len(matches) == 1:
            return matches[0], "woo_id", matches
        if len(matches) > 1:
            return None, "woo_id_conflict", matches

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in sku_keys(woo.get("sku")):
        for row in indexes["by_sku"].get(key, []):
            item_key = str(row.get("item_id"))
            if item_key not in seen:
                matches.append(row)
                seen.add(item_key)
    if len(matches) == 1:
        return matches[0], "sku", matches
    if len(matches) > 1:
        return None, "sku_conflict", matches
    return None, "no_match", []


def compare_field(field: str, supa_value: Any, woo_value: Any) -> dict[str, Any] | None:
    supa = _safe_text(supa_value)
    woo = _safe_text(woo_value)
    if field in {"is_pack"}:
        supa = "1" if str(supa_value or "").strip() in {"1", "true", "True"} else "0"
        woo = "1" if str(woo_value or "").strip() in {"1", "true", "True"} else "0"
    if not supa and woo:
        return {"field": field, "supabase_value": supa, "woo_value": woo, "action": "fill_empty", "severity": "Warning"}
    if supa and woo and normalize_text(supa) != normalize_text(woo):
        # Woo fields can update Woo metadata, but not overwrite internal core fields blindly.
        return {"field": field, "supabase_value": supa, "woo_value": woo, "action": "review_difference", "severity": "Info"}
    return None


def is_variable_parent_without_sku(woo: dict[str, Any]) -> bool:
    return (
        _safe_text(woo.get("item_kind")) == "product"
        and _safe_text(woo.get("type")) == "variable"
        and not _safe_text(woo.get("sku"))
    )


def is_test_or_demo_woo(woo: dict[str, Any], ignored_parent_ids: set[int]) -> bool:
    """Return True for explicit Woo test/demo rows that must not pollute operations."""
    woo_id = woo.get("woo_id")
    parent_id = woo.get("parent_woo_id")
    name = normalize_text(woo.get("name"))
    return (
        woo_id in ignored_parent_ids
        or parent_id in ignored_parent_ids
        or any(token in name for token in ("prueba", "test product", "test1", "test2", "test3"))
    )


def is_variable_parent_sku_owned_by_variation(woo: dict[str, Any], variation_skus_by_parent: dict[int, set[str]]) -> bool:
    """A variable parent can share its SKU with one of its variations; the variation owns the operational link."""
    if _safe_text(woo.get("item_kind")) != "product" or _safe_text(woo.get("type")) != "variable":
        return False
    woo_id = woo.get("woo_id")
    sku = normalize_sku(woo.get("sku"))
    if not sku or woo_id in (None, ""):
        return False
    return sku in variation_skus_by_parent.get(int(woo_id), set())


def is_parent_product(woo: dict[str, Any]) -> bool:
    return _safe_text(woo.get("item_kind")) == "product"


def compute_review_flag(
    *,
    status: str,
    match_method: str,
    supabase_match: dict[str, Any] | None,
    issues: list[dict[str, Any]],
    proposed_update: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    severity = "OK"

    if not supabase_match:
        reasons.append("Sin enlace Supabase")
        severity = "Warning"
    if match_method.endswith("conflict"):
        reasons.append("Conflicto de enlace")
        severity = "Critical"
    if status in {"Error", "Critical"}:
        reasons.append(f"Estado {status}")
        severity = status
    if classification.get("confidence") == "Baja":
        reasons.append("Clasificación baja")
        if severity == "OK":
            severity = "Warning"
    if not classification.get("family") or classification.get("family") == "Otros / Sin clasificar":
        reasons.append("Familia sin definir")
        if severity == "OK":
            severity = "Warning"
    if not classification.get("size") and classification.get("classification_kind") != "pack_or_composition":
        reasons.append("Medida pendiente")
        if severity == "OK":
            severity = "Warning"
    if classification.get("classification_kind") == "pack_or_composition":
        reasons.append("Pack/composición: revisar")
        if severity == "OK":
            severity = "Warning"
    if proposed_update:
        reasons.append("Campos rellenables en Supabase")
        if severity == "OK":
            severity = "Info"

    for issue in issues:
        code = str(issue.get("code") or issue.get("field") or "")
        sev = str(issue.get("severity") or "")
        if sev in {"Error", "Critical"} and f"Incidencia {sev}" not in reasons:
            reasons.append(f"Incidencia {sev}")
            severity = sev
        if code in {"low_classification_confidence", "classification_reason"} and "Revisar clasificación" not in reasons:
            reasons.append("Revisar clasificación")
            if severity == "OK":
                severity = "Warning"

    return {
        "needs_review": bool(reasons),
        "severity": severity,
        "reasons": list(dict.fromkeys(reasons)),
    }



# =====================================================
# v53 - Enlace manual Woo ↔ Supabase con preview seguro
# =====================================================

def _fetch_inventory_item_by_id(session, item_id: int) -> dict[str, Any] | None:
    resp = session.client.table("inventory_items").select("*").eq("item_id", int(item_id)).limit(1).execute()
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def _rows_with_woo_id(session, woo_id: Any) -> list[dict[str, Any]]:
    if woo_id in (None, ""):
        return []
    try:
        resp = session.client.table("inventory_items").select("item_id,name,woo_id,woo_sku,woo_name,woo_link_status").eq("woo_id", int(woo_id)).execute()
    except Exception:
        resp = session.client.table("inventory_items").select("item_id,name,woo_id,woo_sku,woo_name,woo_link_status").eq("woo_id", str(woo_id)).execute()
    return list(getattr(resp, "data", None) or [])


def _inventory_item_has_woo(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if row.get("woo_id") not in (None, ""):
        return True
    if _safe_text(row.get("woo_link_status")).lower() in {"enlazado", "linked", "woo_synced"}:
        return True
    return False


def search_manual_link_inventory_candidates(session, query: str, limit: int = 25) -> list[dict[str, Any]]:
    """Busca items Supabase candidatos a enlazarse manualmente con Woo.

    Devuelve solo filas que no tienen woo_id y no parecen ya enlazadas.
    No escribe nada.
    """
    q = _safe_text(query)
    if not q:
        return []
    limit = max(1, min(int(limit or 25), 50))
    select_cols = (
        "item_id,name,family,subgroup,size,materials,commercial_status,is_pack,"
        "heca_reference,woo_id,woo_sku,woo_name,woo_link_status,store_stock,warehouse_stock"
    )
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(batch: list[dict[str, Any]] | None) -> None:
        for row in batch or []:
            key = str(row.get("item_id") or "")
            if not key or key in seen:
                continue
            if _inventory_item_has_woo(row):
                continue
            seen.add(key)
            rows.append(row)

    if q.isdigit():
        try:
            resp = session.client.table("inventory_items").select(select_cols).eq("item_id", int(q)).limit(limit).execute()
            add(getattr(resp, "data", None))
        except Exception:
            pass
        try:
            resp = session.client.table("inventory_items").select(select_cols).eq("heca_reference", q).limit(limit).execute()
            add(getattr(resp, "data", None))
        except Exception:
            pass
    pattern = f"%{q}%"
    for col in ("name", "heca_reference", "family", "subgroup", "materials"):
        if len(rows) >= limit:
            break
        try:
            resp = session.client.table("inventory_items").select(select_cols).ilike(col, pattern).limit(limit).execute()
            add(getattr(resp, "data", None))
        except Exception:
            continue
    return rows[:limit]


def preview_manual_woo_link(session, woo_sync_row: dict[str, Any], item_id: int) -> dict[str, Any]:
    woo = woo_sync_row.get("woo") or {}
    cls = woo_sync_row.get("classification_after") or {}
    candidate = woo_sync_row.get("manual_link_candidate") or {}
    if not candidate.get("available"):
        raise RuntimeError(candidate.get("reason") or "Este Woo no está disponible para enlace manual.")
    woo_id = woo.get("woo_id")
    if woo_id in (None, ""):
        raise RuntimeError("Woo no tiene woo_id válido.")
    already = _rows_with_woo_id(session, woo_id)
    if already:
        names = ", ".join(f"{r.get('item_id')} · {r.get('name') or r.get('woo_name') or '-'}" for r in already[:5])
        raise RuntimeError(f"Este Woo ya está enlazado en Supabase: {names}")
    before = _fetch_inventory_item_by_id(session, int(item_id))
    if before is None:
        raise RuntimeError(f"No existe inventory_items.item_id={item_id}.")
    if _inventory_item_has_woo(before):
        raise RuntimeError("El item Supabase elegido ya tiene Woo enlazado. Elige un item sin Woo.")

    update_payload = {
        "woo_item_kind": woo.get("item_kind"),
        "woo_id": woo.get("woo_id"),
        "woo_parent_id": woo.get("parent_woo_id"),
        "woo_sku": woo.get("sku"),
        "woo_name": woo.get("name"),
        "woo_type": woo.get("type"),
        "woo_price": woo.get("price"),
        "woo_categories": woo.get("categories"),
        "woo_link_status": "Enlazado manual",
        "woo_link_notes": "Enlace manual desde revisión Woo Sync v53.",
    }
    # Rellenamos solo huecos de clasificación, nunca pisamos datos existentes del catálogo interno.
    for field in ("family", "subgroup", "size", "materials", "commercial_status", "is_pack"):
        if before.get(field) in (None, "") and cls.get(field) not in (None, ""):
            update_payload[field] = cls.get(field)

    after = dict(before)
    after.update(update_payload)
    changes = [
        {"field": k, "before": before.get(k), "after": v}
        for k, v in update_payload.items()
        if before.get(k) != v
    ]
    if not changes:
        raise RuntimeError("No hay cambios para aplicar.")
    return {
        "item_id": int(item_id),
        "woo": dict(woo),
        "before": before,
        "after": after,
        "changes": changes,
        "update_payload": update_payload,
    }


def format_manual_woo_link_preview(preview: dict[str, Any]) -> str:
    woo = preview.get("woo") or {}
    before = preview.get("before") or {}
    lines = [
        "PREVIEW ENLACE MANUAL WOO ↔ SUPABASE",
        "=" * 48,
        "No toca WooCommerce. Solo escribirá el enlace en inventory_items si confirmas.",
        "",
        f"Woo ID: {woo.get('woo_id')} · Tipo: {woo.get('item_kind') or '-'} · SKU: {woo.get('sku') or '-'}",
        f"Woo nombre: {woo.get('name') or '-'}",
        "",
        f"Item Supabase: {preview.get('item_id')} · {before.get('name') or '-'}",
        f"Estado Woo actual Supabase: {before.get('woo_link_status') or '-'}",
        "",
        "Cambios propuestos:",
    ]
    for change in preview.get("changes") or []:
        lines.append(f"- {change.get('field')}: {change.get('before') or '-'} → {change.get('after') or '-'}")
    lines.extend(["", "Se generará operation_snapshot + audit_log. Confirmación requerida: ENLAZAR"])
    return "\n".join(lines)


def apply_manual_woo_link(session, woo_sync_row: dict[str, Any], item_id: int, settings=None) -> dict[str, Any]:
    from futonhub.cloud.audit import AuditEvent, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
    from futonhub.core.config import load_settings

    settings = settings or load_settings()
    preview = preview_manual_woo_link(session, woo_sync_row, item_id)
    before = preview["before"]
    update_payload = dict(preview["update_payload"])
    operation_id = new_operation_id("WOOLINK")
    now = datetime.now(timezone.utc).isoformat()

    snapshot = OperationSnapshot(
        operation_id=operation_id,
        module="woocommerce_sync",
        action="manual_woo_link",
        entity_type="inventory_item",
        entity_id=str(item_id),
        before_data=before,
        reason="Snapshot antes de enlazar manualmente WooCommerce con item Supabase.",
    )
    write_snapshot(session, snapshot)

    update_payload["updated_at"] = now
    update_payload["updated_by"] = session.user_id
    update_payload["source_row"] = {
        "operation_id": operation_id,
        "updated_by_email": session.email,
        "role": session.role,
        "machine": settings.machine_name,
        "manual_woo_link": True,
        "note": "Enlace manual Woo ↔ Supabase. WooCommerce no fue tocado.",
    }
    resp = session.client.table("inventory_items").update(update_payload).eq("item_id", int(item_id)).execute()
    written_rows = getattr(resp, "data", None) or []
    written = written_rows[0] if written_rows else {**before, **update_payload}

    event = AuditEvent(
        operation_id=operation_id,
        module="woocommerce_sync",
        action="manual_woo_link",
        status="OK",
        severity="INFO",
        entity_type="inventory_item",
        entity_id=str(item_id),
        before_data=before,
        after_data=written,
        message="Item Supabase enlazado manualmente con WooCommerce. WooCommerce no fue tocado.",
    )
    write_audit_event(session, event, settings)
    return {"operation_id": operation_id, "preview": preview, "before": before, "after": written}

def apply_manual_classification_edit(row: dict[str, Any], edited: dict[str, Any]) -> dict[str, Any]:
    """Apply a local/manual classification edit to a preview row.

    This does not write Supabase. It only updates the row and JSON preview data
    so the team can curate classifications before v53/v54 write operations.
    """
    row = dict(row)
    woo = dict(row.get("woo") or {})
    cls = dict(row.get("classification_after") or {})

    editable_fields = {
        "family",
        "subgroup",
        "size",
        "materials",
        "commercial_status",
        "is_pack",
        "confidence",
        "classification_kind",
    }
    normalized: dict[str, Any] = {}
    for key, value in (edited or {}).items():
        if key not in editable_fields:
            continue
        if key == "is_pack":
            normalized[key] = 1 if str(value).strip().lower() in {"1", "true", "sí", "si", "yes", "pack"} else 0
        else:
            normalized[key] = str(value or "").strip()

    for key, value in normalized.items():
        cls[key] = value
        woo[key] = value

    reasons = list(cls.get("classification_reasons") or [])
    reasons.append("Clasificación editada manualmente en preview.")
    cls["classification_reasons"] = list(dict.fromkeys(reasons))
    woo["classification_reasons"] = cls["classification_reasons"]

    row["woo"] = woo
    row["classification_after"] = cls
    row["manual_classification_edit"] = {
        "applied": True,
        "fields": normalized,
    }

    # Rebuild proposed fill fields if there is a Supabase match with empty fields.
    supa = row.get("supabase_match") or {}
    proposed = dict(row.get("proposed_supabase_update") or {})
    for field in ("family", "subgroup", "size", "materials", "commercial_status", "is_pack"):
        if field in normalized and not _safe_text(supa.get(field)):
            proposed[field] = normalized[field]
    row["proposed_supabase_update"] = proposed
    row["review"] = compute_review_flag(
        status=str(row.get("status") or "Info"),
        match_method=str(row.get("match_method") or ""),
        supabase_match=supa if supa else None,
        issues=list(row.get("issues") or []),
        proposed_update=proposed,
        classification=cls,
    )
    return row


def build_sync_preview(session, *, limit_products: int | None = None) -> dict[str, Any]:
    woo_items = load_woocommerce_items(limit_products=limit_products)
    inventory = load_inventory_items(session)
    indexes = build_inventory_indexes(inventory)

    items: list[dict[str, Any]] = []
    counters = {"total_woo_items": len(woo_items), "linked_ok": 0, "no_match": 0, "warnings": 0, "errors": 0, "critical": 0}

    ignored_parent_ids: set[int] = set()
    variation_skus_by_parent: dict[int, set[str]] = {}
    for candidate in woo_items:
        candidate_name = normalize_text(candidate.get("name"))
        if _safe_text(candidate.get("item_kind")) == "product" and any(token in candidate_name for token in ("prueba", "test product")):
            if candidate.get("woo_id") not in (None, ""):
                ignored_parent_ids.add(int(candidate.get("woo_id")))
        if _safe_text(candidate.get("item_kind")) == "variation" and candidate.get("parent_woo_id") not in (None, "", 0, "0"):
            sku = normalize_sku(candidate.get("sku"))
            if sku:
                variation_skus_by_parent.setdefault(int(candidate.get("parent_woo_id")), set()).add(sku)

    for woo in woo_items:
        ignored_test = is_test_or_demo_woo(woo, ignored_parent_ids)
        informational_parent = is_variable_parent_without_sku(woo)
        parent_sku_owned_by_variation = is_variable_parent_sku_owned_by_variation(woo, variation_skus_by_parent)

        if ignored_test:
            match, match_method, all_matches = None, "ignored_test_item", []
        elif parent_sku_owned_by_variation:
            match, match_method, all_matches = None, "parent_sku_owned_by_variation", []
        else:
            match, match_method, all_matches = find_inventory_match(woo, indexes)
        status = "OK"
        issues: list[dict[str, Any]] = []
        proposed_update: dict[str, Any] = {}
        supabase_snapshot: dict[str, Any] | None = None

        if ignored_test:
            status = "Info"
            issues.append({
                "severity": "Info",
                "code": "ignored_test_item",
                "message": "Producto de prueba/test excluido del seguimiento operativo.",
            })
        elif parent_sku_owned_by_variation:
            status = "Info"
            issues.append({
                "severity": "Info",
                "code": "parent_sku_owned_by_variation",
                "message": "El SKU del producto padre variable pertenece operativamente a una variación; el padre queda informativo.",
            })
        elif match_method.endswith("conflict"):
            status = "Critical"
            issues.append({
                "severity": "Critical",
                "code": match_method,
                "message": f"Más de un item de Supabase coincide con Woo {woo.get('woo_id')} / SKU {woo.get('sku')}.",
                "matches": [m.get("item_id") for m in all_matches],
            })
        elif match is None:
            if is_variable_parent_without_sku(woo):
                status = "Info"
                issues.append({
                    "severity": "Info",
                    "code": "variable_parent_without_sku",
                    "message": "Producto padre variable sin SKU; se revisan principalmente sus variaciones.",
                })
            else:
                status = "Warning"
                issues.append({
                    "severity": "Warning",
                    "code": "no_supabase_match",
                    "message": "Producto/variación Woo sin enlace claro en inventory_items.",
                })
        else:
            supabase_snapshot = dict(match)
            counters["linked_ok"] += 1
            field_map = {
                "family": woo.get("family"),
                "subgroup": woo.get("subgroup"),
                "size": woo.get("size"),
                "materials": woo.get("materials"),
                "commercial_status": woo.get("commercial_status"),
                "is_pack": woo.get("is_pack"),
                "woo_item_kind": woo.get("item_kind"),
                "woo_id": woo.get("woo_id"),
                "woo_parent_id": woo.get("parent_woo_id"),
                "woo_sku": woo.get("sku"),
                "woo_name": woo.get("name"),
                "woo_type": woo.get("type"),
                "woo_price": woo.get("price"),
                "woo_categories": woo.get("categories"),
                "woo_link_status": "Enlazado",
                "woo_link_notes": "",
            }
            for field, woo_value in field_map.items():
                diff = compare_field(field, match.get(field), woo_value)
                if diff:
                    issues.append(diff)
                    if diff["action"] == "fill_empty" and field in SAFE_SUPABASE_FILL_FIELDS:
                        proposed_update[field] = woo_value

        informational_only = ignored_test or informational_parent or parent_sku_owned_by_variation
        if not informational_only:
            if not woo.get("sku"):
                issues.append({"severity": "Error", "code": "missing_sku", "message": "Woo no tiene SKU. El enlace automático pierde fiabilidad."})
            if woo.get("price") in (None, "", "0", "0.0", "0.00") and woo.get("item_kind") != "variation":
                issues.append({"severity": "Error", "code": "zero_or_empty_woo_price", "message": "Precio Woo vacío o 0 en producto."})
            if woo.get("confidence") == "Baja":
                issues.append({"severity": "Warning", "code": "low_classification_confidence", "message": "Autoclasificación con confianza baja."})
            for reason in woo.get("classification_reasons") or []:
                issues.append({"severity": "Warning", "code": "classification_reason", "message": reason})

        severities = {str(issue.get("severity") or "Info") for issue in issues}
        if "Critical" in severities:
            status = "Critical"
        elif "Error" in severities:
            status = "Error"
        elif "Warning" in severities and status == "OK":
            status = "Warning"

        counters_key = {"Warning": "warnings", "Error": "errors", "Critical": "critical"}.get(status)
        if counters_key:
            counters[counters_key] += 1
        if match is None and not match_method.endswith("conflict") and not informational_only:
            counters["no_match"] += 1

        classification_after = {
            "family": woo.get("family"),
            "subgroup": woo.get("subgroup"),
            "size": woo.get("size"),
            "materials": woo.get("materials"),
            "commercial_status": woo.get("commercial_status"),
            "is_pack": woo.get("is_pack"),
            "confidence": woo.get("confidence"),
            "classification_reasons": woo.get("classification_reasons"),
            "multiple_sizes_detected": woo.get("multiple_sizes_detected"),
            "classification_kind": woo.get("classification_kind"),
        }
        review = compute_review_flag(
            status=status,
            match_method=match_method,
            supabase_match=supabase_snapshot,
            issues=issues,
            proposed_update=proposed_update,
            classification=classification_after,
        )
        if informational_only:
            review = {
                "needs_review": False,
                "severity": "Info",
                "reasons": ["Excluido del pendiente operativo"],
            }

        items.append({
            "status": status,
            "match_method": match_method,
            "woo": woo,
            "classification_after": classification_after,
            "supabase_match": supabase_snapshot,
            "proposed_supabase_update": proposed_update,
            "issues": issues,
            "review": review,
            "manual_classification_edit": {"applied": False, "fields": {}},
            "manual_link_candidate": manual_link_candidate(woo, match_method, indexes),
            "safe_to_apply_later": status in {"OK", "Warning"} and bool(proposed_update),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "preview_only_no_writes",
        "counters": counters,
        "items": items,
        "rules": {
            "safe_fill_fields": sorted(SAFE_SUPABASE_FILL_FIELDS),
            "never_auto_update_fields": sorted(NEVER_AUTO_UPDATE_FIELDS),
        },
    }


def export_preview_json(preview: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return output_path

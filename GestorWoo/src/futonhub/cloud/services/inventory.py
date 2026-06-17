from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from futonhub.cloud.audit import AuditEvent, CloudAuditError, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot
from gestorwoo.config import Settings, load_settings


def _json_safe(value: Any) -> Any:
    import json
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}




INVENTORY_SELECT_COLUMNS = (
    'item_id,name,family,subgroup,size,materials,cubic_meters,rotation_c,packages,store_stock,warehouse_stock,'
    'hub_item_code,item_record_type,base_item_code,heca_reference,commercial_status,woo_item_kind,woo_id,woo_parent_id,woo_name,woo_sku,woo_price,woo_categories,woo_link_status,'
    'order_calculated_price,weighted_average_cost,primary_supplier_price,pascal_price,supplier_order_qty,supplier_order_provider,notes,updated_at'
)

INVENTORY_EDITABLE_FIELDS = {
    'name',
    'family',
    'subgroup',
    'materials',
    'size',
    'cubic_meters',
    'rotation_c',
    'packages',
    'primary_supplier_price',
    'pascal_price',
    'store_stock',
    'warehouse_stock',
    'notes',
}

NUMERIC_INVENTORY_FIELDS = {'cubic_meters', 'rotation_c', 'packages', 'primary_supplier_price', 'pascal_price', 'store_stock', 'warehouse_stock'}


def _normalize_inventory_edit_value(field: str, value: Any) -> Any:
    if value is None:
        return None
    if field in NUMERIC_INVENTORY_FIELDS:
        return _coerce_optional_float(value)
    text = str(value).strip()
    return text if text else None



def _format_relation_quantity(value: Any) -> str:
    try:
        n = float(str(value).replace(',', '.'))
        if n.is_integer():
            return str(int(n))
        return (f"{n:.3f}").rstrip('0').rstrip('.')
    except Exception:
        return str(value or '1')


def _normalize_inventory_numeric_code(value: Any) -> str:
    text = str(value or '').strip()
    if text.isdigit():
        return text.lstrip('0') or '0'
    return text


def _inventory_code_cache_keys(value: Any) -> set[str]:
    text = str(value or '').strip()
    if not text:
        return set()
    return {text.lower(), _normalize_inventory_numeric_code(text).lower()}


def _format_pack_component_line(component: dict[str, Any]) -> str:
    code = component.get('component_item_code') or '-'
    qty = _format_relation_quantity(component.get('quantity') or 1)
    name = component.get('component_name') or ''
    if name:
        return f"{code} x{qty} · {name}"
    return f"{code} x{qty}"


def _component_summary_from_woo_sku(woo_sku: Any) -> tuple[str, str]:
    """Fallback visible para packs: resume tokens del SKU aunque falle la tabla de componentes."""
    text = str(woo_sku or '').strip()
    if '|' not in text:
        return '', ''
    counts: dict[str, int] = {}
    order: list[str] = []
    for raw in text.split('|'):
        token = raw.strip()
        if not token:
            continue
        if token not in counts:
            counts[token] = 0
            order.append(token)
        counts[token] += 1
    parts = [f"{token} x{counts[token]}" for token in order]
    return '; '.join(parts), '\n'.join(f"- {part}" for part in parts)


def _fill_component_names_from_inventory(session, components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resuelve nombres reutilizando la búsqueda real de Inventario.

    No mantiene una segunda implementación de búsqueda. Para cada componente
    llama a `search_cloud_inventory_items(..., enrich_components=False)`, elige
    la coincidencia exacta y copia únicamente su nombre.
    """
    if not components:
        return components

    missing_values = {
        "", "-", "none", "null", "sin nombre", "sin nombre visible",
        "pendiente", "sin definir", "no encontrado en inventario",
    }

    def normalize(value: Any) -> str:
        return _normalize_inventory_numeric_code(value).lower()

    def is_missing(value: Any) -> bool:
        return normalize(value) in missing_values

    codes: list[str] = []
    for component in components:
        code_raw = str(component.get("component_item_code") or "").strip()
        if code_raw and is_missing(component.get("component_name")) and code_raw not in codes:
            codes.append(code_raw)

    def visible_name(row: dict[str, Any]) -> str:
        return str(
            row.get('name')
            or row.get('woo_name')
            or row.get('hub_search_result_name')
            or ''
        ).strip()

    def add_to_cache(cache: dict[str, str], key: Any, row: dict[str, Any]) -> None:
        name = visible_name(row)
        if not name:
            return
        for cache_key in _inventory_code_cache_keys(key):
            cache.setdefault(cache_key, name)

    def fetch_by(column: str, values: list[Any]) -> list[dict[str, Any]]:
        if not values:
            return []
        try:
            resp = (
                session.client.table('inventory_items')
                .select(INVENTORY_SELECT_COLUMNS)
                .in_(column, values)
                .execute()
            )
            return [dict(row) for row in (getattr(resp, 'data', None) or [])]
        except Exception:
            return []

    cache: dict[str, str] = {}
    lookup_codes = sorted({code for raw in codes for code in (raw, _normalize_inventory_numeric_code(raw)) if code})
    for row in fetch_by('heca_reference', lookup_codes):
        add_to_cache(cache, row.get('heca_reference'), row)
    for row in fetch_by('hub_item_code', lookup_codes):
        add_to_cache(cache, row.get('hub_item_code'), row)
    for row in fetch_by('woo_sku', lookup_codes):
        add_to_cache(cache, row.get('woo_sku'), row)

    numeric_codes: list[int] = []
    for code in codes:
        try:
            numeric_codes.append(int(code))
        except Exception:
            continue
    for row in fetch_by('item_id', numeric_codes):
        for key in ('item_id', 'heca_reference', 'hub_item_code', 'woo_sku'):
            add_to_cache(cache, row.get(key), row)

    for component in components:
        code_raw = str(component.get("component_item_code") or "").strip()
        code = normalize(code_raw)
        if not code or not is_missing(component.get("component_name")):
            continue
        resolved = cache.get(code, "")
        component["component_name"] = resolved
        component["component_name_status"] = "resolved" if resolved else "not_found"
        component["component_name_lookup_source"] = "inventory_bulk_lookup" if resolved else "inventory_bulk_no_result"

    return components


def _enrich_rows_with_component_summary(session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Añade resumen de componentes/alias para que la UI no muestre packs a ciegas.

    v55: cuando una búsqueda devuelve WOO-PACK-xxxx, trae todos sus componentes
    desde `inventory_item_components`, no solo el componente por el que coincidió.
    """
    if not rows:
        return rows

    codes: list[str] = []
    for row in rows:
        code = row.get('hub_search_code') or row.get('hub_item_code') or row.get('heca_reference')
        record_type = row.get('hub_search_record_type') or row.get('item_record_type')
        if code and record_type in {'woo_pack', 'manual_pack'}:
            codes.append(str(code))
    codes = sorted(set(codes))

    components_by_parent: dict[str, list[dict[str, Any]]] = {}
    if codes:
        try:
            resp = (
                session.client.table('inventory_item_components')
                .select('parent_item_code,component_item_code,component_name,quantity,relation_type')
                .in_('parent_item_code', codes)
                .eq('relation_type', 'component')
                .order('parent_item_code', desc=False)
                .order('component_item_code', desc=False)
                .execute()
            )
            fetched_components = [dict(comp) for comp in (getattr(resp, 'data', None) or [])]
            fetched_components = _fill_component_names_from_inventory(session, fetched_components)
            for comp in fetched_components:
                parent = str(comp.get('parent_item_code') or '')
                if not parent:
                    continue
                components_by_parent.setdefault(parent, []).append(dict(comp))
        except Exception:
            components_by_parent = {}

    for row in rows:
        code = str(row.get('hub_search_code') or row.get('hub_item_code') or row.get('heca_reference') or '')
        record_type = row.get('hub_search_record_type') or row.get('item_record_type')
        if record_type in {'woo_pack', 'manual_pack'}:
            comps = components_by_parent.get(code) or []
            if comps:
                parts = [_format_pack_component_line(comp) for comp in comps]
                row['hub_pack_components'] = comps
                row['hub_pack_components_text'] = '; '.join(parts)
                row['hub_pack_components_multiline'] = '\n'.join(f"- {part}" for part in parts)
            else:
                sku_text, sku_multiline = _component_summary_from_woo_sku(row.get('woo_sku'))
                if sku_text:
                    row['hub_pack_components_text'] = sku_text
                    row['hub_pack_components_multiline'] = sku_multiline
                    row['hub_pack_components_source'] = 'woo_sku_fallback'
                else:
                    related = row.get('hub_search_related_code')
                    qty = row.get('hub_search_relation_quantity')
                    if related:
                        qty_text = _format_relation_quantity(qty or 1)
                        related_name = row.get('hub_search_related_name') or ''
                        fallback = f"{related} x{qty_text}" + (f" · {related_name}" if related_name else '')
                        row['hub_pack_components_text'] = fallback
                        row['hub_pack_components_multiline'] = f"- {fallback}"
                        row['hub_pack_components_source'] = 'matched_component_fallback'
        elif record_type == 'alias':
            base = row.get('base_item_code') or row.get('hub_search_related_code')
            if base:
                row['hub_pack_components_text'] = f"Alias de {base}"
                row['hub_pack_components_multiline'] = f"Alias de {base}"
    return rows


def fetch_inventory_pack_components(session, parent_item_code: str, woo_sku: Any = None) -> dict[str, Any]:
    """Devuelve el contenido completo de un pack con nombres vivos.

    Ruta principal v59.7: consulta `v_inventory_component_search`, que ya une
    inventory_item_components con inventory_items y devuelve component_name.
    De esta forma no repetimos la búsqueda del Inventario en Python.
    """
    parent = str(parent_item_code or '').strip()
    components: list[dict[str, Any]] = []
    lookup_error = ''

    if parent:
        try:
            resp = (
                session.client.table('v_inventory_component_search')
                .select('relation_id,parent_item_code,component_item_code,component_name,quantity,relation_type,token_type')
                .eq('parent_item_code', parent)
                .eq('relation_type', 'component')
                .eq('token_type', 'component_code')
                .order('component_item_code', desc=False)
                .execute()
            )
            raw_rows = [dict(row) for row in (getattr(resp, 'data', None) or [])]
            seen: set[tuple[str, str]] = set()
            for row in raw_rows:
                code = str(row.get('component_item_code') or '').strip()
                relation_id = str(row.get('relation_id') or '').strip()
                key = (relation_id, code)
                if not code or key in seen:
                    continue
                seen.add(key)
                components.append({
                    'parent_item_code': parent,
                    'component_item_code': code,
                    'component_name': str(row.get('component_name') or '').strip(),
                    'quantity': row.get('quantity') or 1,
                    'relation_type': row.get('relation_type') or 'component',
                })
        except Exception as exc:
            lookup_error = f'v_inventory_component_search: {exc}'
            components = []

    # Respaldo prudente: tabla de relaciones + resolvedor existente.
    if not components and parent:
        try:
            resp = (
                session.client.table('inventory_item_components')
                .select('parent_item_code,component_item_code,component_name,quantity,relation_type')
                .eq('parent_item_code', parent)
                .eq('relation_type', 'component')
                .order('component_item_code', desc=False)
                .execute()
            )
            components = [dict(row) for row in (getattr(resp, 'data', None) or [])]
            components = _fill_component_names_from_inventory(session, components)
        except Exception as exc:
            extra = f'inventory_item_components: {exc}'
            lookup_error = f'{lookup_error}; {extra}'.strip('; ')
            components = []

    if components:
        parts = [_format_pack_component_line(comp) for comp in components]
        return {
            'source': 'v_inventory_component_search' if not lookup_error else 'inventory_item_components_fallback',
            'parent_item_code': parent,
            'components': components,
            'text': '; '.join(parts),
            'multiline': '\n'.join(f'- {part}' for part in parts),
            'lookup_error': lookup_error,
        }

    sku_text, sku_multiline = _component_summary_from_woo_sku(woo_sku)
    if sku_text:
        return {
            'source': 'woo_sku_fallback',
            'parent_item_code': parent,
            'components': [],
            'text': sku_text,
            'multiline': sku_multiline,
            'lookup_error': lookup_error,
        }
    return {
        'source': 'empty',
        'parent_item_code': parent,
        'components': [],
        'text': '',
        'multiline': '',
        'lookup_error': lookup_error,
    }


def list_cloud_inventory_items(session, limit: int = 100) -> list[dict[str, Any]]:
    """Lista inventario real desde Supabase para la vista ERP.

    No devuelve datos mock. Si no hay filas visibles, la UI debe mostrar estado vacio.
    """
    limit = max(1, min(int(limit or 100), 500))
    try:
        response = (
            session.client.table('inventory_items')
            .select(INVENTORY_SELECT_COLUMNS)
            .order('updated_at', desc=True)
            .limit(limit)
            .execute()
        )
    except Exception:
        response = (
            session.client.table('inventory_items')
            .select(INVENTORY_SELECT_COLUMNS)
            .limit(limit)
            .execute()
        )
    return list(getattr(response, 'data', None) or [])


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default

# =====================================================
# v12.3 - Inventario real interno Supabase (sin WooCommerce)
# =====================================================

def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
        if value == '':
            return None
    return float(value)


def search_cloud_inventory_items(session, query: str, limit: int = 25, *, enrich_components: bool = True) -> list[dict[str, Any]]:
    """Busca items reales de inventory_items en Supabase.

    v54: intenta primero la vista exacta `v_inventory_hub_search_ranked`, que devuelve
    items simples, alias y packs Woo por código exacto de componente. Si la vista no
    existe o falla, cae al buscador clásico por inventory_items.

    No toca WooCommerce. Devuelve filas operativas internas.
    """
    q = (query or '').strip()
    if not q:
        return []
    limit = max(1, min(int(limit or 25), 100))

    def _fetch_inventory_full(item_id: Any) -> dict[str, Any] | None:
        try:
            resp = (
                session.client.table('inventory_items')
                .select(INVENTORY_SELECT_COLUMNS)
                .eq('item_id', int(item_id))
                .limit(1)
                .execute()
            )
            data = getattr(resp, 'data', None) or []
            return dict(data[0]) if data else None
        except Exception:
            return None

    # 1) Búsqueda exacta v54: códigos simples, alias y componentes de packs.
    #    Esto permite que buscar 0201001 devuelva también WOO-PACK-xxxx.
    try:
        token = q.lower().strip()
        resp = (
            session.client.table('v_inventory_hub_search_ranked')
            .select('*')
            .eq('search_token_norm', token)
            .order('match_priority', desc=False)
            .order('result_record_type', desc=False)
            .order('result_item_code', desc=False)
            .limit(limit)
            .execute()
        )
        ranked_rows = list(getattr(resp, 'data', None) or [])
        if ranked_rows:
            rows: list[dict[str, Any]] = []
            seen: set[int] = set()
            for ranked in ranked_rows:
                item_id = ranked.get('result_item_id')
                try:
                    key = int(item_id)
                except Exception:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                full = _fetch_inventory_full(key) or {}
                row = dict(full)
                row.setdefault('item_id', key)
                # setdefault no sustituye claves existentes con None/"". La vista
                # ranked sí trae el nombre correcto, así que rellenamos campos vacíos.
                if not str(row.get('name') or '').strip():
                    row['name'] = ranked.get('result_name') or row.get('woo_name') or ''
                if not str(row.get('family') or '').strip():
                    row['family'] = ranked.get('result_family')
                if not str(row.get('subgroup') or '').strip():
                    row['subgroup'] = ranked.get('result_subgroup')
                if row.get('woo_id') in (None, '', '-'):
                    row['woo_id'] = ranked.get('result_woo_id')
                if row.get('woo_parent_id') in (None, '', '-'):
                    row['woo_parent_id'] = ranked.get('result_woo_parent_id')
                if not str(row.get('woo_sku') or '').strip():
                    row['woo_sku'] = ranked.get('result_woo_sku')
                if not str(row.get('hub_item_code') or '').strip():
                    row['hub_item_code'] = ranked.get('result_item_code')
                if not str(row.get('item_record_type') or '').strip():
                    row['item_record_type'] = ranked.get('result_record_type') or 'simple'
                row['hub_search_result_name'] = ranked.get('result_name')
                row['hub_search_token'] = ranked.get('search_token')
                row['hub_search_code'] = ranked.get('result_item_code')
                row['hub_search_record_type'] = ranked.get('result_record_type')
                row['hub_search_related_code'] = ranked.get('related_item_code')
                row['hub_search_related_name'] = ranked.get('related_name')
                row['hub_search_relation_quantity'] = ranked.get('relation_quantity')
                row['hub_search_relation_type'] = ranked.get('relation_type')
                row['hub_search_match_type'] = ranked.get('best_token_type')
                row['hub_search_match_priority'] = ranked.get('match_priority')
                rows.append(row)
            if q.isdigit() or (q.startswith('-') and q[1:].isdigit()):
                normalized_component = _normalize_inventory_numeric_code(q)
                try:
                    component_resp = (
                        session.client.table('inventory_item_components')
                        .select('parent_item_code,component_item_code,component_name,quantity,relation_type')
                        .ilike('component_item_code', f'%{normalized_component}')
                        .eq('relation_type', 'component')
                        .limit(limit)
                        .execute()
                    )
                    component_rows = [
                        dict(row)
                        for row in (getattr(component_resp, 'data', None) or [])
                        if _normalize_inventory_numeric_code(row.get('component_item_code')) == normalized_component
                    ]
                    parent_codes = sorted({str(row.get('parent_item_code') or '').strip() for row in component_rows if row.get('parent_item_code')})
                    for col in ('hub_item_code', 'heca_reference'):
                        if not parent_codes:
                            break
                        try:
                            parent_resp = session.client.table('inventory_items').select(INVENTORY_SELECT_COLUMNS).in_(col, parent_codes).limit(limit).execute()
                        except Exception:
                            continue
                        for parent in getattr(parent_resp, 'data', None) or []:
                            item_id = parent.get('item_id')
                            try:
                                key = int(item_id)
                            except Exception:
                                key = hash(str(parent))
                            if key in seen:
                                continue
                            seen.add(key)
                            parent = dict(parent)
                            parent.setdefault('item_record_type', parent.get('item_record_type') or 'simple')
                            parent.setdefault('hub_item_code', parent.get('hub_item_code') or parent.get('heca_reference') or str(parent.get('item_id') or ''))
                            rows.append(parent)
                except Exception:
                    pass
            return _enrich_rows_with_component_summary(session, rows[:limit]) if enrich_components else rows[:limit]
    except Exception:
        # Si la vista no está creada o RLS la bloquea, seguimos con el buscador clásico.
        pass

    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(data: list[dict[str, Any]] | None) -> None:
        for row in data or []:
            item_id = row.get('item_id')
            try:
                key = int(item_id)
            except Exception:
                key = hash(str(row))
            if key in seen:
                continue
            seen.add(key)
            row = dict(row)
            row.setdefault('item_record_type', row.get('item_record_type') or 'simple')
            row.setdefault('hub_item_code', row.get('hub_item_code') or row.get('heca_reference') or str(row.get('item_id') or ''))
            rows.append(row)

    cols = INVENTORY_SELECT_COLUMNS
    # Búsqueda exacta numérica primero.
    if q.isdigit() or (q.startswith('-') and q[1:].isdigit()):
        n = int(q)
        for col in ('item_id', 'woo_id'):
            try:
                resp = session.client.table('inventory_items').select(cols).eq(col, n).limit(limit).execute()
                add(getattr(resp, 'data', None))
            except Exception:
                pass
        normalized_component = _normalize_inventory_numeric_code(q)
        if normalized_component:
            try:
                resp = (
                    session.client.table('inventory_item_components')
                    .select('parent_item_code,component_item_code,component_name,quantity,relation_type')
                    .ilike('component_item_code', f'%{normalized_component}')
                    .eq('relation_type', 'component')
                    .limit(limit)
                    .execute()
                )
                component_rows = [
                    dict(row)
                    for row in (getattr(resp, 'data', None) or [])
                    if _normalize_inventory_numeric_code(row.get('component_item_code')) == normalized_component
                ]
                parent_codes = sorted({str(row.get('parent_item_code') or '').strip() for row in component_rows if row.get('parent_item_code')})
                if parent_codes:
                    for col in ('hub_item_code', 'heca_reference'):
                        try:
                            parent_resp = session.client.table('inventory_items').select(cols).in_(col, parent_codes).limit(limit).execute()
                            add(getattr(parent_resp, 'data', None))
                        except Exception:
                            pass
            except Exception:
                pass
    # Búsqueda textual por campos principales. Varias queries para evitar depender de or_ con escaping.
    pattern = f'%{q}%'
    for col in ('name', 'woo_name', 'woo_sku', 'heca_reference', 'hub_item_code', 'base_item_code'):
        if len(rows) >= limit:
            break
        try:
            resp = session.client.table('inventory_items').select(cols).ilike(col, pattern).limit(limit).execute()
            add(getattr(resp, 'data', None))
        except Exception:
            continue
    return _enrich_rows_with_component_summary(session, rows[:limit]) if enrich_components else rows[:limit]

def format_cloud_inventory_search(rows: list[dict[str, Any]]) -> str:
    lines = [
        'RESULTADOS INVENTARIO SUPABASE',
        '=' * 40,
        'Copia item_id para actualizar inventario interno. WooCommerce no se toca.',
        '',
    ]
    if not rows:
        lines.append('Sin resultados.')
        return '\n'.join(lines)
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. item_id={row.get('item_id')} · {row.get('name') or row.get('woo_name') or '-'}")
        lines.append(
            f"   familia: {row.get('family') or '-'} · grupo: {row.get('subgroup') or '-'} "
            f"· medidas: {row.get('size') or '-'} · M3 calculo: {row.get('cubic_meters') or 'Pendiente'}"
        )
        lines.append(f"   stock tienda: {row.get('store_stock')} · almacén: {row.get('warehouse_stock')}")
        lines.append(f"   Woo: [{row.get('woo_item_kind') or '-'}] {row.get('woo_id') or '-'} · {row.get('woo_name') or '-'} · link: {row.get('woo_link_status') or '-'}")
        components = row.get('hub_pack_components_text')
        if components:
            lines.append(f"   contenido: {components}")
    return '\n'.join(lines)


def _fetch_inventory_item_by_id(session, item_id: int) -> dict[str, Any] | None:
    resp = session.client.table('inventory_items').select('*').eq('item_id', int(item_id)).limit(1).execute()
    rows = getattr(resp, 'data', None) or []
    return rows[0] if rows else None


def preview_internal_inventory_update(session, item_id: int, store_stock: Any = None, warehouse_stock: Any = None, notes: str = '') -> dict[str, Any]:
    before = _fetch_inventory_item_by_id(session, int(item_id))
    if before is None:
        raise CloudAuditError(f'No existe inventory_items.item_id={item_id} en Supabase.')
    new_store = _coerce_optional_float(store_stock)
    new_warehouse = _coerce_optional_float(warehouse_stock)
    if new_store is None and new_warehouse is None:
        raise CloudAuditError('Indica al menos stock tienda o stock almacén.')
    if new_store is not None and new_store < 0:
        raise CloudAuditError('Stock tienda no puede ser negativo.')
    if new_warehouse is not None and new_warehouse < 0:
        raise CloudAuditError('Stock almacén no puede ser negativo.')
    after = dict(before)
    if new_store is not None:
        after['store_stock'] = new_store
    if new_warehouse is not None:
        after['warehouse_stock'] = new_warehouse
    if notes:
        existing_notes = before.get('notes') or ''
        after['notes'] = (existing_notes + '\n' if existing_notes else '') + notes
    return {
        'item_id': int(item_id),
        'before': before,
        'after': after,
        'store_change': None if new_store is None else new_store - float(before.get('store_stock') or 0),
        'warehouse_change': None if new_warehouse is None else new_warehouse - float(before.get('warehouse_stock') or 0),
        'notes': notes,
    }


def format_internal_inventory_preview(preview: dict[str, Any]) -> str:
    b = preview.get('before') or {}
    a = preview.get('after') or {}
    lines = [
        'PREVIEW CAMBIO INVENTARIO INTERNO',
        '=' * 44,
        'No toca WooCommerce. Solo actualiza Supabase si confirmas.',
        '',
        f"Item ID: {preview.get('item_id')}",
        f"Nombre: {b.get('name') or b.get('woo_name') or '-'}",
        f"Woo: [{b.get('woo_item_kind') or '-'}] {b.get('woo_id') or '-'} · {b.get('woo_name') or '-'}",
        '',
        f"Stock tienda: {b.get('store_stock')} → {a.get('store_stock')}" + (f"  Δ {preview.get('store_change'):+.2f}" if preview.get('store_change') is not None else ''),
        f"Stock almacén: {b.get('warehouse_stock')} → {a.get('warehouse_stock')}" + (f"  Δ {preview.get('warehouse_change'):+.2f}" if preview.get('warehouse_change') is not None else ''),
    ]
    if preview.get('notes'):
        lines.extend(['', f"Nota a añadir: {preview.get('notes')}"])
    lines.extend(['', 'Se generará operation_snapshot + audit_log.'])
    return '\n'.join(lines)


def update_internal_inventory_item(session, item_id: int, store_stock: Any = None, warehouse_stock: Any = None, notes: str = '', settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    preview = preview_internal_inventory_update(session, item_id, store_stock, warehouse_stock, notes)
    before = preview['before']
    after = preview['after']
    operation_id = new_operation_id('INVREAL')
    now = datetime.now(timezone.utc).isoformat()

    snapshot = OperationSnapshot(
        operation_id=operation_id,
        module='inventory_items',
        action='internal_inventory_update',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        reason='Cambio real interno de inventario en Supabase antes de aplicar actualización.',
    )
    write_snapshot(session, snapshot)

    update_payload: dict[str, Any] = {
        'updated_at': now,
        'updated_by': session.user_id,
        'source_row': {
            'operation_id': operation_id,
            'updated_by_email': session.email,
            'role': session.role,
            'machine': settings.machine_name,
            'inventory_change': True,
            'note': 'Cambio interno Supabase. WooCommerce no fue tocado.',
        },
    }
    if after.get('store_stock') != before.get('store_stock'):
        update_payload['store_stock'] = after.get('store_stock')
    if after.get('warehouse_stock') != before.get('warehouse_stock'):
        update_payload['warehouse_stock'] = after.get('warehouse_stock')
    if after.get('notes') != before.get('notes'):
        update_payload['notes'] = after.get('notes')

    resp = session.client.table('inventory_items').update(update_payload).eq('item_id', int(item_id)).execute()
    written_rows = getattr(resp, 'data', None) or []
    written = written_rows[0] if written_rows else {**before, **update_payload}

    event = AuditEvent(
        operation_id=operation_id,
        module='inventory_items',
        action='internal_inventory_update',
        status='OK',
        severity='INFO',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        after_data=_json_safe(written),
        message='Inventario interno actualizado en Supabase. WooCommerce no fue tocado.',
    )
    write_audit_event(session, event, settings)
    return {'operation_id': operation_id, 'before': before, 'after': written, 'preview': preview}



def fetch_inventory_item_history(session, item_id: int, limit: int = 80) -> list[dict[str, Any]]:
    """Devuelve historial real conocido para un item.

    Lee inventory_change_history si existe y audit_logs como fuente de caja negra.
    No fabrica puntos: si no hay historial real, devuelve lista vacia.
    """
    limit = max(1, min(int(limit or 80), 300))
    item_id_text = str(item_id)
    events: list[dict[str, Any]] = []

    def add_change(created_at: Any, operation_id: Any, source: str, field: str, before: Any, after: Any, message: str = '') -> None:
        if before == after:
            return
        events.append({
            'created_at': created_at,
            'operation_id': operation_id,
            'source': source,
            'field': field,
            'before': before,
            'after': after,
            'message': message,
        })

    # Tabla local/operativa de historico si esta instalada.
    try:
        resp = (
            session.client.table('inventory_change_history')
            .select('*')
            .eq('item_id', int(item_id))
            .order('created_at', desc=True)
            .limit(limit)
            .execute()
        )
        for row in getattr(resp, 'data', None) or []:
            field = row.get('field') or row.get('field_name') or row.get('changed_field') or row.get('change_type') or 'inventario'
            before = row.get('old_value') if 'old_value' in row else row.get('before_value')
            after = row.get('new_value') if 'new_value' in row else row.get('after_value')
            add_change(row.get('created_at'), row.get('operation_id') or row.get('id'), 'inventory_change_history', str(field), before, after, row.get('message') or row.get('notes') or '')
    except Exception:
        pass

    # Caja negra: cambios que tengan entity_id del item o before/after con item_id.
    try:
        resp = (
            session.client.table('audit_logs')
            .select('created_at,operation_id,module,action,severity,status,entity_type,entity_id,before_data,after_data,message')
            .order('created_at', desc=True)
            .limit(limit)
            .execute()
        )
        rows = getattr(resp, 'data', None) or []
    except Exception:
        rows = []
    for row in rows:
        before_data = row.get('before_data') or {}
        after_data = row.get('after_data') or {}
        if not isinstance(before_data, dict):
            before_data = {}
        if not isinstance(after_data, dict):
            after_data = {}
        row_entity = str(row.get('entity_id') or '')
        before_id = str(before_data.get('item_id') or '')
        after_id = str(after_data.get('item_id') or '')
        if item_id_text not in {row_entity, before_id, after_id}:
            continue
        for field in sorted(set(before_data.keys()) | set(after_data.keys())):
            if field in {'updated_at', 'updated_by', 'source_row'}:
                continue
            before = before_data.get(field)
            after = after_data.get(field)
            add_change(row.get('created_at'), row.get('operation_id'), f"{row.get('module') or ''}.{row.get('action') or ''}".strip('.'), field, before, after, row.get('message') or '')

    events.sort(key=lambda row: str(row.get('created_at') or ''), reverse=True)
    return events[:limit]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value in (None, ''):
            continue
        try:
            return int(str(value).strip())
        except Exception:
            continue
    return None


def _select_single_inventory_item(session, column: str, value: Any) -> tuple[dict[str, Any] | None, str]:
    if value in (None, ''):
        return None, ''
    try:
        resp = (
            session.client.table('inventory_items')
            .select('item_id,heca_reference,woo_sku,woo_id,woo_parent_id,name')
            .eq(column, value)
            .limit(2)
            .execute()
        )
        rows = getattr(resp, 'data', None) or []
    except Exception as exc:
        return None, f'No se pudo resolver inventory_items por {column}={value}: {exc}'
    if len(rows) == 1:
        return rows[0], ''
    if len(rows) > 1:
        return None, f'Resolucion ambigua de inventory_items por {column}={value}.'
    return None, ''


def _select_inventory_item_by_id(session, item_id: int) -> dict[str, Any]:
    resp = (
        session.client.table('inventory_items')
        .select('item_id,name,heca_reference,woo_sku,woo_id,woo_parent_id,woo_price,source_row')
        .eq('item_id', int(item_id))
        .limit(1)
        .execute()
    )
    rows = getattr(resp, 'data', None) or []
    if not rows:
        raise CloudAuditError(f'No existe inventory_items.item_id={item_id} para sincronizar precio Woo.')
    return rows[0]


def resolve_inventory_item_id_for_woo_price_event(
    session,
    *,
    proposal: dict[str, Any] | None = None,
    cloud_item: dict[str, Any] | None = None,
    woo_id: Any = None,
) -> dict[str, Any]:
    proposal = _as_dict(proposal)
    cloud_item = _as_dict(cloud_item)
    source_row = _as_dict(proposal.get('source_row'))
    item_snapshot = _as_dict(source_row.get('item_snapshot'))
    diagnostics: list[str] = []

    direct_item_id = _first_int(
        proposal.get('item_id'),
        proposal.get('inventory_item_id'),
        source_row.get('item_id'),
        source_row.get('inventory_item_id'),
        item_snapshot.get('item_id'),
        item_snapshot.get('inventory_item_id'),
        cloud_item.get('item_id'),
    )
    if direct_item_id is not None:
        return {'item_id': direct_item_id, 'strategy': 'direct_item_id', 'source': 'direct_item_id', 'diagnostics': diagnostics}

    resolved_woo_id = _first_int(woo_id, proposal.get('item_woo_id'), proposal.get('local_id'), item_snapshot.get('woo_id'), cloud_item.get('woo_id'))
    if resolved_woo_id is not None:
        row, diagnostic = _select_single_inventory_item(session, 'woo_id', resolved_woo_id)
        if row:
            return {'item_id': row.get('item_id'), 'strategy': 'inventory_items.woo_id', 'source': 'inventory_items.woo_id', 'row': row, 'diagnostics': diagnostics}
        if diagnostic:
            diagnostics.append(diagnostic)

    for value in (
        item_snapshot.get('heca_reference'),
        source_row.get('heca_reference'),
        proposal.get('heca_reference'),
        item_snapshot.get('sku'),
        item_snapshot.get('woo_sku'),
        cloud_item.get('sku'),
        cloud_item.get('woo_sku'),
    ):
        text = str(value or '').strip()
        if not text:
            continue
        for column in ('heca_reference', 'woo_sku'):
            row, diagnostic = _select_single_inventory_item(session, column, text)
            if row:
                return {'item_id': row.get('item_id'), 'strategy': f'inventory_items.{column}', 'source': f'inventory_items.{column}', 'row': row, 'diagnostics': diagnostics}
            if diagnostic:
                diagnostics.append(diagnostic)

    diagnostics.append('No se pudo resolver inventory_items.item_id para evento Woo; no se inventa asociacion.')
    return {'item_id': None, 'strategy': '', 'source': '', 'diagnostics': diagnostics}


def _history_insert_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    item_name = str(payload.get('item_name') or '')
    old_value = payload.get('old_value')
    new_value = payload.get('new_value')
    message = str(payload.get('message') or payload.get('notes') or '')
    action = str(payload.get('action') or '')
    metadata = _json_safe(payload.get('metadata') or {})
    source = str(payload.get('source') or 'woocommerce_publish')
    field = str(payload.get('field') or 'woo_price')
    operation_id = payload.get('operation_id')
    item_id = payload.get('item_id')
    return [
        {
            'item_id': item_id,
            'field': field,
            'field_name': field,
            'old_value': old_value,
            'new_value': new_value,
            'operation_id': operation_id,
            'message': message,
            'notes': message,
            'source': source,
            'change_source': source,
            'action': action,
            'metadata': metadata,
            'item_name': item_name,
        },
        {
            'item_id': item_id,
            'field': field,
            'old_value': old_value,
            'new_value': new_value,
            'operation_id': operation_id,
            'message': message,
            'notes': message,
            'source': source,
            'action': action,
            'metadata': metadata,
        },
        {
            'item_id': item_id,
            'field_name': field,
            'old_value': old_value,
            'new_value': new_value,
            'operation_id': operation_id,
            'notes': message,
            'change_source': source,
            'item_name': item_name,
        },
        {
            'item_id': item_id,
            'field': field,
            'old_value': old_value,
            'new_value': new_value,
            'operation_id': operation_id,
            'message': message,
        },
    ]


def record_woo_price_inventory_history(
    session,
    *,
    operation_id: str,
    item_id: Any,
    before: Any,
    after: Any,
    action: str,
    message: str = '',
    metadata: dict[str, Any] | None = None,
    item_name: str = '',
) -> dict[str, Any]:
    resolved_item_id = _first_int(item_id)
    if resolved_item_id is None:
        return {'inserted': False, 'reason': 'missing_item_id'}
    if before == after:
        return {'inserted': False, 'reason': 'unchanged'}

    try:
        existing = (
            session.client.table('inventory_change_history')
            .select('id,operation_id')
            .eq('operation_id', operation_id)
            .eq('item_id', resolved_item_id)
            .limit(1)
            .execute()
        )
        existing_rows = getattr(existing, 'data', None) or []
        for row in existing_rows:
            row_field = str(row.get('field') or row.get('field_name') or row.get('changed_field') or '').lower()
            if row_field in {'', 'woo_price', 'precio woo'}:
                return {'inserted': False, 'reason': 'duplicate', 'item_id': resolved_item_id, 'row': row}
    except Exception as exc:
        raise CloudAuditError(f'No se pudo comprobar idempotencia de inventory_change_history: {exc}') from exc

    payload = {
        'item_id': resolved_item_id,
        'item_name': item_name,
        'field': 'woo_price',
        'old_value': None if before is None else str(before),
        'new_value': None if after is None else str(after),
        'operation_id': operation_id,
        'message': message or action,
        'notes': message or action,
        'source': 'woocommerce_publish',
        'action': action,
        'metadata': _json_safe(metadata or {}),
    }
    errors: list[str] = []
    for candidate in _history_insert_candidates(payload):
        try:
            resp = session.client.table('inventory_change_history').insert(candidate).execute()
            rows = getattr(resp, 'data', None) or []
            return {'inserted': True, 'item_id': resolved_item_id, 'row': rows[0] if rows else candidate}
        except Exception as exc:
            errors.append(str(exc))
    raise CloudAuditError('No se pudo insertar inventory_change_history para precio Woo: ' + ' | '.join(errors))


def sync_woocommerce_price_inventory_state(
    session,
    *,
    operation_id: str,
    proposal: dict[str, Any] | None,
    cloud_item: dict[str, Any] | None,
    woo_id: Any,
    before_price: Any,
    verified_price: Any,
    action: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolution = resolve_inventory_item_id_for_woo_price_event(session, proposal=proposal, cloud_item=cloud_item, woo_id=woo_id)
    item_id = _first_int(resolution.get('item_id'))
    if item_id is None:
        raise CloudAuditError('No se pudo resolver inventory_items.item_id para sincronizar precio Woo: ' + '; '.join(resolution.get('diagnostics') or []))

    before_item = _select_inventory_item_by_id(session, item_id)
    previous_inventory_price = before_item.get('woo_price')
    new_price_text = None if verified_price is None else str(verified_price)
    source_row = before_item.get('source_row') if isinstance(before_item.get('source_row'), dict) else {}
    update_payload = {
        'woo_price': new_price_text,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': getattr(session, 'user_id', None),
        'source_row': {
            **source_row,
            'woo_price_sync': True,
            'woo_price_sync_operation_id': operation_id,
            'woo_price_sync_action': action,
            'woo_price_sync_message': message,
            'woo_price_sync_resolution': _json_safe(resolution),
        },
    }
    update_errors: list[str] = []
    for payload in (
        update_payload,
        {key: value for key, value in update_payload.items() if key != 'source_row'},
        {'woo_price': new_price_text},
    ):
        try:
            resp = session.client.table('inventory_items').update(payload).eq('item_id', item_id).execute()
            rows = getattr(resp, 'data', None) or []
            if rows:
                written = rows[0]
            else:
                check = session.client.table('inventory_items').select('item_id,woo_price').eq('item_id', item_id).limit(1).execute()
                check_rows = getattr(check, 'data', None) or []
                written = check_rows[0] if check_rows else {}
            if str((written or {}).get('woo_price') or '') == str(new_price_text or ''):
                history = record_woo_price_inventory_history(
                    session,
                    operation_id=operation_id,
                    item_id=item_id,
                    before=before_price if before_price is not None else previous_inventory_price,
                    after=new_price_text,
                    action=action,
                    message=message,
                    metadata={**(metadata or {}), 'resolution': resolution, 'inventory_before': _json_safe(before_item)},
                    item_name=str(before_item.get('name') or ''),
                )
                return {
                    'ok': True,
                    'item_id': item_id,
                    'resolution': resolution,
                    'inventory_before': before_item,
                    'inventory_after': written or {'item_id': item_id, 'woo_price': new_price_text},
                    'history': history,
                }
            update_errors.append(f"inventory_items.item_id={item_id} no confirmo woo_price={new_price_text!r}; respuesta={written!r}")
        except Exception as exc:
            update_errors.append(str(exc))
    raise CloudAuditError('Woo verificado, pero fallo sincronizacion de inventory_items.woo_price: ' + ' | '.join(update_errors))


def preview_inventory_item_field_update(session, item_id: int, changes: dict[str, Any]) -> dict[str, Any]:
    before = _fetch_inventory_item_by_id(session, int(item_id))
    if before is None:
        raise CloudAuditError(f'No existe inventory_items.item_id={item_id} en Supabase.')
    safe_changes: dict[str, Any] = {}
    change_rows: list[dict[str, Any]] = []
    for field, raw_value in (changes or {}).items():
        if field not in INVENTORY_EDITABLE_FIELDS:
            raise CloudAuditError(f'Campo no editable desde Inventario: {field}')
        new_value = _normalize_inventory_edit_value(field, raw_value)
        old_value = before.get(field)
        if field in NUMERIC_INVENTORY_FIELDS:
            old_compare = _coerce_optional_float(old_value)
            new_compare = new_value
        else:
            old_compare = str(old_value or '').strip() or None
            new_compare = str(new_value or '').strip() or None
        if old_compare == new_compare:
            continue
        if field in {'store_stock', 'warehouse_stock'} and new_value is not None and float(new_value) < 0:
            raise CloudAuditError(f'{field} no puede ser negativo.')
        safe_changes[field] = new_value
        change_rows.append({'field': field, 'before': old_value, 'after': new_value})
    if not safe_changes:
        raise CloudAuditError('No hay cambios para aplicar.')
    after = dict(before)
    after.update(safe_changes)
    return {'item_id': int(item_id), 'before': before, 'after': after, 'changes': change_rows}


def update_inventory_item_fields(session, item_id: int, changes: dict[str, Any], notes: str = '', settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    preview = preview_inventory_item_field_update(session, item_id, changes)
    before = preview['before']
    after = preview['after']
    safe_changes = {row['field']: row['after'] for row in preview['changes']}
    operation_id = new_operation_id('INVITEM')
    now = datetime.now(timezone.utc).isoformat()

    snapshot = OperationSnapshot(
        operation_id=operation_id,
        module='inventory_items',
        action='inventory_item_field_update',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        reason='Snapshot antes de modificar campos internos del item desde UI ERP.',
    )
    write_snapshot(session, snapshot)

    update_payload = dict(safe_changes)
    update_payload['updated_at'] = now
    update_payload['updated_by'] = session.user_id
    update_payload['source_row'] = {
        'operation_id': operation_id,
        'updated_by_email': session.email,
        'role': session.role,
        'machine': settings.machine_name,
        'inventory_item_field_update': True,
        'note': notes or 'Cambio interno de item desde UI ERP. WooCommerce no fue tocado.',
    }

    resp = session.client.table('inventory_items').update(update_payload).eq('item_id', int(item_id)).execute()
    written_rows = getattr(resp, 'data', None) or []
    written = written_rows[0] if written_rows else {**before, **update_payload}

    event = AuditEvent(
        operation_id=operation_id,
        module='inventory_items',
        action='inventory_item_field_update',
        status='OK',
        severity='INFO',
        entity_type='inventory_item',
        entity_id=str(item_id),
        before_data=_json_safe(before),
        after_data=_json_safe(written),
        message='Campos internos del item actualizados desde UI ERP. WooCommerce no fue tocado.',
    )
    write_audit_event(session, event, settings)
    return {'operation_id': operation_id, 'before': before, 'after': written, 'preview': preview}


def run_cloud_search_inventory(query: str, limit: int = 25) -> int:
    try:
        session, _settings = _login_from_console()
        rows = search_cloud_inventory_items(session, query, limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print(format_cloud_inventory_search(rows))
    return 0


def run_cloud_inventory_update_internal(item_id: int, store_stock: str = '', warehouse_stock: str = '', notes: str = '', execute: bool = False) -> int:
    try:
        session, settings = _login_from_console()
        preview = preview_internal_inventory_update(session, item_id, store_stock or None, warehouse_stock or None, notes)
        print(format_internal_inventory_preview(preview))
        if not execute:
            print('\nPREVIEW ONLY: no se aplicó nada. Repite con --execute para actualizar Supabase.')
            return 0
        typed = input('\nEscribe APLICAR para confirmar cambio interno de inventario: ').strip().upper()
        if typed != 'APLICAR':
            print('Cancelado. No se aplicó nada.')
            return 1
        result = update_internal_inventory_item(session, item_id, store_stock or None, warehouse_stock or None, notes, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f'ERROR: {exc}')
        return 2
    except Exception as exc:
        print(f'ERROR inesperado: {exc}')
        return 2
    print('\nCAMBIO INVENTARIO INTERNO APLICADO')
    print('=' * 42)
    print(f"operation_id: {result['operation_id']}")
    print(f'item_id: {item_id}')
    print('Supabase actualizado. WooCommerce no fue tocado.')
    print('Caja negra: audit_log + operation_snapshot generados.')
    return 0


coerce_optional_float = _coerce_optional_float
fetch_inventory_item_by_id = _fetch_inventory_item_by_id


# =====================================================
# ERP - Crear nuevo artículo en inventory_items
# =====================================================

CREATE_INVENTORY_ITEM_FIELDS = {
    'item_id',
    'name',
    'family',
    'subgroup',
    'size',
    'materials',
    'cubic_meters',
    'rotation_c',
    'packages',
    'primary_supplier_price',
    'pascal_price',
    'store_stock',
    'warehouse_stock',
    'commercial_status',
    'heca_reference',
    'woo_sku',
    'notes',
}


def _normalize_new_inventory_item_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    try:
        item_id = int(str(data.get('item_id') or '').strip())
    except Exception:
        raise CloudAuditError('ID / Referencia inválida. Debe ser numérica.')
    if item_id <= 0:
        raise CloudAuditError('ID / Referencia debe ser mayor que 0.')

    name = str(data.get('name') or '').strip()
    if not name:
        raise CloudAuditError('El nombre del artículo es obligatorio.')

    payload['item_id'] = item_id
    payload['name'] = name

    for field in ('family', 'subgroup', 'size', 'materials', 'commercial_status', 'heca_reference', 'woo_sku', 'notes'):
        value = data.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            payload[field] = text

    payload.setdefault('commercial_status', 'Normal')
    payload.setdefault('heca_reference', str(item_id).zfill(7))

    for field in ('cubic_meters', 'rotation_c', 'primary_supplier_price', 'pascal_price', 'store_stock', 'warehouse_stock'):
        value = data.get(field)
        if value in (None, ''):
            continue
        number = _coerce_optional_float(value)
        if number is not None:
            if field in {'primary_supplier_price', 'pascal_price', 'store_stock', 'warehouse_stock'} and number < 0:
                raise CloudAuditError(f'{field} no puede ser negativo.')
            payload[field] = number

    packages = data.get('packages')
    if packages not in (None, ''):
        try:
            pkg = int(float(str(packages).replace(',', '.')))
        except Exception:
            raise CloudAuditError('Bultos debe ser numérico.')
        if pkg <= 0:
            raise CloudAuditError('Bultos debe ser mayor que 0.')
        payload['packages'] = pkg
    else:
        payload['packages'] = 1

    return payload


def preview_create_cloud_inventory_item(session, data: dict[str, Any]) -> dict[str, Any]:
    payload = _normalize_new_inventory_item_payload(data)
    existing = _fetch_inventory_item_by_id(session, int(payload['item_id']))
    return {
        'exists': existing is not None,
        'existing': existing,
        'payload': payload,
    }


def create_cloud_inventory_item(session, data: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    """Crea un artículo nuevo en inventory_items.

    No toca WooCommerce. No toca stock externo. Genera snapshot + audit log.
    """
    settings = settings or load_settings()
    preview = preview_create_cloud_inventory_item(session, data)
    if preview.get('exists'):
        existing = preview.get('existing') or {}
        raise CloudAuditError(f"Ya existe inventory_items.item_id={existing.get('item_id')} · {existing.get('name') or '-'}")

    payload = dict(preview['payload'])
    operation_id = new_operation_id('INVITEM')
    now = datetime.now(timezone.utc).isoformat()
    payload['created_at'] = now
    payload['updated_at'] = now
    payload['updated_by'] = session.user_id
    payload['source_row'] = {
        'operation_id': operation_id,
        'created_by_email': session.email,
        'role': session.role,
        'machine': settings.machine_name,
        'created_from': 'UI ERP Inventario > Crear nuevo artículo',
        'note': 'Creación manual. WooCommerce no fue tocado.',
    }

    snapshot = OperationSnapshot(
        operation_id=operation_id,
        module='inventory_items',
        action='create_inventory_item',
        entity_type='inventory_item',
        entity_id=str(payload['item_id']),
        before_data={'created_payload': _json_safe(payload)},
        reason='Creación manual de artículo nuevo en inventory_items desde UI ERP.',
    )
    try:
        write_snapshot(session, snapshot)
    except Exception:
        pass

    try:
        resp = session.client.table('inventory_items').insert(payload).execute()
    except Exception as exc:
        message = str(exc)
        # Algunos esquemas pueden no tener source_row/created_at/updated_by.
        optional = ('source_row', 'created_at', 'updated_by')
        payload2 = dict(payload)
        changed = False
        for field in optional:
            if field in message and field in payload2:
                payload2.pop(field, None)
                changed = True
        if changed:
            resp = session.client.table('inventory_items').insert(payload2).execute()
            payload = payload2
        else:
            raise
    written_rows = getattr(resp, 'data', None) or []
    written = written_rows[0] if written_rows else payload

    event = AuditEvent(
        operation_id=operation_id,
        module='inventory_items',
        action='create_inventory_item',
        status='OK',
        severity='INFO',
        entity_type='inventory_item',
        entity_id=str(payload.get('item_id')),
        before_data=None,
        after_data=_json_safe(written),
        message='Artículo creado manualmente en inventory_items. WooCommerce no fue tocado.',
    )
    try:
        write_audit_event(session, event, settings)
    except Exception:
        pass
    return {'operation_id': operation_id, 'after': written, 'preview': preview}

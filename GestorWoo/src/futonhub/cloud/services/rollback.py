from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from futonhub.cloud.audit import CloudAuditError

def json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}

# =====================================================
# v12.4 · Rollback lógico desde operation_snapshot
# =====================================================

ROLLBACK_ENTITY_SPECS = {
    'inventory_item': {
        'table': 'inventory_items',
        'key': 'item_id',
        'label': 'Inventario interno',
        'safe_note': 'Solo revierte Supabase. WooCommerce no se toca.',
    },
    'price_change_proposal': {
        'table': 'price_change_proposals',
        'key': 'id',
        'label': 'Propuesta de precio',
        'safe_note': 'Solo revierte el estado/datos internos de la propuesta en Supabase. WooCommerce no se toca.',
    },
    'business_constant': {
        'table': 'business_constants',
        'key': 'key',
        'label': 'Constante del negocio',
        'safe_note': 'Revierte una constante en Supabase. Revisa cálculos después si era una constante real.',
    },
}


def _require_admin_role(session) -> None:
    if (session.role or '').strip().lower() != 'admin':
        raise CloudAuditError('Solo admin puede ejecutar esta operación.')


def _fetch_snapshot_by_operation_id(session, operation_id: str) -> dict[str, Any]:
    op = (operation_id or '').strip()
    if not op:
        raise CloudAuditError('Indica operation_id del snapshot.')
    # v12.4: preferimos RPC admin para evitar falsos bloqueos si el subcliente REST
    # pierde el token. Si el SQL de v12.4 aún no existe, se usa fallback directo.
    try:
        resp = session.client.rpc(
            'futonhub_read_snapshot_by_operation_id',
            {'p_user_id': session.user_id, 'p_operation_id': op},
        ).execute()
        rows = getattr(resp, 'data', None) or []
        if rows:
            return rows[0]
    except Exception:
        pass
    resp = (
        session.client.table('operation_snapshots')
        .select('*')
        .eq('operation_id', op)
        .order('created_at', desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, 'data', None) or []
    if not rows:
        raise CloudAuditError(f'No se encontró operation_snapshot con operation_id={op}.')
    return rows[0]


def list_rollback_candidates(session, limit: int = 30) -> list[dict[str, Any]]:
    _require_admin_role(session)
    limit = max(1, min(int(limit or 30), 100))
    resp = (
        session.client.table('operation_snapshots')
        .select('id,created_at,operation_id,module,action,entity_type,entity_id,reason')
        .order('created_at', desc=True)
        .limit(limit)
        .execute()
    )
    rows = getattr(resp, 'data', None) or []
    supported = set(ROLLBACK_ENTITY_SPECS)
    for row in rows:
        row['rollback_supported'] = (row.get('entity_type') in supported)
    return rows


def format_rollback_candidates(rows: list[dict[str, Any]]) -> str:
    lines = [
        'SNAPSHOTS CANDIDATOS A ROLLBACK',
        '=' * 48,
        'Solo admin. Preview obligatorio antes de revertir. WooCommerce no se toca.',
        '',
    ]
    if not rows:
        lines.append('Sin snapshots visibles.')
        return '\n'.join(lines)
    for i, row in enumerate(rows, start=1):
        support = 'OK' if row.get('rollback_supported') else 'NO SOPORTADO'
        lines.append(
            f"{i}. {support} · {row.get('created_at') or ''} · {row.get('operation_id') or ''}"
        )
        lines.append(
            f"   {row.get('module') or ''}.{row.get('action') or ''} · {row.get('entity_type') or ''}:{row.get('entity_id') or ''}"
        )
        if row.get('reason'):
            lines.append(f"   {row.get('reason')}")
    return '\n'.join(lines)


def rollback_target_from_snapshot(snapshot: dict[str, Any]) -> tuple[dict[str, Any], str, str, Any]:
    entity_type = snapshot.get('entity_type')
    spec = ROLLBACK_ENTITY_SPECS.get(entity_type)
    if not spec:
        raise CloudAuditError(f"Rollback no soportado para entity_type={entity_type!r}.")
    before = snapshot.get('before_data') or {}
    if not isinstance(before, dict) or not before:
        raise CloudAuditError('El snapshot no contiene before_data válido para restaurar.')
    table = spec['table']
    key = spec['key']
    key_value = before.get(key)
    if key_value in (None, ''):
        # Fallback para snapshots antiguos que guardaron entity_id como identificador.
        key_value = snapshot.get('entity_id')
    if key_value in (None, ''):
        raise CloudAuditError(f'No se pudo determinar la clave {key} para restaurar {entity_type}.')
    return before, table, key, key_value


def _fetch_current_row_for_rollback(session, table: str, key: str, key_value: Any) -> dict[str, Any] | None:
    resp = session.client.table(table).select('*').eq(key, key_value).limit(1).execute()
    rows = getattr(resp, 'data', None) or []
    return rows[0] if rows else None


def rollback_update_payload(table: str, key: str, before: dict[str, Any], *, user_id: str | None = None) -> dict[str, Any]:
    payload = dict(before)
    # Evita cambiar claves primarias o metadatos conflictivos. Dejamos created_at quieto.
    for protected in {'id', key, 'created_at'}:
        payload.pop(protected, None)
    # Marcamos trazabilidad del rollback si la tabla lo soporta.
    if table in {'inventory_items', 'business_constants'}:
        payload['updated_at'] = datetime.now(timezone.utc).isoformat()
    if user_id and table in {'inventory_items', 'business_constants'}:
        payload['updated_by'] = user_id
    return json_safe(payload) or {}


def preview_rollback_from_snapshot(session, operation_id: str) -> dict[str, Any]:
    _require_admin_role(session)
    snapshot = _fetch_snapshot_by_operation_id(session, operation_id)
    before, table, key, key_value = _rollback_target_from_snapshot(snapshot)
    current = _fetch_current_row_for_rollback(session, table, key, key_value)
    if current is None:
        raise CloudAuditError(f'No existe fila actual en {table} donde {key}={key_value}. No se puede revertir automáticamente.')
    spec = ROLLBACK_ENTITY_SPECS.get(snapshot.get('entity_type')) or {}
    return {
        'snapshot': snapshot,
        'table': table,
        'key': key,
        'key_value': key_value,
        'before_data': before,
        'current_data': current,
        'entity_label': spec.get('label') or snapshot.get('entity_type'),
        'safe_note': spec.get('safe_note') or 'WooCommerce no se toca.',
    }


def short_json_diff(before: dict[str, Any], current: dict[str, Any], max_items: int = 12) -> list[str]:
    keys = sorted(set(before.keys()) | set(current.keys()))
    lines: list[str] = []
    for key in keys:
        if before.get(key) != current.get(key):
            lines.append(f"{key}: actual={current.get(key)!r} → restaurar={before.get(key)!r}")
        if len(lines) >= max_items:
            remaining = len([k for k in keys if before.get(k) != current.get(k)]) - len(lines)
            if remaining > 0:
                lines.append(f"... y {remaining} cambio(s) más")
            break
    return lines


def format_rollback_preview(preview: dict[str, Any]) -> str:
    snap = preview.get('snapshot') or {}
    current = preview.get('current_data') or {}
    before = preview.get('before_data') or {}
    diff = _short_json_diff(before, current)
    lines = [
        'PREVIEW ROLLBACK DESDE SNAPSHOT',
        '=' * 48,
        'Solo admin. Revertirá datos internos en Supabase.',
        'WooCommerce NO se toca.',
        '',
        f"Snapshot operation_id: {snap.get('operation_id')}",
        f"Origen: {snap.get('module')}.{snap.get('action')}",
        f"Entidad: {snap.get('entity_type')}:{snap.get('entity_id')}",
        f"Tabla destino: {preview.get('table')} · {preview.get('key')}={preview.get('key_value')}",
        f"Tipo: {preview.get('entity_label')}",
        '',
        preview.get('safe_note') or 'WooCommerce no se toca.',
        '',
        'Cambios que se revertirían:',
    ]
    if diff:
        lines.extend(f'- {line}' for line in diff)
    else:
        lines.append('- No se detectan diferencias entre actual y snapshot previo.')
    lines.extend(['', 'Para ejecutar por consola: añade --execute --confirm REVERTIR'])
    return '\n'.join(lines)


def execute_rollback_from_snapshot(session, operation_id: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    preview = preview_rollback_from_snapshot(session, operation_id)
    snapshot = preview['snapshot']
    current = preview['current_data']
    before = preview['before_data']
    table = preview['table']
    key = preview['key']
    key_value = preview['key_value']
    rollback_operation_id = new_operation_id('ROLLBACK')

    # Snapshot del estado justo antes de revertir, para poder deshacer el rollback si hiciera falta.
    rollback_snapshot = OperationSnapshot(
        operation_id=rollback_operation_id,
        module='rollback',
        action='rollback_from_snapshot',
        entity_type=snapshot.get('entity_type') or 'unknown',
        entity_id=str(snapshot.get('entity_id') or key_value),
        before_data=json_safe(current),
        reason=f"Estado actual antes de revertir usando snapshot {snapshot.get('operation_id')}. WooCommerce no se toca.",
    )
    write_snapshot(session, rollback_snapshot)

    payload = _rollback_update_payload(table, key, before, user_id=session.user_id)
    if not payload:
        raise CloudAuditError('No hay datos restaurables en el snapshot después de limpiar claves protegidas.')
    resp = session.client.table(table).update(payload).eq(key, key_value).execute()
    written_rows = getattr(resp, 'data', None) or []
    restored = written_rows[0] if written_rows else {**current, **payload}

    event = AuditEvent(
        operation_id=rollback_operation_id,
        module='rollback',
        action='rollback_from_snapshot',
        status='ROLLED_BACK',
        severity='WARNING',
        entity_type=snapshot.get('entity_type') or 'unknown',
        entity_id=str(snapshot.get('entity_id') or key_value),
        before_data=json_safe(current),
        after_data=json_safe(restored),
        message=f"Rollback interno ejecutado desde snapshot {snapshot.get('operation_id')}. WooCommerce no fue tocado.",
    )
    write_audit_event(session, event, settings)
    return {
        'operation_id': rollback_operation_id,
        'source_operation_id': snapshot.get('operation_id'),
        'table': table,
        'key': key,
        'key_value': key_value,
        'before_current': current,
        'restored': restored,
        'preview': preview,
    }


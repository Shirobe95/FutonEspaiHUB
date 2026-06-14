from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from gestorwoo.config import Settings, load_settings
from gestorwoo.cloud.auth import CloudUserSession


VALID_SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}
VALID_STATUSES = {"STARTED", "OK", "ERROR", "BLOCKED", "REJECTED", "ROLLED_BACK", "TEST"}


def new_operation_id(prefix: str = "OP") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8].upper()}"


@dataclass(frozen=True)
class AuditEvent:
    module: str
    action: str
    status: str
    severity: str = "INFO"
    entity_type: str | None = None
    entity_id: str | None = None
    before_data: dict[str, Any] | None = None
    after_data: dict[str, Any] | None = None
    message: str = ""
    error_detail: str = ""
    operation_id: str = field(default_factory=new_operation_id)


@dataclass(frozen=True)
class OperationSnapshot:
    operation_id: str
    module: str
    action: str
    entity_type: str
    entity_id: str
    before_data: dict[str, Any]
    reason: str = ""


class CloudAuditError(RuntimeError):
    pass


def _clean_json(value: Any) -> Any:
    """Convierte datos Python a JSON seguro para Supabase/Postgres."""
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"_raw": str(value)}


def event_to_payload(
    event: AuditEvent,
    *,
    user_id: str | None,
    user_email: str | None = None,
    role: str | None = None,
    machine_name: str,
    device_id: str | None = None,
) -> dict[str, Any]:
    severity = (event.severity or "INFO").upper()
    status = (event.status or "OK").upper()
    if severity not in VALID_SEVERITIES:
        severity = "INFO"
    if status not in VALID_STATUSES:
        # La tabla acepta texto libre en status, pero normalizamos para que la caja negra sea legible.
        status = event.status or "OK"

    return {
        "operation_id": event.operation_id,
        "user_id": user_id,
        "user_email": user_email,
        "role": role,
        "device_id": device_id,
        "machine_name": machine_name,
        "module": event.module,
        "action": event.action,
        "status": status,
        "severity": severity,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "before_data": _clean_json(event.before_data),
        "after_data": _clean_json(event.after_data),
        "message": event.message,
        "error_detail": event.error_detail,
    }


def snapshot_to_payload(snapshot: OperationSnapshot, *, user_id: str | None) -> dict[str, Any]:
    return {
        "operation_id": snapshot.operation_id,
        "user_id": user_id,
        "module": snapshot.module,
        "action": snapshot.action,
        "entity_type": snapshot.entity_type,
        "entity_id": snapshot.entity_id,
        "before_data": _clean_json(snapshot.before_data) or {},
        "reason": snapshot.reason,
    }


def _extract_rpc_row(response: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    data = getattr(response, "data", None)
    if isinstance(data, list) and data:
        first = data[0]
        return first if isinstance(first, dict) else {"result": first, **fallback}
    if isinstance(data, dict):
        return data
    return fallback


def write_audit_event(
    session: CloudUserSession,
    event: AuditEvent,
    settings: Settings | None = None,
    *,
    device_id: str | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings()
    payload = event_to_payload(
        event,
        user_id=session.user_id,
        user_email=session.email,
        role=session.role or settings.sync_role,
        machine_name=settings.machine_name,
        device_id=device_id,
    )

    # v8.2: la caja negra escribe mediante RPC security definer.
    # Motivo: en algunos entornos supabase-py mantiene el subcliente REST como anon
    # aunque Auth tenga sesión. La RPC valida el user_id contra profiles y evita que
    # los workers necesiten permisos directos de lectura/escritura sobre audit_logs.
    rpc_args = {
        "p_operation_id": payload.get("operation_id"),
        "p_user_id": payload.get("user_id"),
        "p_user_email": payload.get("user_email"),
        "p_role": payload.get("role"),
        "p_device_id": payload.get("device_id"),
        "p_machine_name": payload.get("machine_name"),
        "p_module": payload.get("module"),
        "p_action": payload.get("action"),
        "p_status": payload.get("status"),
        "p_severity": payload.get("severity"),
        "p_entity_type": payload.get("entity_type"),
        "p_entity_id": payload.get("entity_id"),
        "p_before_data": payload.get("before_data"),
        "p_after_data": payload.get("after_data"),
        "p_message": payload.get("message"),
        "p_error_detail": payload.get("error_detail"),
    }
    try:
        response = session.client.rpc("futonhub_write_audit_log", rpc_args).execute()
        return _extract_rpc_row(response, payload)
    except Exception as rpc_exc:
        # Fallback para instalaciones antiguas donde aún no se ejecutó el SQL v8.2.
        try:
            response = session.client.table("audit_logs").insert(payload).execute()
        except Exception as exc:
            raise CloudAuditError(f"No se pudo escribir audit_log: {exc} | RPC previa: {rpc_exc}") from exc
        data = getattr(response, "data", None) or []
        return data[0] if data else payload


def write_snapshot(
    session: CloudUserSession,
    snapshot: OperationSnapshot,
) -> dict[str, Any]:
    payload = snapshot_to_payload(snapshot, user_id=session.user_id)
    rpc_args = {
        "p_operation_id": payload.get("operation_id"),
        "p_user_id": payload.get("user_id"),
        "p_module": payload.get("module"),
        "p_action": payload.get("action"),
        "p_entity_type": payload.get("entity_type"),
        "p_entity_id": payload.get("entity_id"),
        "p_before_data": payload.get("before_data"),
        "p_reason": payload.get("reason"),
    }
    try:
        response = session.client.rpc("futonhub_write_operation_snapshot", rpc_args).execute()
        return _extract_rpc_row(response, payload)
    except Exception as rpc_exc:
        # Fallback para instalaciones antiguas donde aún no se ejecutó el SQL v8.2.
        try:
            response = session.client.table("operation_snapshots").insert(payload).execute()
        except Exception as exc:
            raise CloudAuditError(f"No se pudo escribir operation_snapshot: {exc} | RPC previa: {rpc_exc}") from exc
        data = getattr(response, "data", None) or []
        return data[0] if data else payload


def create_test_audit_event(session: CloudUserSession, settings: Settings | None = None) -> AuditEvent:
    settings = settings or load_settings()
    operation_id = new_operation_id("TESTLOG")
    return AuditEvent(
        operation_id=operation_id,
        module="blackbox",
        action="cloud_test_log",
        status="TEST",
        severity="INFO",
        entity_type="diagnostic",
        entity_id=settings.machine_name,
        before_data=None,
        after_data={
            "mode": settings.app_mode,
            "machine_name": settings.machine_name,
            "user_email": session.email,
            "role": session.role,
        },
        message="Prueba manual de audit_log generada desde FutonHUB v6 Caja Negra.",
    )


def create_test_snapshot(session: CloudUserSession, settings: Settings | None = None) -> OperationSnapshot:
    settings = settings or load_settings()
    operation_id = new_operation_id("TESTSNAP")
    return OperationSnapshot(
        operation_id=operation_id,
        module="blackbox",
        action="cloud_test_snapshot",
        entity_type="diagnostic",
        entity_id=settings.machine_name,
        before_data={
            "sample": True,
            "mode": settings.app_mode,
            "machine_name": settings.machine_name,
            "user_email": session.email,
            "role": session.role,
            "note": "Snapshot de prueba. No modifica datos reales.",
        },
        reason="Prueba manual de snapshot lógico desde FutonHUB v6 Caja Negra.",
    )


def list_audit_logs(session: CloudUserSession, *, limit: int = 25) -> list[dict[str, Any]]:
    # v8.3: lectura admin por RPC security definer.
    # Esto evita falsos "Sin logs visibles" cuando el subcliente REST pierde el token.
    try:
        response = session.client.rpc(
            "futonhub_read_audit_logs",
            {"p_user_id": session.user_id, "p_limit": limit},
        ).execute()
        data = getattr(response, "data", None)
        if data is not None:
            return list(data or [])
    except Exception:
        # Fallback para instalaciones donde aún no se ejecutó el SQL v8.3.
        pass
    try:
        response = (
            session.client.table("audit_logs")
            .select("id,created_at,operation_id,user_email,role,machine_name,module,action,severity,status,entity_type,entity_id,message,error_detail")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        raise CloudAuditError(f"No se pudieron leer audit_logs: {exc}") from exc
    return list(getattr(response, "data", None) or [])


def list_operation_snapshots(session: CloudUserSession, *, limit: int = 25) -> list[dict[str, Any]]:
    try:
        response = session.client.rpc(
            "futonhub_read_operation_snapshots",
            {"p_user_id": session.user_id, "p_limit": limit},
        ).execute()
        data = getattr(response, "data", None)
        if data is not None:
            return list(data or [])
    except Exception:
        pass
    try:
        response = (
            session.client.table("operation_snapshots")
            .select("id,created_at,operation_id,user_id,module,action,entity_type,entity_id,before_data,reason")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        raise CloudAuditError(f"No se pudieron leer operation_snapshots: {exc}") from exc
    return list(getattr(response, "data", None) or [])


def format_audit_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Sin logs visibles."
    lines = []
    for row in rows:
        lines.append(
            f"{row.get('created_at','')} | {row.get('severity','')} | {row.get('status','')} | "
            f"{row.get('module','')}.{row.get('action','')} | {row.get('operation_id','')} | "
            f"{row.get('user_email') or '-'} | {row.get('machine_name') or '-'}"
        )
        msg = row.get("message") or row.get("error_detail")
        if msg:
            lines.append(f"    {msg}")
    return "\n".join(lines)


def format_snapshot_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Sin snapshots visibles."
    lines = []
    for row in rows:
        lines.append(
            f"{row.get('created_at','')} | {row.get('module','')}.{row.get('action','')} | "
            f"{row.get('entity_type','')}:{row.get('entity_id','')} | {row.get('operation_id','')}"
        )
        reason = row.get("reason")
        if reason:
            lines.append(f"    {reason}")
    return "\n".join(lines)

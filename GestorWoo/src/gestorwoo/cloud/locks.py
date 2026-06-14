from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from gestorwoo.cloud.audit import CloudAuditError
from gestorwoo.cloud.auth import CloudUserSession
from gestorwoo.config import Settings, load_settings


def lock_payload(*, operation_key: str, locked_by: str, details: str = "", ttl_minutes: int = 30) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "operation_key": operation_key,
        "locked_by": locked_by,
        "locked_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
        "status": "running",
        "details": details,
    }


def acquire_system_lock(
    session: CloudUserSession,
    operation_key: str,
    *,
    details: str = "",
    ttl_minutes: int = 15,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Bloquea una operacion critica mediante RPC atomica en Supabase."""
    settings = settings or load_settings()
    try:
        response = session.client.rpc(
            "futonhub_acquire_system_lock",
            {
                "p_operation_key": operation_key,
                "p_user_id": session.user_id,
                "p_machine_name": settings.machine_name,
                "p_details": details,
                "p_ttl_minutes": ttl_minutes,
            },
        ).execute()
    except Exception as exc:
        raise CloudAuditError(
            "No se pudo adquirir lock online. Ejecuta docs/supabase/19_hardening_seguridad_locks_v13_1.sql antes de publicar."
        ) from exc

    data = getattr(response, "data", None)
    result = data[0] if isinstance(data, list) and data else data
    if not isinstance(result, dict):
        raise CloudAuditError("Respuesta invalida al adquirir lock online.")
    if not result.get("acquired"):
        raise CloudAuditError(
            "Operacion bloqueada por otro proceso activo: "
            f"{result.get('operation_key')} · {result.get('locked_by_machine') or result.get('locked_by')} "
            f"hasta {result.get('expires_at')}."
        )
    return result


def release_system_lock(
    session: CloudUserSession,
    operation_key: str,
    *,
    status: str = "released",
) -> None:
    try:
        session.client.rpc(
            "futonhub_release_system_lock",
            {
                "p_operation_key": operation_key,
                "p_user_id": session.user_id,
                "p_status": status,
            },
        ).execute()
    except Exception:
        return

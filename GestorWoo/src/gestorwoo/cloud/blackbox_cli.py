from __future__ import annotations

import getpass

from gestorwoo.cloud.audit import (
    CloudAuditError,
    create_test_audit_event,
    create_test_snapshot,
    format_audit_rows,
    format_snapshot_rows,
    list_audit_logs,
    list_operation_snapshots,
    write_audit_event,
    write_snapshot,
)
from gestorwoo.cloud.auth import SupabaseAuthError, register_device_seen, sign_in_with_password
from gestorwoo.config import load_settings


def _login_from_console():
    settings = load_settings()
    email = settings.hub_user_email
    if not email:
        email = input("Email Supabase: ").strip()
    print(f"Login Supabase para: {email}")
    password = getpass.getpass("Contraseña Supabase: ")
    session = sign_in_with_password(email, password, settings)
    register_device_seen(session, settings)
    return session, settings


def run_cloud_test_log() -> int:
    try:
        session, settings = _login_from_console()
        event = create_test_audit_event(session, settings)
        row = write_audit_event(session, event, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Audit log creado correctamente.")
    print(f"operation_id: {row.get('operation_id', event.operation_id)}")
    print(f"module/action: {event.module}.{event.action}")
    print(f"usuario: {session.email} · rol: {session.role}")
    return 0


def run_cloud_test_snapshot() -> int:
    try:
        session, settings = _login_from_console()
        snapshot = create_test_snapshot(session, settings)
        snap_row = write_snapshot(session, snapshot)
        event = create_test_audit_event(session, settings)
        event = event.__class__(
            operation_id=snapshot.operation_id,
            module="blackbox",
            action="cloud_test_snapshot",
            status="TEST",
            severity="INFO",
            entity_type=snapshot.entity_type,
            entity_id=snapshot.entity_id,
            before_data=snapshot.before_data,
            after_data={"snapshot_created": True},
            message="Prueba manual de snapshot lógico creada correctamente.",
        )
        write_audit_event(session, event, settings)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("Snapshot creado correctamente.")
    print(f"operation_id: {snap_row.get('operation_id', snapshot.operation_id)}")
    print(f"entity: {snapshot.entity_type}:{snapshot.entity_id}")
    print("También se registró un audit_log asociado.")
    return 0


def run_cloud_logs(limit: int = 25) -> int:
    try:
        session, _settings = _login_from_console()
        rows = list_audit_logs(session, limit=limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("AUDIT LOGS CLOUD")
    print("=" * 50)
    print(format_audit_rows(rows))
    return 0


def run_cloud_snapshots(limit: int = 25) -> int:
    try:
        session, _settings = _login_from_console()
        rows = list_operation_snapshots(session, limit=limit)
    except (SupabaseAuthError, CloudAuditError) as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:
        print(f"ERROR inesperado: {exc}")
        return 2

    print("SNAPSHOTS CLOUD")
    print("=" * 50)
    print(format_snapshot_rows(rows))
    return 0

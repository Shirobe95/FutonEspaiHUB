from __future__ import annotations

import getpass
from dataclasses import dataclass
from typing import Any

from gestorwoo.config import load_settings
from gestorwoo.cloud.auth import SupabaseAuthError, sign_in_with_password, register_device_seen
from gestorwoo.cloud.client import (
    SupabaseDependencyMissing,
    SupabaseNotConfigured,
    connection_info,
    create_supabase_client,
)


@dataclass(frozen=True)
class CloudDiagnosticResult:
    text: str
    ok: bool


CLOUD_TABLES = (
    "profiles",
    "devices",
    "role_permissions",
    "system_locks",
    "entity_locks",
    "audit_logs",
    "operation_snapshots",
    "notifications",
)


def collect_cloud_diagnostics(
    *,
    try_connect: bool = True,
    authenticated: bool = False,
    password: str | None = None,
) -> CloudDiagnosticResult:
    settings = load_settings()
    info = connection_info(settings)
    lines: list[str] = []
    warnings: list[str] = []

    lines.append("DIAGNOSTICO SUPABASE FUTONHUB")
    lines.append("=" * 34)
    lines.append(f"Modo HUB: {info.mode}")
    lines.append(f"Rol local configurado: {info.role}")
    lines.append(f"Usuario/email local: {info.user_email or '(no configurado)'}")
    lines.append(f"SUPABASE_URL: {info.url or '(no configurada)'}")
    lines.append(f"SUPABASE_ANON_KEY: {'OK' if info.anon_key_present else 'FALTA'}")
    lines.append(f"SERVICE_ROLE_KEY local: {'presente (solo admin)' if info.service_key_present else 'no configurada'}")
    lines.append(f"Lectura solicitada: {'autenticada' if authenticated else 'anon/sin sesión'}")
    lines.append("")

    if not info.configured:
        warnings.append("Supabase aún no está configurado en GestorWoo/.env.")
        lines.append("Estado conexión: pendiente de configurar")
        return _finish(lines, warnings)

    if not try_connect:
        lines.append("Estado conexión: no probado")
        return _finish(lines, warnings)

    session = None
    client: Any
    try:
        if authenticated:
            session = sign_in_with_password(info.user_email, password or "", settings)
            client = session.client
            lines.append("Estado conexión: cliente creado + login OK")
            lines.append(f"Auth local: sesión activa · {session.email} · rol cloud: {session.role or '(sin profile)'}")
            try:
                register_device_seen(session, settings)
            except Exception:
                pass
        else:
            client = create_supabase_client(settings)
            lines.append("Estado conexión: cliente creado")
    except (SupabaseNotConfigured, SupabaseDependencyMissing, SupabaseAuthError) as exc:
        warnings.append(str(exc))
        lines.append(f"Estado conexión: {exc}")
        return _finish(lines, warnings)
    except Exception as exc:
        warnings.append(f"No se pudo crear cliente/login Supabase: {exc}")
        lines.append(f"Estado conexión: ERROR: {exc}")
        return _finish(lines, warnings)

    lines.append("")
    lines.append("TABLAS CLOUD")
    lines.append("-" * 34)

    zero_tables: list[str] = []
    for table in CLOUD_TABLES:
        try:
            response = client.table(table).select("*", count="exact").limit(1).execute()
            count = getattr(response, "count", None)
            if count == 0:
                zero_tables.append(table)
            lines.append(f"{table}: OK" + (f" · filas visibles: {count}" if count is not None else ""))
        except Exception as exc:
            warnings.append(f"Tabla {table}: no accesible o no creada ({exc})")
            lines.append(f"{table}: ERROR · {exc}")

    lines.append("")
    if authenticated and session is not None:
        _append_profile_check(lines, warnings, client, session.user_id)
        _append_permission_check(lines, warnings, client, session.role or info.role)
    else:
        lines.append("Auth local: sin sesión activa")
        if zero_tables:
            lines.append("Nota RLS: ver 0 filas sin sesión puede ser normal si las políticas protegen las tablas.")
            lines.append("Para lectura real usa: python gestorwoo.py cloud-login-diagnostic")
        else:
            lines.append("Nota: lectura anon completada; para validar rol real usa cloud-login-diagnostic.")

    return _finish(lines, warnings)


def _append_profile_check(lines: list[str], warnings: list[str], client: Any, user_id: str) -> None:
    try:
        response = client.table("profiles").select("id,email,display_name,role,active").eq("id", user_id).limit(1).execute()
        data = getattr(response, "data", None) or []
        if not data:
            warnings.append("Login OK, pero no se encontró profile para este auth.uid().")
            lines.append("Perfil actual: NO ENCONTRADO")
            return
        profile = data[0]
        lines.append("PERFIL ACTUAL")
        lines.append("-" * 34)
        lines.append(f"id: {profile.get('id')}")
        lines.append(f"email: {profile.get('email')}")
        lines.append(f"display_name: {profile.get('display_name')}")
        lines.append(f"role: {profile.get('role')}")
        lines.append(f"active: {profile.get('active')}")
    except Exception as exc:
        warnings.append(f"No se pudo leer profile autenticado: {exc}")
        lines.append(f"Perfil actual: ERROR · {exc}")


def _append_permission_check(lines: list[str], warnings: list[str], client: Any, role: str) -> None:
    try:
        response = client.table("role_permissions").select("module,can_view,can_execute").eq("role", role).order("module").execute()
        data = getattr(response, "data", None) or []
        lines.append("")
        lines.append(f"PERMISOS VISIBLES PARA ROL {role}")
        lines.append("-" * 34)
        if not data:
            warnings.append(f"No se encontraron permisos visibles para el rol {role}.")
            lines.append("sin permisos visibles")
            return
        for row in data:
            lines.append(
                f"{row.get('module')}: ver={row.get('can_view')} · ejecutar={row.get('can_execute')}"
            )
    except Exception as exc:
        warnings.append(f"No se pudieron leer permisos autenticados: {exc}")
        lines.append(f"Permisos: ERROR · {exc}")


def print_cloud_diagnostics() -> int:
    result = collect_cloud_diagnostics()
    print(result.text)
    return 0 if result.ok else 1


def print_cloud_login_diagnostics() -> int:
    settings = load_settings()
    email = settings.hub_user_email or input("Email Supabase: ").strip()
    print(f"Login Supabase para: {email}")
    password = getpass.getpass("Contraseña Supabase: ")
    result = collect_cloud_diagnostics(authenticated=True, password=password)
    print(result.text)
    return 0 if result.ok else 1


def _finish(lines: list[str], warnings: list[str]) -> CloudDiagnosticResult:
    lines.append("")
    if warnings:
        lines.append("AVISOS")
        lines.append("-" * 34)
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("Estado Supabase: OK")
    return CloudDiagnosticResult(text="\n".join(lines), ok=not warnings)

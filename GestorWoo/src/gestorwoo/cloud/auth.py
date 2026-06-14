from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gestorwoo.config import Settings, load_settings
from gestorwoo.cloud.client import create_supabase_client


class SupabaseAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudUserSession:
    client: Any
    user_id: str
    email: str
    access_token: str | None = None
    refresh_token: str | None = None
    role: str | None = None
    display_name: str | None = None


def _apply_authenticated_token(client: Any, access_token: str | None, refresh_token: str | None = None) -> None:
    """Fuerza que el cliente PostgREST use el token del usuario logueado.

    En algunas versiones de supabase-py, `auth.sign_in_with_password()` devuelve una
    sesión válida, pero las llamadas posteriores a `.table(...).insert(...)` pueden
    salir todavía como `anon` si el token no queda aplicado al subcliente REST.
    Eso provoca errores RLS aunque el login sea correcto.
    """
    if not access_token:
        return

    # Supabase-py v2 suele exponer `postgrest.auth(token)`.
    for attr_name in ("postgrest", "rest"):
        rest_client = getattr(client, attr_name, None)
        auth_method = getattr(rest_client, "auth", None)
        if callable(auth_method):
            try:
                auth_method(access_token)
            except Exception:
                pass

    # Algunas versiones mantienen headers internos accesibles. Los tocamos solo
    # si existen para no acoplar el HUB a una versión concreta de la librería.
    for target in (client, getattr(client, "postgrest", None), getattr(client, "rest", None)):
        headers = getattr(target, "headers", None)
        if isinstance(headers, dict):
            headers["Authorization"] = f"Bearer {access_token}"
            headers["apikey"] = headers.get("apikey", "")

    # Si la API lo permite, rehidrata también el gestor de Auth.
    set_session = getattr(getattr(client, "auth", None), "set_session", None)
    if callable(set_session) and refresh_token:
        try:
            set_session(access_token, refresh_token)
        except Exception:
            pass


def sign_in_with_password(
    email: str,
    password: str,
    settings: Settings | None = None,
) -> CloudUserSession:
    """Inicia sesión con Supabase Auth y devuelve cliente autenticado.

    Importante: no se guarda la contraseña. El token vive solo en memoria durante
    la ejecución actual del comando/ventana.
    """
    settings = settings or load_settings()
    email = (email or settings.hub_user_email or "").strip().lower()
    if not email:
        raise SupabaseAuthError("Falta GESTORWOO_USER_EMAIL en .env o email de login.")
    if not password:
        raise SupabaseAuthError("Contraseña vacía. No se puede iniciar sesión.")

    client = create_supabase_client(settings)
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # supabase-py cambia tipos según versión; preservamos mensaje útil.
        raise SupabaseAuthError(f"No se pudo iniciar sesión en Supabase: {exc}") from exc

    user = getattr(response, "user", None)
    session = getattr(response, "session", None)
    user_id = getattr(user, "id", None)
    token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)
    if not user_id:
        raise SupabaseAuthError("Supabase no devolvió usuario autenticado.")

    _apply_authenticated_token(client, token, refresh_token)

    profile = fetch_current_profile(client, user_id)
    role = (profile or {}).get("role")
    display_name = (profile or {}).get("display_name")
    profile_email = (profile or {}).get("email") or email
    return CloudUserSession(
        client=client,
        user_id=str(user_id),
        email=str(profile_email),
        access_token=token,
        refresh_token=refresh_token,
        role=role,
        display_name=display_name,
    )


def fetch_current_profile(client: Any, user_id: str) -> dict[str, Any] | None:
    try:
        response = client.table("profiles").select("id,email,display_name,role,active").eq("id", user_id).limit(1).execute()
        data = getattr(response, "data", None) or []
        return data[0] if data else None
    except Exception:
        return None


def register_device_seen(session: CloudUserSession, settings: Settings | None = None) -> None:
    """Registra/actualiza la máquina actual para trazabilidad básica.

    Si RLS o la versión de supabase-py bloquea el upsert, no rompemos el arranque.
    El diagnóstico lo contará como aviso si procede.
    """
    settings = settings or load_settings()
    payload = {
        "user_id": session.user_id,
        "machine_name": settings.machine_name,
        "device_label": settings.machine_name,
        "role": session.role or settings.sync_role or "worker",
        "active": True,
        "last_seen_at": "now()",
    }
    # Evitamos upsert con constraint compuesta inexistente. Insertamos una fila por máquina/sesión.
    safe_payload = dict(payload)
    safe_payload.pop("last_seen_at", None)
    try:
        session.client.table("devices").insert(safe_payload).execute()
    except Exception:
        # No se considera crítico todavía; v5 es login/lectura.
        return

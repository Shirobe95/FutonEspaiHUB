from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gestorwoo.config import Settings, load_settings
from gestorwoo.cloud.client import create_supabase_client


class SupabaseAuthError(RuntimeError):
    pass


class SupabaseRefreshSessionError(SupabaseAuthError):
    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


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
    """Force PostgREST clients to use the authenticated user token."""
    if not access_token:
        return

    for attr_name in ("postgrest", "rest"):
        rest_client = getattr(client, attr_name, None)
        auth_method = getattr(rest_client, "auth", None)
        if callable(auth_method):
            try:
                auth_method(access_token)
            except Exception:
                pass

    for target in (client, getattr(client, "postgrest", None), getattr(client, "rest", None)):
        headers = getattr(target, "headers", None)
        if isinstance(headers, dict):
            headers["Authorization"] = f"Bearer {access_token}"
            headers["apikey"] = headers.get("apikey", "")

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
    """Sign in with Supabase Auth without persisting the password."""
    settings = settings or load_settings()
    email = (email or settings.hub_user_email or "").strip().lower()
    if not email:
        raise SupabaseAuthError("Falta GESTORWOO_USER_EMAIL en .env o email de login.")
    if not password:
        raise SupabaseAuthError("Contrasena vacia. No se puede iniciar sesion.")

    client = create_supabase_client(settings)
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        raise SupabaseAuthError(f"No se pudo iniciar sesion en Supabase: {exc}") from exc

    return _session_from_auth_response(client, response, email_hint=email)


def sign_in_with_refresh_token(
    refresh_token: str,
    settings: Settings | None = None,
) -> CloudUserSession:
    """Renew a Supabase session without knowing or persisting the password."""
    settings = settings or load_settings()
    if not refresh_token:
        raise SupabaseRefreshSessionError("Sesion recordada vacia.", kind="invalid_session")
    client = create_supabase_client(settings)
    refresh_session = getattr(getattr(client, "auth", None), "refresh_session", None)
    if not callable(refresh_session):
        raise SupabaseRefreshSessionError(
            "La version de Supabase Auth no permite renovar sesiones.",
            kind="invalid_session",
        )
    try:
        try:
            response = refresh_session(refresh_token)
        except TypeError:
            response = refresh_session({"refresh_token": refresh_token})
    except Exception as exc:
        kind = _classify_refresh_error(exc)
        if kind == "network_error":
            raise SupabaseRefreshSessionError(
                "No se pudo conectar con Supabase para renovar la sesion.",
                kind=kind,
            ) from exc
        raise SupabaseRefreshSessionError(
            "La sesion recordada ya no es valida.",
            kind="invalid_session",
        ) from exc
    try:
        return _session_from_auth_response(client, response, email_hint=settings.hub_user_email)
    except SupabaseAuthError as exc:
        raise SupabaseRefreshSessionError(str(exc), kind="invalid_session") from exc


def _session_from_auth_response(client: Any, response: Any, *, email_hint: str = "") -> CloudUserSession:
    user = getattr(response, "user", None)
    session = getattr(response, "session", None)
    user_id = getattr(user, "id", None)
    token = getattr(session, "access_token", None)
    refresh_token = getattr(session, "refresh_token", None)
    if not user_id:
        raise SupabaseAuthError("Supabase no devolvio usuario autenticado.")

    _apply_authenticated_token(client, token, refresh_token)

    profile = fetch_current_profile(client, user_id)
    role = (profile or {}).get("role")
    display_name = (profile or {}).get("display_name")
    profile_email = (profile or {}).get("email") or getattr(user, "email", None) or email_hint
    return CloudUserSession(
        client=client,
        user_id=str(user_id),
        email=str(profile_email),
        access_token=token,
        refresh_token=refresh_token,
        role=role,
        display_name=display_name,
    )


def _classify_refresh_error(exc: Exception) -> str:
    text = str(exc).lower()
    network_markers = (
        "network",
        "connection",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "unavailable",
        "dns",
        "failed to establish",
        "max retries",
        "name resolution",
    )
    if any(marker in text for marker in network_markers):
        return "network_error"
    return "invalid_session"


def fetch_current_profile(client: Any, user_id: str) -> dict[str, Any] | None:
    try:
        response = client.table("profiles").select("id,email,display_name,role,active").eq("id", user_id).limit(1).execute()
        data = getattr(response, "data", None) or []
        return data[0] if data else None
    except Exception:
        return None


def register_device_seen(session: CloudUserSession, settings: Settings | None = None) -> None:
    """Register this machine for basic traceability without blocking startup."""
    settings = settings or load_settings()
    payload = {
        "user_id": session.user_id,
        "machine_name": settings.machine_name,
        "device_label": settings.machine_name,
        "role": session.role or settings.sync_role or "worker",
        "active": True,
        "last_seen_at": "now()",
    }
    safe_payload = dict(payload)
    safe_payload.pop("last_seen_at", None)
    try:
        session.client.table("devices").insert(safe_payload).execute()
    except Exception:
        return

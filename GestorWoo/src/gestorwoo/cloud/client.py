from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gestorwoo.config import Settings


class SupabaseNotConfigured(RuntimeError):
    pass


class SupabaseDependencyMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseConnectionInfo:
    configured: bool
    url: str
    anon_key_present: bool
    service_key_present: bool
    mode: str
    role: str
    user_email: str


def connection_info(settings: Settings) -> SupabaseConnectionInfo:
    return SupabaseConnectionInfo(
        configured=bool(settings.supabase_url and settings.supabase_anon_key),
        url=settings.supabase_url,
        anon_key_present=bool(settings.supabase_anon_key),
        service_key_present=bool(settings.supabase_service_key),
        mode=settings.app_mode,
        role=settings.sync_role,
        user_email=settings.hub_user_email,
    )


def create_supabase_client(settings: Settings, *, use_service_key: bool = False) -> Any:
    """Crea cliente Supabase de forma opcional.

    No importamos supabase al arrancar el HUB para que el modo local siga funcionando
    aunque el paquete no esté instalado todavía.
    """
    key = settings.supabase_service_key if use_service_key else settings.supabase_anon_key
    if not settings.supabase_url or not key:
        raise SupabaseNotConfigured(
            "Faltan SUPABASE_URL y/o SUPABASE_ANON_KEY en GestorWoo/.env."
        )
    try:
        from supabase import create_client
    except ModuleNotFoundError as exc:
        raise SupabaseDependencyMissing(
            "No está instalado el paquete 'supabase'. Ejecuta: pip install supabase"
        ) from exc
    return create_client(settings.supabase_url, key)

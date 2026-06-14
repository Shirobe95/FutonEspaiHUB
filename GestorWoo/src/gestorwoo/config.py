from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from gestorwoo.pathing import DEFAULT_DB_RELATIVE_PATH, gestorwoo_root, resolve_gestorwoo_path


VALID_APP_MODES = {"local", "local_guarded", "supabase_guarded"}
VALID_SYNC_ROLES = {"admin", "worker", "standalone"}


@dataclass(frozen=True)
class Settings:
    woocommerce_url: str
    consumer_key: str
    consumer_secret: str
    db_path: Path
    app_mode: str
    machine_name: str
    env_path: Path
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    sync_role: str
    hub_user_email: str
    price_drop_warning_percent: float
    price_drop_block_percent: float

    @property
    def guarded_mode(self) -> bool:
        return self.app_mode in {"local_guarded", "supabase_guarded"}

    @property
    def supabase_enabled(self) -> bool:
        return self.app_mode == "supabase_guarded" or bool(self.supabase_url and self.supabase_anon_key)

    @property
    def is_admin(self) -> bool:
        return self.sync_role == "admin"


def load_settings() -> Settings:
    # Carga .env desde la carpeta real de GestorWoo, aunque se lance desde otro cwd.
    env_path = gestorwoo_root() / ".env"
    load_env_file(env_path)

    url = os.getenv("WOOCOMMERCE_URL", "").rstrip("/")
    key = os.getenv("WOOCOMMERCE_CONSUMER_KEY", "")
    secret = os.getenv("WOOCOMMERCE_CONSUMER_SECRET", "")
    db_path = resolve_gestorwoo_path(
        os.getenv("GESTORWOO_DB_PATH"),
        default=DEFAULT_DB_RELATIVE_PATH,
    )
    app_mode = os.getenv("GESTORWOO_MODE", "local_guarded").strip().lower() or "local_guarded"
    if app_mode not in VALID_APP_MODES:
        app_mode = "local_guarded"
    machine_name = _machine_name(os.getenv("GESTORWOO_MACHINE_NAME"))
    sync_role = os.getenv("GESTORWOO_SYNC_ROLE", "standalone").strip().lower() or "standalone"
    if sync_role not in VALID_SYNC_ROLES:
        sync_role = "standalone"
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    hub_user_email = os.getenv("GESTORWOO_USER_EMAIL", "").strip().lower()
    price_drop_warning_percent = _safe_float_env("GESTORWOO_PRICE_DROP_WARNING_PERCENT", 30.0)
    price_drop_block_percent = _safe_float_env("GESTORWOO_PRICE_DROP_BLOCK_PERCENT", 60.0)
    if price_drop_warning_percent < 0:
        price_drop_warning_percent = 30.0
    if price_drop_block_percent <= 0:
        price_drop_block_percent = 60.0
    if price_drop_warning_percent >= price_drop_block_percent:
        price_drop_warning_percent = max(0.0, price_drop_block_percent / 2)

    return Settings(
        woocommerce_url=url,
        consumer_key=key,
        consumer_secret=secret,
        db_path=db_path,
        app_mode=app_mode,
        machine_name=machine_name,
        env_path=env_path,
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        supabase_service_key=supabase_service_key,
        sync_role=sync_role,
        hub_user_email=hub_user_email,
        price_drop_warning_percent=price_drop_warning_percent,
        price_drop_block_percent=price_drop_block_percent,
    )



def _safe_float_env(key: str, default: float) -> float:
    raw = os.getenv(key, "")
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(str(raw).strip().replace(",", "."))
    except Exception:
        return float(default)

def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _machine_name(configured: str | None = None) -> str:
    value = (configured or "").strip()
    if value:
        return _safe_machine_name(value)
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "PC_LOCAL"
    return _safe_machine_name(hostname or "PC_LOCAL")


def _safe_machine_name(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    return clean[:60] or "PC_LOCAL"

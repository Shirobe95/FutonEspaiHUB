from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


SCHEMA_VERSION = 1
APP_CONFIG_DIR = Path("FutonHUB") / "config"
SESSION_FILE_NAME = "remembered_session.json"


class RememberedSessionError(RuntimeError):
    """Raised when a remembered session cannot be safely used."""


class RememberedSessionUnavailable(RememberedSessionError):
    """Raised when the secure backend is unavailable on this platform."""


class SecureSessionStore(Protocol):
    def protect(self, data: bytes) -> bytes:
        ...

    def unprotect(self, protected_data: bytes) -> bytes:
        ...


@dataclass(frozen=True)
class RememberedSession:
    email: str
    refresh_token: str
    saved_at: str
    schema_version: int = SCHEMA_VERSION


class WindowsDpapiSessionStore:
    """Protects secrets using Windows DPAPI scoped to the current user."""

    _DESCRIPTION = "FutonHUB remembered Supabase session"

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RememberedSessionUnavailable("Remember Me solo esta disponible con DPAPI en Windows.")

    def protect(self, data: bytes) -> bytes:
        return _dpapi_protect(data, self._DESCRIPTION)

    def unprotect(self, protected_data: bytes) -> bytes:
        return _dpapi_unprotect(protected_data)


class InMemorySecureSessionStore:
    """Test backend that never writes plaintext secrets to the persisted file."""

    def __init__(self) -> None:
        self._secrets: dict[str, bytes] = {}

    def protect(self, data: bytes) -> bytes:
        key = uuid.uuid4().hex
        self._secrets[key] = bytes(data)
        return f"memory:{key}".encode("ascii")

    def unprotect(self, protected_data: bytes) -> bytes:
        marker = protected_data.decode("ascii")
        if not marker.startswith("memory:"):
            raise RememberedSessionError("Formato de secreto recordado invalido.")
        key = marker.split(":", 1)[1]
        try:
            return self._secrets[key]
        except KeyError as exc:
            raise RememberedSessionError("Secreto recordado no disponible.") from exc


def remembered_session_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".futonhub"
    return base / APP_CONFIG_DIR / SESSION_FILE_NAME


def default_secure_store() -> SecureSessionStore:
    return WindowsDpapiSessionStore()


def has_remembered_session(*, path: Path | None = None) -> bool:
    return (path or remembered_session_path()).is_file()


def save_remembered_session(
    email: str,
    refresh_token: str,
    *,
    path: Path | None = None,
    store: SecureSessionStore | None = None,
) -> Path:
    email = (email or "").strip().lower()
    if not email:
        raise RememberedSessionError("No se puede recordar una sesion sin email.")
    if not refresh_token:
        raise RememberedSessionError("Supabase no devolvio material de sesion renovable.")
    target = path or remembered_session_path()
    secure_store = store or default_secure_store()
    protected = secure_store.protect(refresh_token.encode("utf-8"))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "remember_enabled": True,
        "email": email,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "secret_backend": secure_store.__class__.__name__,
        "protected_secret": base64.b64encode(protected).decode("ascii"),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_remembered_session(
    *,
    path: Path | None = None,
    store: SecureSessionStore | None = None,
) -> RememberedSession | None:
    target = path or remembered_session_path()
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RememberedSessionError("La sesion recordada local esta corrupta.") from exc
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        raise RememberedSessionError("Version de sesion recordada no soportada.")
    if payload.get("remember_enabled") is not True:
        return None
    email = str(payload.get("email") or "").strip().lower()
    protected_text = str(payload.get("protected_secret") or "")
    if not email or not protected_text:
        raise RememberedSessionError("La sesion recordada no contiene metadata valida.")
    try:
        protected = base64.b64decode(protected_text.encode("ascii"), validate=True)
        token = (store or default_secure_store()).unprotect(protected).decode("utf-8")
    except RememberedSessionUnavailable:
        raise
    except Exception as exc:
        raise RememberedSessionError("No se pudo descifrar la sesion recordada.") from exc
    if not token:
        raise RememberedSessionError("La sesion recordada no contiene token renovable.")
    return RememberedSession(
        email=email,
        refresh_token=token,
        saved_at=str(payload.get("saved_at") or ""),
        schema_version=SCHEMA_VERSION,
    )


def clear_remembered_session(*, path: Path | None = None) -> None:
    target = path or remembered_session_path()
    try:
        target.unlink()
    except FileNotFoundError:
        return


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _dpapi_protect(data: bytes, description: str) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        ctypes.c_wchar_p(description),
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise RememberedSessionError("DPAPI no pudo proteger la sesion recordada.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(protected_data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _buffer = _blob_from_bytes(protected_data)
    out_blob = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise RememberedSessionError("DPAPI no pudo abrir la sesion recordada.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)

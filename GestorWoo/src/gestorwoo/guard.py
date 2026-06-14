from __future__ import annotations

import contextlib
import os
import socket
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from gestorwoo.config import Settings
from gestorwoo.security import log_event

LOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS system_locks (
    operation_key TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    module TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
)
"""


class OperationBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class LockInfo:
    operation_key: str
    locked_by: str
    locked_at: str
    expires_at: str
    status: str
    module: str
    details: str


def machine_name(default: str | None = None) -> str:
    configured = (default or os.getenv("GESTORWOO_MACHINE_NAME") or "").strip()
    if configured:
        raw = configured
    else:
        try:
            raw = socket.gethostname()
        except Exception:
            raw = "PC_LOCAL"
    clean = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in raw.strip())
    return clean[:60] or "PC_LOCAL"


def connect_guarded(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def init_guard_schema(db_path: Path) -> None:
    with connect_guarded(db_path) as conn:
        conn.execute(LOCK_SCHEMA)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_locks_status ON system_locks(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_system_locks_expires ON system_locks(expires_at)")
        conn.commit()


def active_locks(db_path: Path) -> list[LockInfo]:
    init_guard_schema(db_path)
    now = _now_text()
    with connect_guarded(db_path) as conn:
        rows = conn.execute(
            """
            SELECT operation_key, locked_by, locked_at, expires_at, status, module, details
            FROM system_locks
            WHERE status = 'running' AND expires_at > ?
            ORDER BY locked_at
            """,
            (now,),
        ).fetchall()
    return [LockInfo(**dict(row)) for row in rows]


def stale_locks(db_path: Path) -> list[LockInfo]:
    init_guard_schema(db_path)
    now = _now_text()
    with connect_guarded(db_path) as conn:
        rows = conn.execute(
            """
            SELECT operation_key, locked_by, locked_at, expires_at, status, module, details
            FROM system_locks
            WHERE status = 'running' AND expires_at <= ?
            ORDER BY locked_at
            """,
            (now,),
        ).fetchall()
    return [LockInfo(**dict(row)) for row in rows]


def acquire_lock(
    db_path: Path,
    operation_key: str,
    *,
    module: str,
    locked_by: str | None = None,
    details: str = "",
    ttl_minutes: int = 30,
) -> LockInfo:
    init_guard_schema(db_path)
    now = datetime.now()
    now_text = _dt_text(now)
    expires_text = _dt_text(now + timedelta(minutes=max(ttl_minutes, 1)))
    owner = machine_name(locked_by)

    with connect_guarded(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT operation_key, locked_by, locked_at, expires_at, status, module, details
            FROM system_locks
            WHERE operation_key = ? AND status = 'running' AND expires_at > ?
            """,
            (operation_key, now_text),
        ).fetchone()
        if row:
            current = LockInfo(**dict(row))
            conn.rollback()
            raise OperationBlockedError(
                "Operacion bloqueada por seguridad. "
                f"'{current.operation_key}' sigue en uso por {current.locked_by} "
                f"desde {current.locked_at}. Expira automaticamente en {current.expires_at}."
            )
        conn.execute(
            """
            INSERT OR REPLACE INTO system_locks (
                operation_key, locked_by, locked_at, expires_at, status, module, details
            ) VALUES (?, ?, ?, ?, 'running', ?, ?)
            """,
            (operation_key, owner, now_text, expires_text, module, details),
        )
        conn.commit()
    return LockInfo(operation_key, owner, now_text, expires_text, "running", module, details)


def release_lock(db_path: Path, operation_key: str, *, status: str = "done") -> None:
    init_guard_schema(db_path)
    with connect_guarded(db_path) as conn:
        conn.execute(
            "UPDATE system_locks SET status = ?, expires_at = ? WHERE operation_key = ?",
            (status, _now_text(), operation_key),
        )
        conn.commit()


def clear_stale_locks(db_path: Path) -> int:
    init_guard_schema(db_path)
    now = _now_text()
    with connect_guarded(db_path) as conn:
        cur = conn.execute(
            "UPDATE system_locks SET status = 'expired' WHERE status = 'running' AND expires_at <= ?",
            (now,),
        )
        conn.commit()
        return int(cur.rowcount or 0)


@contextlib.contextmanager
def operation_lock(
    settings: Settings,
    operation_key: str,
    *,
    module: str,
    details: str = "",
    ttl_minutes: int = 30,
) -> Iterator[None]:
    if not settings.guarded_mode:
        yield
        return

    acquire_lock(
        settings.db_path,
        operation_key,
        module=module,
        locked_by=settings.machine_name,
        details=details,
        ttl_minutes=ttl_minutes,
    )
    try:
        yield
    except Exception:
        release_lock(settings.db_path, operation_key, status="failed")
        raise
    else:
        release_lock(settings.db_path, operation_key, status="done")


@contextlib.contextmanager
def guarded_database_operation(
    settings: Settings,
    operation_key: str,
    *,
    module: str,
    action: str,
    details: str = "",
    ttl_minutes: int = 30,
    backup_reason: str | None = None,
) -> Iterator[Path | None]:
    backup_path: Path | None = None
    with operation_lock(settings, operation_key, module=module, details=details, ttl_minutes=ttl_minutes):
        log_event(
            settings.db_path,
            module=module,
            action=action,
            status="STARTED",
            severity="INFO",
            details=details,
            context={"machine": settings.machine_name, "mode": settings.app_mode},
        )
        if backup_reason:
            backup_path = create_sqlite_backup(settings.db_path, backup_reason)
            log_event(
                settings.db_path,
                module=module,
                action="Backup automatico previo",
                status="OK",
                severity="INFO",
                entity_type="backup",
                entity_id=str(backup_path.name),
                details=f"Backup creado antes de: {action}",
                context={"path": str(backup_path)},
            )
        try:
            yield backup_path
        except Exception as exc:
            log_event(
                settings.db_path,
                module=module,
                action=action,
                status="ERROR",
                severity="ERROR",
                details=str(exc),
                context={"machine": settings.machine_name, "mode": settings.app_mode},
            )
            raise
        else:
            log_event(
                settings.db_path,
                module=module,
                action=action,
                status="OK",
                severity="INFO",
                details=details,
                context={"machine": settings.machine_name, "mode": settings.app_mode},
            )


def create_sqlite_backup(db_path: Path, reason: str) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"No existe la base de datos: {db_path}")
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason.strip())[:80] or "auto"
    target = backup_dir / f"gestorwoo-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe_reason}.sqlite3"
    source_connection = sqlite3.connect(db_path)
    try:
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
    finally:
        source_connection.close()
    return target


def check_database_writable(db_path: Path) -> tuple[bool, str]:
    if not db_path.exists():
        return False, "La base de datos no existe."
    try:
        with connect_guarded(db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS system_healthcheck (id INTEGER PRIMARY KEY, checked_at TEXT NOT NULL)")
            conn.execute("INSERT INTO system_healthcheck (checked_at) VALUES (?)", (_now_text(),))
            conn.execute("DELETE FROM system_healthcheck WHERE id NOT IN (SELECT MAX(id) FROM system_healthcheck)")
            conn.commit()
        return True, "Lectura/escritura OK"
    except sqlite3.Error as exc:
        return False, f"No se pudo escribir en la base: {exc}"


def latest_backup(db_path: Path) -> Path | None:
    backup_dir = db_path.parent / "backups"
    if not backup_dir.exists():
        return None
    backups = sorted(backup_dir.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def _now_text() -> str:
    return _dt_text(datetime.now())


def _dt_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")

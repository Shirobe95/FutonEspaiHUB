from __future__ import annotations

import platform
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from gestorwoo.config import load_settings
from gestorwoo.cloud.client import connection_info
from gestorwoo.guard import active_locks, check_database_writable, clear_stale_locks, init_guard_schema, latest_backup, stale_locks
from gestorwoo.security import init_security_schema
from gestorwoo.pathing import calculo_coste_root, futon_root, gestorwoo_root


TABLES_TO_COUNT = (
    "products",
    "product_variations",
    "inventory_items",
    "supplier_prices",
    "heca_stock",
    "price_change_proposals",
    "inventory_change_history",
    "security_logs",
    "system_locks",
)


@dataclass(frozen=True)
class DiagnosticResult:
    text: str
    ok: bool


def collect_diagnostics() -> DiagnosticResult:
    settings = load_settings()
    root = futon_root()
    gestor_root = gestorwoo_root()
    calc_root = calculo_coste_root()
    db_path = settings.db_path

    lines: list[str] = []
    warnings: list[str] = []

    lines.append("DIAGNOSTICO FUTONHUB")
    lines.append("=" * 26)
    lines.append(f"Python: {sys.version.split()[0]}")
    lines.append(f"Sistema: {platform.system()} {platform.release()}")
    lines.append(f"Ejecutable Python: {sys.executable}")
    lines.append(f"Carpeta actual: {Path.cwd()}")
    lines.append("")

    lines.append("MODO DE TRABAJO")
    lines.append("-" * 26)
    lines.append(f"Modo HUB: {settings.app_mode}")
    lines.append(f"Maquina: {settings.machine_name}")
    lines.append(f".env activo: {settings.env_path} {'OK' if settings.env_path.exists() else 'NO EXISTE'}")
    lines.append("Red compartida: desactivada/no requerida")
    lines.append(f"Rol sincronización: {settings.sync_role}")
    lines.append(f"Usuario/email HUB: {settings.hub_user_email or '(no configurado)'}")
    lines.append("")

    cloud_info = connection_info(settings)
    lines.append("SUPABASE / ONLINE")
    lines.append("-" * 26)
    lines.append(f"Configurado: {'SI' if cloud_info.configured else 'NO'}")
    lines.append(f"URL: {cloud_info.url or '(no configurada)'}")
    lines.append(f"Anon key: {'OK' if cloud_info.anon_key_present else 'FALTA'}")
    lines.append(f"Service key local: {'presente' if cloud_info.service_key_present else 'no configurada'}")
    if settings.app_mode == 'supabase_guarded' and not cloud_info.configured:
        warnings.append("El modo es supabase_guarded, pero falta configurar Supabase URL/Anon Key.")
    lines.append("")

    lines.append("RUTAS")
    lines.append("-" * 26)
    lines.append(f"Raiz del proyecto: {root}")
    lines.append(f"GestorWoo: {gestor_root} {'OK' if gestor_root.exists() else 'NO EXISTE'}")
    lines.append(f"CalculoCoste: {calc_root} {'OK' if calc_root.exists() else 'NO EXISTE'}")
    lines.append("")

    lines.append("BASE DE DATOS ACTIVA")
    lines.append("-" * 26)
    lines.append(f"GESTORWOO_DB_PATH resuelto: {db_path}")
    lines.append(f"Existe: {'SI' if db_path.exists() else 'NO'}")
    if db_path.exists():
        lines.append(f"Tamano: {_format_size(db_path.stat().st_size)}")
        writable_ok, writable_msg = check_database_writable(db_path)
        init_guard_schema(db_path)
        init_security_schema(db_path)
        lines.append(f"Escritura: {writable_msg}")
        if not writable_ok:
            warnings.append(writable_msg)
        try:
            counts = _sqlite_counts(db_path)
            for table in TABLES_TO_COUNT:
                value = counts.get(table)
                lines.append(f"{table}: {value if value is not None else 'tabla no encontrada'}")
            if (counts.get("products") or 0) == 0 and (counts.get("product_variations") or 0) == 0:
                warnings.append("La base activa existe, pero no contiene productos ni variaciones.")
        except sqlite3.Error as exc:
            warnings.append(f"No se pudo leer la base activa: {exc}")
    else:
        warnings.append("La base activa no existe. El HUB podria crear una base nueva vacia si se abre un modulo.")
    lines.append("")

    lines.append("BACKUPS")
    lines.append("-" * 26)
    backup = latest_backup(db_path)
    if backup:
        lines.append(f"Ultimo backup: {backup.name} · {_format_size(backup.stat().st_size)}")
        lines.append(f"Ruta: {backup}")
    else:
        lines.append("Ultimo backup: no encontrado")
        warnings.append("No se encontraron backups en la carpeta esperada.")
    lines.append("")

    lines.append("BLOQUEOS DE SEGURIDAD")
    lines.append("-" * 26)
    if db_path.exists():
        expired = clear_stale_locks(db_path)
        if expired:
            lines.append(f"Bloqueos caducados limpiados: {expired}")
        locks = active_locks(db_path)
        stale = stale_locks(db_path)
        if locks:
            warnings.append(f"Hay {len(locks)} bloqueo(s) activo(s).")
            for lock in locks:
                lines.append(f"ACTIVO: {lock.operation_key} · {lock.locked_by} · hasta {lock.expires_at} · {lock.details}")
        else:
            lines.append("Bloqueos activos: ninguno")
        if stale:
            for lock in stale:
                lines.append(f"CADUCADO: {lock.operation_key} · {lock.locked_by} · expiro {lock.expires_at}")
    else:
        lines.append("Bloqueos activos: no se pudo comprobar porque no existe la base")
    lines.append("")

    lines.append("CONTROL DE DUPLICADOS")
    lines.append("-" * 26)
    duplicate_candidates = [
        root / "data" / "gestorwoo.sqlite3",
        root / "_aislado_sqlite_duplicada_vacia" / "gestorwoo.sqlite3",
    ]
    for candidate in duplicate_candidates:
        if candidate.exists():
            marker = "ACTIVA" if candidate.resolve() == db_path.resolve() else "NO ACTIVA"
            lines.append(f"{candidate}: {marker}, {_format_size(candidate.stat().st_size)}")
            if marker != "ACTIVA" and candidate.parent.name != "_aislado_sqlite_duplicada_vacia":
                warnings.append(f"Hay una SQLite duplicada fuera de GestorWoo/data: {candidate}")
        else:
            lines.append(f"{candidate}: no existe")
    lines.append("")

    if warnings:
        lines.append("AVISOS")
        lines.append("-" * 26)
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("Estado general: OK")

    return DiagnosticResult(text="\n".join(lines), ok=not warnings)


def print_diagnostics() -> int:
    result = collect_diagnostics()
    print(result.text)
    return 0 if result.ok else 1


def _sqlite_counts(db_path: Path) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        for table in TABLES_TO_COUNT:
            if table not in tables:
                counts[table] = None
            else:
                counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"

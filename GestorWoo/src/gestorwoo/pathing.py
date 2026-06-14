from __future__ import annotations

import os
import sys
from pathlib import Path


APP_FOLDER_NAME = "GestorWoo"
COST_FOLDER_NAME = "CalculoCoste"
DEFAULT_DB_RELATIVE_PATH = Path("data") / "gestorwoo.sqlite3"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def futon_root() -> Path:
    """Devuelve la raíz del proyecto FutonEspaiHUB.

    Prioridad:
    1. Variable FUTON_ESPAI_ROOT, si existe.
    2. Carpeta del ejecutable, si estamos en .exe.
    3. Estructura normal del código fuente.
    """
    configured = os.getenv("FUTON_ESPAI_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name == APP_FOLDER_NAME:
            return exe_dir.parent
        if (exe_dir / APP_FOLDER_NAME).exists():
            return exe_dir
        return exe_dir.parent

    # pathing.py vive en FutonEspaiHUB/GestorWoo/src/gestorwoo/pathing.py
    return Path(__file__).resolve().parents[3]


def gestorwoo_root() -> Path:
    root = futon_root()
    if root.name == APP_FOLDER_NAME:
        return root
    return root / APP_FOLDER_NAME


def calculo_coste_root() -> Path:
    return futon_root() / COST_FOLDER_NAME


def resolve_gestorwoo_path(path_value: str | os.PathLike[str] | None, default: Path | None = None) -> Path:
    """Resuelve rutas relativas siempre desde GestorWoo, no desde el cwd actual."""
    if path_value is None or str(path_value).strip() == "":
        candidate = default or DEFAULT_DB_RELATIVE_PATH
    else:
        candidate = Path(path_value).expanduser()

    if candidate.is_absolute():
        return candidate.resolve()
    return (gestorwoo_root() / candidate).resolve()


def default_db_path() -> Path:
    return resolve_gestorwoo_path(DEFAULT_DB_RELATIVE_PATH)

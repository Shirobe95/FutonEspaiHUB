"""Version visible de la aplicacion (semver del paquete + commit desplegado por el launcher)."""
from __future__ import annotations

from pathlib import Path

from futonhub import __version__

# GestorWoo/src/futonhub/version_info.py -> raiz de la instalacion (donde el launcher escribe SOURCE_COMMIT)
_INSTALL_ROOT = Path(__file__).resolve().parents[3]


def deployed_commit(root: Path | None = None) -> str:
    """Commit completo desplegado por el launcher, o '' si no hay (ejecucion desde un clon)."""
    try:
        value = ((root or _INSTALL_ROOT) / "SOURCE_COMMIT").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""
    return value if len(value) == 40 and all(c in "0123456789abcdef" for c in value.lower()) else ""


def app_version_label(root: Path | None = None) -> str:
    """``v0.6.4`` o ``v0.6.4 · a1b2c3d4e5f6`` cuando el launcher ha desplegado un commit."""
    commit = deployed_commit(root)
    return f"v{__version__}" + (f" · {commit[:12]}" if commit else "")

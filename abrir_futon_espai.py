from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GESTOR = ROOT / "GestorWoo" / "gestorwoo.py"

if not GESTOR.exists():
    raise SystemExit(f"No se encontro el lanzador: {GESTOR}")

raise SystemExit(
    subprocess.call([sys.executable, str(GESTOR), "hub"], cwd=str(GESTOR.parent))
)

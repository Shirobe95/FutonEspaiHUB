"""Compuerta para tests que dependen de artefactos generados por las auditorias de Codex.

Esos artefactos (``auditoria/out/...`` y los scripts ``auditoria/*.py``) NO estan versionados,
asi que en un clon limpio estos tests no pueden ejecutarse. En lugar de fallar con
``FileNotFoundError`` se omiten con un motivo explicito; en una maquina que SI tiene los
artefactos se ejecutan con normalidad.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_OUT = REPO_ROOT / "auditoria" / "out"


def require_audit_out(*sub_paths: str) -> None:
    """Omite el modulo si falta ``auditoria/out`` (o alguna de las rutas indicadas)."""
    missing = [str(AUDIT_OUT / p) for p in sub_paths if not (AUDIT_OUT / p).exists()]
    if not AUDIT_OUT.is_dir():
        raise unittest.SkipTest(
            "Requiere artefactos de auditoria no versionados (auditoria/out); "
            "ejecutar en una maquina que los tenga."
        )
    if missing:
        raise unittest.SkipTest("Faltan artefactos de auditoria: " + ", ".join(missing[:3]))


def skip_unless_script(script_name: str) -> None:
    """Omite el modulo si el script ``auditoria/<script_name>`` no esta en el repositorio."""
    if not (REPO_ROOT / "auditoria" / script_name).is_file():
        raise unittest.SkipTest(
            f"El script auditoria/{script_name} no esta versionado en este repositorio."
        )


def requires_audit_out(obj):
    """Decorador (clase o test): omite si no existe ``auditoria/out`` (artefactos no versionados)."""
    return unittest.skipUnless(
        AUDIT_OUT.is_dir(),
        "Requiere artefactos de auditoria no versionados (auditoria/out); ejecutar en una maquina que los tenga.",
    )(obj)

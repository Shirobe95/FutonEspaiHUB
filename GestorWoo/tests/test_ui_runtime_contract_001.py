"""Contratos estaticos de la UI (auditoria 2026-10, corte 2).

Cada comprobacion corresponde a un fallo que solo se manifestaba en tiempo de ejecucion,
al pulsar un boton o al producirse un error: NameError por lambdas que capturan la variable
de ``except ... as exc``, ``_render_content`` inexistente y excepciones sin importar.
"""
from __future__ import annotations

import ast
import builtins
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

UI_FILES = sorted((SRC / "futonhub" / "ui").rglob("*.py")) + sorted((SRC / "gestorwoo").glob("*.py"))

# Modulos con nombres sin definir ya conocidos y pendientes de otro corte (codigo legacy/CLI).
# Esta lista solo debe ADELGAZAR: no anadir entradas nuevas.
KNOWN_PENDING_EXCEPTION_NAMES: dict[str, set[str]] = {}


def lambdas_capturing_except_variable(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for handler in ast.walk(ast.parse(source)):
        if not (isinstance(handler, ast.ExceptHandler) and handler.name):
            continue
        for node in ast.walk(handler):
            if isinstance(node, ast.Lambda):
                params = {a.arg for a in node.args.args + node.args.kwonlyargs}
                used = {n.id for n in ast.walk(node.body) if isinstance(n, ast.Name)}
                if handler.name in used and handler.name not in params:
                    found.append((node.lineno, handler.name))
    return found


def undefined_exception_names(source: str) -> set[str]:
    tree = ast.parse(source)
    defined = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                defined.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
    star = any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree))
    if star:
        return set()
    missing: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for item in types:
                if isinstance(item, ast.Name) and item.id not in defined:
                    missing.add(item.id)
    return missing


class UiRuntimeContractTests(unittest.TestCase):
    def test_no_lambda_captures_the_except_variable(self) -> None:
        offenders = []
        for path in UI_FILES:
            for line, name in lambdas_capturing_except_variable(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(SRC)}:{line} lambda usa '{name}' tras salir del except")
        self.assertEqual(offenders, [])

    def test_exception_classes_used_in_ui_are_defined(self) -> None:
        offenders = []
        for path in UI_FILES:
            rel = str(path.relative_to(SRC))
            missing = undefined_exception_names(path.read_text(encoding="utf-8")) - KNOWN_PENDING_EXCEPTION_NAMES.get(rel, set())
            if missing:
                offenders.append(f"{rel}: {sorted(missing)}")
        self.assertEqual(offenders, [])

    def test_helpers_detect_the_original_bugs(self) -> None:
        bad = "try:\n    pass\nexcept Exception as exc:\n    after(0, lambda: show(exc))\n"
        good = "try:\n    pass\nexcept Exception as exc:\n    after(0, lambda error=exc: show(error))\n"
        self.assertEqual(lambdas_capturing_except_variable(bad), [(4, "exc")])
        self.assertEqual(lambdas_capturing_except_variable(good), [])
        self.assertEqual(undefined_exception_names("try:\n    pass\nexcept CloudAuditError:\n    pass\n"), {"CloudAuditError"})
        self.assertEqual(undefined_exception_names("from x import CloudAuditError\ntry:\n    pass\nexcept CloudAuditError:\n    pass\n"), set())

    def test_prototype_never_calls_a_missing_method(self) -> None:
        try:
            from futonhub.ui.erp.prototype import FutonHubErpPrototype
        except Exception as exc:  # pragma: no cover - sin tkinter
            self.skipTest(f"prototype no importable: {exc}")
        source = (SRC / "futonhub" / "ui" / "erp" / "prototype.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned = {
            n.attr
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name) and n.value.id == "self"
        }
        missing = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and node.func.attr.startswith("_")
                and not node.func.attr.startswith("__")
            ):
                name = node.func.attr
                if not hasattr(FutonHubErpPrototype, name) and name not in assigned:
                    missing.setdefault(name, node.lineno)
        self.assertEqual(missing, {})

    def test_cloud_prices_imports_cloud_audit_error(self) -> None:
        source = (SRC / "futonhub" / "ui" / "erp" / "cloud_prices.py").read_text(encoding="utf-8")
        self.assertEqual(undefined_exception_names(source), set())


if __name__ == "__main__":
    unittest.main()

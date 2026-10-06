"""Integridad de los servicios cloud (auditoria 2026-10, corte 3).

1. Ningun modulo de ``futonhub/cloud/services`` referencia nombres sin definir (antes habia
   ~40 en funciones duplicadas e inalcanzables que se han eliminado).
2. ``services/rollback.py`` (que tenia nombres sin definir) funciona y es equivalente a la
   implementacion que usa hoy la UI (``operational_legacy``).
"""
from __future__ import annotations

import ast
import builtins
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SERVICES = sorted((SRC / "futonhub" / "cloud" / "services").glob("*.py"))


def undefined_names(source: str) -> set[str]:
    """Aproximacion a pyflakes: nombres leidos que no son locales, globales del modulo ni builtins."""
    tree = ast.parse(source)
    module_names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    return set()
                module_names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            module_names.add(node.id)
        elif isinstance(node, ast.arg):
            module_names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            module_names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            module_names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            module_names.add(node.name)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in module_names
    }


class ServicesUndefinedNamesTests(unittest.TestCase):
    def test_no_service_module_reads_an_undefined_name(self) -> None:
        offenders = {}
        for path in SERVICES:
            missing = undefined_names(path.read_text(encoding="utf-8"))
            if missing:
                offenders[path.name] = sorted(missing)
        self.assertEqual(offenders, {})

    def test_checker_detects_undefined_names(self) -> None:
        self.assertEqual(undefined_names("def f():\n    return missing_helper(1)\n"), {"missing_helper"})
        self.assertEqual(undefined_names("import os\ndef f(a):\n    b = a\n    return os.name, b\n"), set())

    def test_removed_dead_duplicates_are_not_referenced_by_the_live_code(self) -> None:
        import gestorwoo.cloud.operational as operational
        from futonhub.ui.erp import cloud_prices  # noqa: F401  (importa price_heart_attack_tests)

        for name in (
            "run_cloud_list_real_price_proposals",
            "run_cloud_search_inventory",
            "run_cloud_import_woocommerce_product",
            "run_cloud_woocommerce_publish_preview",
            "price_heart_attack_tests",
        ):
            self.assertTrue(callable(getattr(operational, name)), name)


def _plain(text: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").replace("\u00b7", "-")


class _Query:
    def __init__(self, client: "_Client", table: str) -> None:
        self.client, self.table = client, table
        self.filters: dict = {}
        self.payload = None
        self.op = "select"

    def select(self, *a, **k):
        self.op = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def __getattr__(self, name):  # order/limit/insert...
        return lambda *a, **k: self

    def execute(self):
        if self.op == "update":
            self.client.updates.append((self.table, dict(self.payload), dict(self.filters)))
            return SimpleNamespace(data=[{**self.client.current[self.table], **self.payload}])
        return SimpleNamespace(data=[dict(self.client.current[self.table])])


class _Rpc:
    def __init__(self, client: "_Client", name: str, args: dict) -> None:
        self.client, self.name, self.args = client, name, args

    def execute(self):
        self.client.rpcs.append((self.name, self.args))
        if self.name == "futonhub_read_snapshot_by_operation_id":
            return SimpleNamespace(data=[self.client.snapshot])
        return SimpleNamespace(data=[self.args])


class _Client:
    def __init__(self) -> None:
        self.current = {"business_constants": {"key": "K1", "value": 2, "unit": "EUR"}}
        self.snapshot = {
            "operation_id": "OP-1", "module": "Configuracion", "action": "save", "entity_type": "business_constant",
            "entity_id": "K1", "before_data": {"key": "K1", "value": 1, "unit": "EUR", "created_at": "x"},
        }
        self.updates: list = []
        self.rpcs: list = []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, args):
        return _Rpc(self, name, args)


def make_session() -> SimpleNamespace:
    return SimpleNamespace(client=_Client(), role="admin", user_id="u-1", email="a@b.c")


class RollbackServiceTests(unittest.TestCase):
    def test_service_and_live_implementation_agree_on_preview(self) -> None:
        from futonhub.cloud.services import rollback as service
        import gestorwoo.cloud.operational_legacy as legacy

        a = service.preview_rollback_from_snapshot(make_session(), "OP-1")
        b = legacy.preview_rollback_from_snapshot(make_session(), "OP-1")
        for key in ("table", "key", "key_value", "before_data", "current_data"):
            self.assertEqual(a[key], b[key], key)
        # El texto solo difiere en tildes entre las dos copias.
        self.assertEqual(_plain(service.format_rollback_preview(a)), _plain(legacy.format_rollback_preview(b)))

    def test_service_execute_writes_snapshot_audit_and_restores_values(self) -> None:
        from futonhub.cloud.services import rollback as service

        session = make_session()
        result = service.execute_rollback_from_snapshot(session, "OP-1")
        table, payload, filters = session.client.updates[0]
        self.assertEqual((table, filters), ("business_constants", {"key": "K1"}))
        self.assertEqual(payload["value"], 1)
        self.assertEqual(payload["updated_by"], "u-1")
        self.assertNotIn("created_at", payload)
        self.assertNotIn("key", payload)
        names = [name for name, _ in session.client.rpcs]
        self.assertIn("futonhub_write_operation_snapshot", names)
        self.assertIn("futonhub_write_audit_log", names)
        self.assertEqual(result["key_value"], "K1")
        snapshot_args = dict(session.client.rpcs)["futonhub_write_operation_snapshot"]
        self.assertEqual(snapshot_args["p_before_data"]["value"], 2)  # estado previo al rollback

    def test_non_admin_cannot_roll_back(self) -> None:
        from futonhub.cloud.audit import CloudAuditError
        from futonhub.cloud.services import rollback as service

        session = make_session()
        session.role = "worker"
        with self.assertRaises(CloudAuditError):
            service.execute_rollback_from_snapshot(session, "OP-1")
        self.assertEqual(session.client.updates, [])


if __name__ == "__main__":
    unittest.main()

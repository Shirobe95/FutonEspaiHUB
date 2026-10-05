"""Contrato de uso de AuditEvent / OperationSnapshot (auditoria 2026-10, corte 1).

Las llamadas con kwargs inexistentes lanzaban TypeError, que los ``except Exception: pass``
de los servicios tragaban: la operacion se hacia pero sin snapshot ni audit log.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gestorwoo.cloud.audit import AuditEvent, OperationSnapshot  # noqa: E402

CLASSES = {"AuditEvent": AuditEvent, "OperationSnapshot": OperationSnapshot}


def _invalid_calls(source: str) -> list[tuple[int, str, str]]:
    problems: list[tuple[int, str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        cls = CLASSES.get(name)
        if cls is None:
            continue
        fields = {f.name for f in dataclasses.fields(cls)}
        if node.args:
            problems.append((node.lineno, name, "argumentos posicionales"))
        for kw in node.keywords:
            if kw.arg is None:
                continue  # **kwargs: no verificable estaticamente
            if kw.arg not in fields:
                problems.append((node.lineno, name, kw.arg))
    return problems


class AuditEventContractTests(unittest.TestCase):
    def test_all_source_calls_use_declared_fields(self) -> None:
        offenders: list[str] = []
        for path in sorted(SRC.rglob("*.py")):
            for line, name, kwarg in _invalid_calls(path.read_text(encoding="utf-8")):
                offenders.append(f"{path.relative_to(SRC)}:{line} {name}({kwarg}=...)")
        self.assertEqual(offenders, [])

    def test_checker_detects_invalid_kwargs(self) -> None:
        bad = "AuditEvent(module='m', action='a', status='s', entity_table='t', metadata={})"
        self.assertEqual(
            sorted(k for _, _, k in _invalid_calls(bad)), ["entity_table", "metadata"]
        )
        bad2 = "OperationSnapshot(operation_id='o', module='m', action='a', entity_type='t', entity_id='1', before_data={}, after_data={})"
        self.assertEqual([k for _, _, k in _invalid_calls(bad2)], ["after_data"])


class _Chain:
    def __init__(self, client: "_Client", table: str) -> None:
        self.client, self.table = client, table

    def __getattr__(self, name: str):
        def call(*args, **kwargs):
            self.client.table_calls.append((self.table, name))
            return self
        return call

    def execute(self):
        return SimpleNamespace(data=[])


class _Rpc:
    def __init__(self, client: "_Client", name: str, args: dict) -> None:
        self.client, self.name, self.args = client, name, args

    def execute(self):
        self.client.rpcs.append((self.name, self.args))
        return SimpleNamespace(data=[self.args])


class _Client:
    def __init__(self) -> None:
        self.rpcs: list[tuple[str, dict]] = []
        self.table_calls: list[tuple[str, str]] = []

    def table(self, name: str) -> _Chain:
        return _Chain(self, name)

    def rpc(self, name: str, args: dict) -> _Rpc:
        return _Rpc(self, name, args)


class SaveBusinessConstantsWritesAuditTests(unittest.TestCase):
    def test_snapshot_and_audit_log_are_actually_written(self) -> None:
        from futonhub.cloud.services import business_constants as bc

        key = next(iter(bc.DEFAULT_BUSINESS_CONSTANTS))
        client = _Client()
        session = SimpleNamespace(
            client=client, email="t@example.com", user_id="u-1", role="admin"
        )
        result = bc.save_business_constants(session, {key: 1.5})
        self.assertEqual(result["count"], 1)
        names = [name for name, _ in client.rpcs]
        self.assertIn("futonhub_write_operation_snapshot", names)
        self.assertIn("futonhub_write_audit_log", names)
        snap = dict(client.rpcs)["futonhub_write_operation_snapshot"]
        self.assertEqual(snap["p_entity_type"], "business_constants")
        self.assertEqual(json.loads(snap["p_reason"]), {"count": 1})
        audit = dict(client.rpcs)["futonhub_write_audit_log"]
        self.assertEqual(audit["p_entity_type"], "business_constants")
        self.assertEqual(audit["p_after_data"], {"keys": [key]})


if __name__ == "__main__":
    unittest.main()

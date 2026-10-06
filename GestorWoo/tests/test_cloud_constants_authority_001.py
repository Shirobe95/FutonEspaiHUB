"""Supabase es la fuente de verdad de las constantes (decision del negocio 2026-10-06).

Antes, el bloqueo de bajada de precio usaba GESTORWOO_PRICE_DROP_BLOCK_PERCENT del .env (60 por defecto) e
ignoraba PRICE_DROP_BLOCK_PERCENT de Supabase (30): cada PC podia bloquear distinto.
"""
from __future__ import annotations

import ast
import dataclasses
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.services import business_constants as bc  # noqa: E402
from futonhub.cloud.services.prices import price_safety_preview  # noqa: E402
from gestorwoo.config import load_settings  # noqa: E402


class _Query:
    def __init__(self, client: "_Client") -> None:
        self.client = client

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        self.client.queries += 1
        if self.client.error:
            raise RuntimeError("sin red")
        return SimpleNamespace(data=self.client.rows)


class _Client:
    def __init__(self, rows=None, error: bool = False) -> None:
        self.rows, self.error, self.queries = rows or [], error, 0

    def table(self, name):
        assert name == "business_constants"
        return _Query(self)


def session(value=30, **kw):
    rows = [{"key": "PRICE_DROP_BLOCK_PERCENT", "value": value}] if value is not None else []
    return SimpleNamespace(client=_Client(rows, **kw))


class CloudThresholdTests(unittest.TestCase):
    def setUp(self) -> None:
        bc._threshold_cache.clear()

    def test_reads_the_supabase_value(self) -> None:
        self.assertEqual(bc.cloud_price_drop_block_percent(session(30)), 30.0)

    def test_invalid_or_missing_values_fall_back_to_none(self) -> None:
        for bad in (0, -5, 150, "abc", "nan", None):
            bc._threshold_cache.clear()
            with self.subTest(bad=bad):
                self.assertIsNone(bc.cloud_price_drop_block_percent(session(bad)))
        bc._threshold_cache.clear()
        self.assertIsNone(bc.cloud_price_drop_block_percent(session(30, error=True)))
        self.assertIsNone(bc.cloud_price_drop_block_percent(SimpleNamespace()))

    def test_result_is_cached_briefly(self) -> None:
        s = session(30)
        for _ in range(5):
            bc.cloud_price_drop_block_percent(s)
        self.assertEqual(s.client.queries, 1)
        bc.cloud_price_drop_block_percent(s, use_cache=False)
        self.assertEqual(s.client.queries, 2)

    def test_settings_get_the_cloud_threshold_and_keep_a_coherent_warning(self) -> None:
        base = dataclasses.replace(load_settings(), price_drop_block_percent=60.0, price_drop_warning_percent=30.0)
        updated = bc.apply_cloud_price_thresholds(session(30), base)
        self.assertEqual(updated.price_drop_block_percent, 30.0)
        self.assertEqual(updated.price_drop_warning_percent, 15.0)  # nunca >= bloqueo
        self.assertEqual(base.price_drop_block_percent, 60.0)  # el original no se muta
        bc._threshold_cache.clear()
        self.assertIs(bc.apply_cloud_price_thresholds(session(30, error=True), base), base)

    def test_a_35_percent_drop_is_blocked_with_the_supabase_threshold_but_not_with_the_env_one(self) -> None:
        base = dataclasses.replace(load_settings(), price_drop_block_percent=60.0, price_drop_warning_percent=30.0)
        item = {"price": "100", "type": "simple"}
        self.assertEqual(price_safety_preview(item, "product", 65.0, base)["status"], "WARNING")
        cloud = bc.apply_cloud_price_thresholds(session(30), base)
        self.assertEqual(price_safety_preview(item, "product", 65.0, cloud)["status"], "ERROR")

    def test_every_price_safety_call_uses_the_cloud_thresholds(self) -> None:
        offenders = []
        for rel in (
            "futonhub/cloud/services/price_proposals.py",
            "futonhub/cloud/services/woocommerce_publish.py",
            "gestorwoo/cloud/operational_legacy.py",
        ):
            tree = ast.parse((SRC / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_price_safety_preview":
                    last = node.args[-1]
                    ok = isinstance(last, ast.Call) and getattr(last.func, "id", "") == "apply_cloud_price_thresholds"
                    if not ok:
                        offenders.append(f"{rel}:{node.lineno}")
        self.assertEqual(offenders, [])


class LegacyCacheTests(unittest.TestCase):
    ROWS = [
        {"key": "COSTE_TOTAL_DESCARGA_FUTONES_IVA", "value": 375.35},
        {"key": "COSTE_DIARIO_ALMACENAJE_M3", "value": 0.485},
        {"key": "COSTE_DESCARGA_FUTONES_UNIDAD", "value": 2.3},
        {"key": "PRICE_DROP_BLOCK_PERCENT", "value": 30},
    ]

    def setUp(self) -> None:
        import tempfile

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "constantes_negocio.json"
        self.addCleanup(bc.enable_legacy_constants_cache, None)

    def test_disabled_by_default_writes_nothing(self) -> None:
        bc.enable_legacy_constants_cache(None)
        bc.list_business_constants(SimpleNamespace(client=_Client(self.ROWS)))
        self.assertFalse(self.path.exists())

    def test_cloud_values_overwrite_stale_local_ones_and_keep_the_rest(self) -> None:
        import json

        self.path.write_text(json.dumps({"COSTE_TOTAL_DESCARGA_FUTONES_IVA": 308.0, "COSTE_DESCARGA_FUTONES_UNIDAD": 1.69, "IMPORTES_VARIOS": 100.0}), encoding="utf-8")
        bc.enable_legacy_constants_cache(self.path)
        bc.list_business_constants(SimpleNamespace(client=_Client(self.ROWS)))
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["COSTE_TOTAL_DESCARGA_FUTONES_IVA"], 375.35)
        self.assertEqual(saved["COSTE_DESCARGA_FUTONES_UNIDAD"], 2.3)
        self.assertEqual(saved["COSTE_DIARIO_ALMACENAJE_M3"], 0.485)
        self.assertEqual(saved["IMPORTES_VARIOS"], 100.0)
        self.assertNotIn("PRICE_DROP_BLOCK_PERCENT", saved)  # solo las constantes que lee el calculo legacy

    def test_defaults_without_cloud_rows_are_never_written(self) -> None:
        bc.enable_legacy_constants_cache(self.path)
        bc.list_business_constants(SimpleNamespace(client=_Client([])))
        bc.list_business_constants(SimpleNamespace(client=_Client(error=True)))
        self.assertFalse(self.path.exists())

    def test_cache_errors_never_break_the_read(self) -> None:
        bc.enable_legacy_constants_cache(Path(self.temp.name) / "no" / "\0bad" / "x.json")
        result = bc.list_business_constants(SimpleNamespace(client=_Client(self.ROWS)))
        self.assertEqual(result["COSTE_TOTAL_DESCARGA_FUTONES_IVA"]["value"], 375.35)

    def test_required_constants_path_also_refreshes_the_cache(self) -> None:
        import json

        rows = [{"key": key, "value": value} for key, value in (("COSTE_TOTAL_DESCARGA_FUTONES_IVA", 375.35), ("COSTE_DIARIO_ALMACENAJE_M3", 0.485))]
        bc.enable_legacy_constants_cache(self.path)
        bc.list_business_constants(SimpleNamespace(client=_Client(rows)), required_keys=bc.SUPPLIER_ORDER_GENERAL_REQUIRED_CONSTANTS)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["COSTE_DIARIO_ALMACENAJE_M3"], 0.485)

    def test_stale_constants_file_is_no_longer_tracked_in_the_repo(self) -> None:
        repo = ROOT.parent
        self.assertFalse((repo / "CalculoCoste" / "constantes_negocio.json").exists() and (repo / ".git").exists() and self._is_tracked(repo))
        lines = {line.strip() for line in (repo / ".gitignore").read_text(encoding="utf-8").splitlines()}
        self.assertIn("CalculoCoste/constantes_negocio.json", lines)

    @staticmethod
    def _is_tracked(repo: Path) -> bool:
        import subprocess

        result = subprocess.run(["git", "ls-files", "--error-unmatch", "CalculoCoste/constantes_negocio.json"], cwd=repo, capture_output=True)
        return result.returncode == 0


if __name__ == "__main__":
    unittest.main()

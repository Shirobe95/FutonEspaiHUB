from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.services.combination_price_impact import (  # noqa: E402
    CombinationPriceImpactError,
    CombinationPriceImpactService,
    combination_price_impact_runtime_dir,
)


class Release005A5RuntimeCombinationImpactTests(unittest.TestCase):
    def _runtime_copy(self, directory: str | Path) -> Path:
        target = Path(directory) / "combination_price_impact"
        shutil.copytree(combination_price_impact_runtime_dir(), target)
        return target

    def _load_from_runtime_copy(self, runtime_dir: Path) -> CombinationPriceImpactService:
        with patch(
            "futonhub.services.combination_price_impact.combination_price_impact_runtime_dir",
            return_value=runtime_dir,
        ):
            return CombinationPriceImpactService()

    def test_default_combination_service_uses_packaged_runtime_not_legacy_artifacts(self) -> None:
        service = CombinationPriceImpactService()
        description = service.describe()

        self.assertEqual(description["source_kind"], "runtime_config")
        self.assertNotIn("auditoria", description["artifact_root"].replace("\\", "/").casefold())
        self.assertEqual(description["clean_graph_edges"], 926)
        self.assertEqual(description["operational_combinations"], 241)
        self.assertEqual(description["impact_matrix_rows"], 640)
        self.assertEqual(description["excluded_combinations"], 142)

    def test_runtime_checksum_accepts_lf_crlf_and_utf8_bom_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_dir = self._runtime_copy(directory)
            for path in runtime_dir.glob("WOO_MAP_*.csv"):
                text = path.read_text(encoding="utf-8-sig")
                path.write_bytes(("\ufeff" + text.replace("\n", "\r\n")).encode("utf-8"))
            graph_json = runtime_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.json"
            graph_text = graph_json.read_text(encoding="utf-8-sig")
            graph_json.write_bytes(("\ufeff" + graph_text.replace("\n", "\r\n")).encode("utf-8"))
            manifest_json = runtime_dir / "combination_price_impact_manifest.json"
            manifest_text = manifest_json.read_text(encoding="utf-8-sig")
            manifest_json.write_bytes(("\ufeff" + manifest_text.replace("\n", "\r\n")).encode("utf-8"))

            service = self._load_from_runtime_copy(runtime_dir)

        self.assertEqual(service.describe()["source_kind"], "runtime_config")
        self.assertEqual(service.describe()["impact_matrix_rows"], 640)

    def test_runtime_checksum_fails_closed_when_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_dir = self._runtime_copy(directory)
            target = runtime_dir / "WOO_MAP_001A_4_WOO_IMPACT_MATRIX.csv"
            target.write_text(target.read_text(encoding="utf-8-sig") + "\nMANIPULATED\n", encoding="utf-8")

            with self.assertRaisesRegex(CombinationPriceImpactError, "checksum mismatch"):
                self._load_from_runtime_copy(runtime_dir)

    def test_runtime_manifest_sha_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_dir = self._runtime_copy(directory)
            manifest_path = runtime_dir / "combination_price_impact_manifest.json"
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["files"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            with self.assertRaisesRegex(CombinationPriceImpactError, "checksum mismatch"):
                self._load_from_runtime_copy(runtime_dir)

    def test_runtime_missing_file_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime_dir = self._runtime_copy(directory)
            (runtime_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.csv").unlink()

            with self.assertRaisesRegex(CombinationPriceImpactError, "missing runtime artifact"):
                self._load_from_runtime_copy(runtime_dir)

    def test_distributed_runtime_without_auditoria_covers_inventory_and_price_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_src = Path(temporary) / "App" / "src"
            shutil.copytree(
                ROOT / "src" / "futonhub",
                runtime_src / "futonhub",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            shutil.copytree(
                ROOT / "src" / "gestorwoo",
                runtime_src / "gestorwoo",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            self.assertFalse((runtime_src.parent / "auditoria").exists())

            probe = textwrap.dedent(
                """
                import json

                import futonhub.ui.erp.dashboard
                import futonhub.ui.erp.inventory_detail
                import futonhub.ui.erp.inventory_list
                import futonhub.ui.erp.prototype
                from futonhub.services.catalog_operational_baseline import CatalogOperationalBaseline, OPERATIONAL
                from futonhub.services.combination_price_impact import CombinationPriceImpactService, approved_woo_edges_runtime_path
                from futonhub.services.price_woo_catalog_index import build_woo_read_only_index, load_approved_woo_edges, reconcile_woo_contexts
                from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot


                class FakeWoo:
                    writes = 0

                    def iter_products(self):
                        yield {
                            "id": 3655,
                            "type": "variable",
                            "sku": "PARENT-TEST",
                            "name": "Parent",
                            "status": "publish",
                            "regular_price": "",
                            "sale_price": "",
                        }

                    def iter_product_variations(self, parent_id):
                        if int(parent_id) == 3655:
                            yield {
                                "id": 4549,
                                "parent_id": 3655,
                                "sku": "0201002",
                                "name": "Tatami",
                                "status": "publish",
                                "regular_price": "100.00",
                                "sale_price": "",
                            }


                snapshot = PhysicalCatalogSnapshot.load()
                baseline = CatalogOperationalBaseline()
                live_rows = [dict(row) for row in snapshot.rows_by_item_id.values()]
                eligible_rows = snapshot.eligible_live_rows(live_rows)
                enriched_rows = baseline.enrich_rows(eligible_rows)
                target = next(row for row in enriched_rows if row["item_id"] == "201002")
                macao = next(row for row in enriched_rows if row["item_id"] == "402014")

                service = CombinationPriceImpactService()
                assert "auditoria" not in str(service.artifact_root).replace("\\\\", "/").casefold()
                woo_index = build_woo_read_only_index(FakeWoo())
                approved_edges = load_approved_woo_edges(approved_woo_edges_runtime_path())
                sync = reconcile_woo_contexts([target], woo_index=woo_index, approved_edges_by_item_id=approved_edges)
                impact = service.impact_for_changes([{
                    "physical_item_id": "201002",
                    "physical_sku": "0201002",
                    "old_price": "10.00",
                    "new_price": "11.00",
                }])

                assert len(snapshot.item_ids) == 254
                assert len(enriched_rows) == 254
                assert len(baseline.operational_by_item_id) == 188
                assert len(baseline.quarantine_by_item_id) == 66
                assert macao["hub_item_code"] == "0402014"
                assert macao["operational_status"] != OPERATIONAL
                assert macao["can_participate_in_price_propagation"] is False
                assert "4549" == sync["live_price_context_by_physical_item"]["201002"]["woo_id"]
                assert sync["counts"]["ready"] == 1
                assert sync["writes"] == {"woo": 0, "supabase": 0, "sql": 0}
                assert impact["counts"]["included_combinations"] == 19
                assert impact["publication_allowed"] == "NO"

                print(json.dumps({
                    "DISTRIBUTED_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "PRICE_CHANGE_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "COMBINATION_IMPACT_RUNTIME": "PASS",
                    "PHYSICAL_ROWS": len(snapshot.item_ids),
                    "OPERATIONAL_BASELINE_ROWS": len(baseline.rows_by_item_id),
                    "OPERATIONAL": len(baseline.operational_by_item_id),
                    "QUARANTINED": len(baseline.quarantine_by_item_id),
                    "COMBINATION_INCLUDED": impact["counts"]["included_combinations"],
                }, sort_keys=True))
                """
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(runtime_src)
            completed = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=runtime_src.parent,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(completed.stdout.strip()),
                {
                    "COMBINATION_IMPACT_RUNTIME": "PASS",
                    "COMBINATION_INCLUDED": 19,
                    "DISTRIBUTED_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "OPERATIONAL": 188,
                    "OPERATIONAL_BASELINE_ROWS": 254,
                    "PHYSICAL_ROWS": 254,
                    "PRICE_CHANGE_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "QUARANTINED": 66,
                },
            )

    def test_runtime_code_has_no_automatic_auditoria_out_dependency(self) -> None:
        runtime_modules = [
            ROOT / "src" / "futonhub" / "services" / "combination_price_impact.py",
            ROOT / "src" / "futonhub" / "services" / "catalog_operational_baseline.py",
            ROOT / "src" / "futonhub" / "ui" / "erp" / "prototype.py",
            ROOT / "src" / "futonhub" / "ui" / "erp" / "inventory_list.py",
            ROOT / "src" / "futonhub" / "ui" / "erp" / "inventory_detail.py",
            ROOT / "src" / "futonhub" / "ui" / "erp" / "dashboard.py",
        ]
        forbidden = re.compile(r"""(["'])auditoria\1\s*/\s*(["'])out\2|auditoria[/\\]out""")
        for path in runtime_modules:
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

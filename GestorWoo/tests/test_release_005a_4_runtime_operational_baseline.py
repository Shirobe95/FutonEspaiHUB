from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Release005A4RuntimeOperationalBaselineTests(unittest.TestCase):
    def test_distributed_runtime_without_auditoria_runs_full_inventory_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime_root = Path(temporary) / "runtime" / "src"
            shutil.copytree(
                ROOT / "src" / "futonhub",
                runtime_root / "futonhub",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            shutil.copytree(
                ROOT / "src" / "gestorwoo",
                runtime_root / "gestorwoo",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
            self.assertFalse((runtime_root.parent / "auditoria").exists())

            probe = textwrap.dedent(
                """
                import json

                from futonhub.services.catalog_operational_baseline import (
                    CatalogOperationalBaseline,
                    OPERATIONAL,
                )
                from futonhub.services.inventory_visibility import InventoryVisibilityOverrides
                from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot


                snapshot = PhysicalCatalogSnapshot.load()
                baseline = CatalogOperationalBaseline()
                visibility = InventoryVisibilityOverrides.load()
                assert snapshot.expected_count == 254
                assert len(snapshot.item_ids) == 254
                assert len(baseline.rows_by_item_id) == 254
                assert len(baseline.operational_by_item_id) == 188
                assert len(baseline.quarantine_by_item_id) == 66
                assert "auditoria" not in str(baseline.source_path).replace("\\\\", "/").casefold()
                assert "auditoria" not in str(visibility.source_path).replace("\\\\", "/").casefold()

                def list_cloud_inventory_items_by_ids(_session, item_ids):
                    requested = visibility.requested_item_ids(snapshot.item_ids)
                    assert tuple(item_ids) == requested
                    rows = [dict(row) for row in snapshot.rows_by_item_id.values()]
                    for item_id in ("1002010", "1018005", "1020005", "1020006", "1020007", "1020009"):
                        rows.append({
                            "item_id": item_id,
                            "heca_reference": item_id,
                            "hub_item_code": item_id,
                            "name": f"Pack aprobado {item_id}",
                            "family": "Futones",
                            "filter_family": "Futones",
                            "filter_group": "Pack",
                            "filter_size": "Sin definir",
                            "filter_gama": "Sin definir",
                            "item_record_type": "simple",
                            "is_pack": True,
                        })
                    return rows

                requested_item_ids = visibility.requested_item_ids(snapshot.item_ids)
                live_rows = list_cloud_inventory_items_by_ids(object(), requested_item_ids)
                eligible_rows = visibility.apply_to_live_rows(snapshot, live_rows)
                enriched_rows = baseline.enrich_rows(eligible_rows)
                macao = next(row for row in enriched_rows if row["item_id"] == "402014")

                assert len(requested_item_ids) == 260
                assert len(eligible_rows) == 257
                assert len(enriched_rows) == 257
                assert macao["hub_item_code"] == "0402014"
                assert macao["operational_status"] != OPERATIONAL
                assert macao["quarantine_group"] == "DESCATALOGADO"
                assert macao["quarantine_reason"] == "DESCATALOGADO_REVIEW_RESOLVED"
                assert macao["can_participate_in_price_propagation"] is False

                print(json.dumps({
                    "DISTRIBUTED_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "INVENTORY_FULL_RUNTIME_SEQUENCE": "PASS",
                    "PHYSICAL_ROWS": len(snapshot.item_ids),
                    "INVENTORY_VISIBLE_ROWS": len(enriched_rows),
                    "OPERATIONAL_BASELINE_ROWS": len(baseline.rows_by_item_id),
                    "OPERATIONAL": len(baseline.operational_by_item_id),
                    "QUARANTINED": len(baseline.quarantine_by_item_id),
                }))
                """
            )
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(runtime_root)
            completed = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=runtime_root.parent,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(completed.stdout.strip()),
                {
                    "DISTRIBUTED_RUNTIME_WITHOUT_AUDITORIA": "PASS",
                    "INVENTORY_FULL_RUNTIME_SEQUENCE": "PASS",
                    "PHYSICAL_ROWS": 254,
                    "INVENTORY_VISIBLE_ROWS": 257,
                    "OPERATIONAL_BASELINE_ROWS": 254,
                    "OPERATIONAL": 188,
                    "QUARANTINED": 66,
                },
            )


if __name__ == "__main__":
    unittest.main()

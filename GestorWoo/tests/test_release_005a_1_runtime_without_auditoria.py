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


class Release005A1RuntimeWithoutAuditoriaTests(unittest.TestCase):
    def test_runtime_without_auditoria(self) -> None:
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

                from futonhub.app.cli import main
                from futonhub.services.price_initial_live_sync import sync_initial_live_prices
                from futonhub.ui.erp.catalog_filters import CatalogFilterSelection, PhysicalCatalogSnapshot, filter_catalog_rows
                from futonhub.ui.erp.prototype import FutonHubErpPrototype


                class NoWoo:
                    def __init__(self):
                        self.calls = []

                    def get(self, endpoint, params=None):
                        self.calls.append((endpoint, params))
                        raise AssertionError("unlinked Macao must not call Woo")


                snapshot = PhysicalCatalogSnapshot.load()
                macao = snapshot.rows_by_item_id["402014"]
                assert snapshot.expected_count == 254
                assert macao["hub_item_code"] == "0402014"
                assert macao["item_record_type"] == "simple"
                assert macao["is_pack"] == "false"

                visible = filter_catalog_rows(
                    snapshot.rows_by_item_id.values(),
                    CatalogFilterSelection(
                        filter_family=macao["filter_family"],
                        filter_group="Macao",
                        filter_size=macao["filter_size"],
                        filter_gama=macao["filter_gama"],
                    ),
                )
                assert any(row["item_id"] == "402014" for row in visible)

                resolved, strategy = snapshot.resolve_price_row({"item_id": "402014", "hub_item_code": "0402014"})
                assert resolved is not None and resolved["item_id"] == "402014"
                assert strategy == "explicit_item_id"

                live = dict(macao)
                assert snapshot.eligible_live_rows([live]) == [live]

                app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
                app.__dict__["_inventory_catalog_snapshot_cache"] = None
                assert app._price_catalog_snapshot().rows_by_item_id["402014"]["hub_item_code"] == "0402014"

                woo = NoWoo()
                result = sync_initial_live_prices([
                    {
                        "code": "0402014",
                        "name": macao["name"],
                        "source": {
                            "physical_item_id": "402014",
                            "physical_sku": "0402014",
                            "price_operable": True,
                            "item_snapshot": {
                                "item_id": "402014",
                                "item_record_type": "simple",
                                "is_pack": False,
                            },
                        },
                    }
                ], woo_client=woo, session=None)
                context = result["live_price_context_by_physical_item"]["402014"]
                assert context["sync_status"] == "NO_WOO_LINK"
                assert context["price_change_eligible"] == "NO"
                assert context["woo_id"] != "3661"
                assert woo.calls == []
                assert result["writes"] == {"woo": 0, "supabase": 0, "sql": 0}

                assert callable(main)
                print(json.dumps({"health": "PASS", "snapshot_rows": snapshot.expected_count, "macao": context["sync_status"]}))
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
            self.assertEqual(json.loads(completed.stdout.strip()), {"health": "PASS", "snapshot_rows": 254, "macao": "NO_WOO_LINK"})


if __name__ == "__main__":
    unittest.main()

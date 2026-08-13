from __future__ import annotations

import inspect
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


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gestorwoo.windowing import clamped_window_size  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.responsive import (  # noqa: E402
    catalog_filter_bar_layout,
    modal_dimensions_for_viewport,
    shell_layout_metrics,
)


class AfkWorkday001ResponsiveTests(unittest.TestCase):
    def test_center_window_clamps_to_laptop_viewports(self) -> None:
        for width, height in ((1920, 1080), (1366, 768), (1280, 720)):
            with self.subTest(viewport=(width, height)):
                actual_width, actual_height = clamped_window_size(1380, 820, width, height)
                self.assertLessEqual(actual_width, width - 80)
                self.assertLessEqual(actual_height, height - 80)

    def test_modal_dimensions_keep_minimums_inside_viewport(self) -> None:
        for width, height in ((1366, 768), (1280, 720)):
            with self.subTest(viewport=(width, height)):
                actual_width, actual_height, min_width, min_height = modal_dimensions_for_viewport(
                    width,
                    height,
                    1200,
                    840,
                    min_width=960,
                    min_height=600,
                )
                self.assertLessEqual(actual_width, width - 80)
                self.assertLessEqual(actual_height, height - 80)
                self.assertLessEqual(min_width, actual_width)
                self.assertLessEqual(min_height, actual_height)

    def test_shared_filter_bar_wraps_at_laptop_widths(self) -> None:
        compact = catalog_filter_bar_layout(620)
        medium = catalog_filter_bar_layout(900)
        wide = catalog_filter_bar_layout(1200)

        self.assertEqual(compact.filter_columns, 2)
        self.assertEqual(compact.search_row, 2)
        self.assertEqual(compact.button_row, 3)
        self.assertEqual(medium.filter_columns, 4)
        self.assertEqual(medium.search_row, 1)
        self.assertEqual(wide.search_row, 0)
        self.assertEqual(wide.button_column, 5)

    def test_shell_metrics_reduce_fixed_width_on_small_laptops(self) -> None:
        small = shell_layout_metrics(1280)
        large = shell_layout_metrics(1920)

        self.assertLess(small.sidebar_width, large.sidebar_width)
        self.assertLess(small.content_pad_x, large.content_pad_x)
        self.assertLessEqual(small.sidebar_width + (small.content_pad_x * 2), 260)

    def test_price_selection_actions_are_wrapped_below_adjustment_controls(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)

        self.assertIn("adjustment_row = tk.Frame(footer", source)
        self.assertIn("pagination_row = tk.Frame(footer", source)
        self.assertIn("action_row = tk.Frame(footer", source)
        self.assertIn('add_button = self._button(action_row, "Anadir seleccionados"', source)
        self.assertIn('preview_button = self._button(\n            action_row,', source)

    def test_main_window_minimum_supports_1280x720_stress_viewport(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype.__init__)

        self.assertIn("center_window(self, 1280, 760)", source)
        self.assertIn("self.minsize(1000, 620)", source)


class AfkWorkday001DistributionTests(unittest.TestCase):
    def test_runtime_source_has_no_local_development_file_dependency(self) -> None:
        forbidden = re.compile(
            r"auditoria[/\\]out|C:[/\\]{1,2}Users|_Checkpoint|\\.codex|Codex_Handoff",
            re.IGNORECASE,
        )
        for path in sorted((ROOT / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(forbidden.search(text))

    def test_distributed_runtime_smoke_without_auditoria_imports_main_views(self) -> None:
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
                import futonhub.ui.erp.formula_library
                import futonhub.ui.erp.inventory_detail
                import futonhub.ui.erp.inventory_list
                import futonhub.ui.erp.prototype
                from futonhub.services.catalog_operational_baseline import CatalogOperationalBaseline
                from futonhub.services.combination_price_impact import CombinationPriceImpactService
                from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot
                from futonhub.ui.erp.prototype import FutonHubErpPrototype


                snapshot = PhysicalCatalogSnapshot.load()
                baseline = CatalogOperationalBaseline()
                service = CombinationPriceImpactService()
                live_rows = [dict(row) for row in snapshot.rows_by_item_id.values()]
                enriched_rows = baseline.enrich_rows(snapshot.eligible_live_rows(live_rows))
                impact = service.impact_for_changes([{
                    "physical_item_id": "201002",
                    "physical_sku": "0201002",
                    "old_price": "10.00",
                    "new_price": "11.00",
                }])
                required_views = [
                    "_build_dashboard",
                    "_build_inventory",
                    "_open_inventory_detail_window",
                    "_build_prices",
                    "_build_price_edit_workspace",
                    "_build_order_calc",
                    "_build_woocommerce",
                    "_build_supplier_prices",
                    "_build_formula_library",
                ]
                assert not (__import__("pathlib").Path.cwd() / "auditoria").exists()
                assert all(hasattr(FutonHubErpPrototype, view) for view in required_views)
                assert len(snapshot.item_ids) == 254
                assert len(enriched_rows) == 254
                assert len(baseline.operational_by_item_id) == 188
                assert len(baseline.quarantine_by_item_id) == 66
                assert impact["counts"]["included_combinations"] == 19
                print(json.dumps({
                    "DISTRIBUTED_RUNTIME_SMOKE": "PASS",
                    "DASHBOARD": "PASS",
                    "INVENTORY": "PASS",
                    "PRICE_CHANGE": "PASS",
                    "FORMULA_LIBRARY": "PASS",
                    "PHYSICAL_ROWS": len(snapshot.item_ids),
                    "OPERATIONAL": len(baseline.operational_by_item_id),
                    "QUARANTINED": len(baseline.quarantine_by_item_id),
                    "COMBINATION_IMPACT_RUNTIME": "PASS",
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
                    "DASHBOARD": "PASS",
                    "DISTRIBUTED_RUNTIME_SMOKE": "PASS",
                    "FORMULA_LIBRARY": "PASS",
                    "INVENTORY": "PASS",
                    "OPERATIONAL": 188,
                    "PHYSICAL_ROWS": 254,
                    "PRICE_CHANGE": "PASS",
                    "QUARANTINED": 66,
                },
            )


if __name__ == "__main__":
    unittest.main()

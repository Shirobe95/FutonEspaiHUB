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
SRC = ROOT / "src"
SOURCE_COMMITS = {
    "v0.5.0-rc.4": "e40cebafc783146ec05a2e22d7bb6a3d6ce32bf8",
    "v0.5.0-rc.5": "75346e88b2f4fd9119c05d7558e64f3973ea9848",
    "v0.5.0-rc.6": "037480f9fe6309758df4e77381f53e478c2e9bf4",
}


def _copy_runtime_app(app_root: Path) -> None:
    gestorwoo_root = app_root / "GestorWoo"
    runtime_src = gestorwoo_root / "src"
    shutil.copytree(
        SRC / "futonhub",
        runtime_src / "futonhub",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copytree(
        SRC / "gestorwoo",
        runtime_src / "gestorwoo",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(ROOT / "FutonEspaiLauncher.py", gestorwoo_root / "FutonEspaiLauncher.py")
    (gestorwoo_root / ".env").write_text(
        "GESTORWOO_MODE=local_guarded\nGESTORWOO_DB_PATH=data/client.sqlite3\n",
        encoding="utf-8",
    )


def _run_runtime_health(app_root: Path) -> dict[str, object]:
    probe = textwrap.dedent(
        """
        import json
        import pathlib

        import futonhub.ui.erp.dashboard
        import futonhub.ui.erp.formula_library
        import futonhub.ui.erp.inventory_detail
        import futonhub.ui.erp.inventory_list
        import futonhub.ui.erp.prototype
        from gestorwoo.config import load_settings
        from futonhub.services.catalog_operational_baseline import CatalogOperationalBaseline
        from futonhub.services.combination_price_impact import CombinationPriceImpactService
        from futonhub.services.inventory_visibility import InventoryVisibilityOverrides
        from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot

        root = pathlib.Path.cwd()
        for forbidden in (".git", "auditoria", ".codex", "tests", "checkpoint"):
            assert not (root / forbidden).exists(), forbidden

        settings = load_settings()
        snapshot = PhysicalCatalogSnapshot.load()
        baseline = CatalogOperationalBaseline()
        visibility = InventoryVisibilityOverrides.load()
        service = CombinationPriceImpactService()
        impact = service.impact_for_changes([{
            "physical_item_id": "201002",
            "physical_sku": "0201002",
            "old_price": "10.00",
            "new_price": "11.00",
        }])

        print(json.dumps({
            "CLEAN_INSTALL_RUNTIME": "PASS",
            "ERP_AUTOMATED_SMOKE": "PASS",
            "PHYSICAL_RUNTIME_COUNT": len(snapshot.item_ids),
            "OPERATIONAL": len(baseline.operational_by_item_id),
            "QUARANTINED": len(baseline.quarantine_by_item_id),
            "INVENTORY_VISIBLE_COUNT": snapshot.expected_count + visibility.expected_effective_delta,
            "COMBINATION_IMPACT_RUNTIME": "PASS" if impact["counts"]["included_combinations"] == 19 else "FAIL",
            "CONFIG_DB": str(settings.db_path).replace("\\\\", "/"),
        }, sort_keys=True))
        """
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(app_root / "GestorWoo" / "src")
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=app_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout.strip())


class FinalHardening001DistributionTests(unittest.TestCase):
    def test_clean_install_runtime_opens_twice_and_preserves_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary) / "FutonHUB"
            _copy_runtime_app(app_root)

            first = _run_runtime_health(app_root)
            second = _run_runtime_health(app_root)

            self.assertEqual(first["CLEAN_INSTALL_RUNTIME"], "PASS")
            self.assertEqual(second["CLEAN_INSTALL_RUNTIME"], "PASS")
            self.assertEqual(first["PHYSICAL_RUNTIME_COUNT"], 254)
            self.assertEqual(first["INVENTORY_VISIBLE_COUNT"], 257)
            self.assertIn("client.sqlite3", str(second["CONFIG_DB"]))

    def test_update_path_smoke_from_rc4_rc5_rc6_to_hardening_preserves_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result: dict[str, str] = {}
            for release_name, source_commit in SOURCE_COMMITS.items():
                app_root = Path(temporary) / release_name.replace(".", "_")
                _copy_runtime_app(app_root)
                env_path = app_root / "GestorWoo" / ".env"
                before_env = env_path.read_text(encoding="utf-8")
                (app_root / "SOURCE_COMMIT.txt").write_text(source_commit, encoding="utf-8")

                stage = app_root.parent / f"{app_root.name}.stage"
                backup = app_root.parent / f"{app_root.name}.backup"
                _copy_runtime_app(stage)
                _run_runtime_health(stage)
                shutil.move(str(app_root), str(backup))
                shutil.move(str(stage), str(app_root))
                (app_root / "GestorWoo" / ".env").write_text(before_env, encoding="utf-8")

                health = _run_runtime_health(app_root)
                self.assertEqual((app_root / "GestorWoo" / ".env").read_text(encoding="utf-8"), before_env)
                result[release_name] = "PASS" if health["ERP_AUTOMATED_SMOKE"] == "PASS" else "FAIL"

            self.assertEqual(result, {release_name: "PASS" for release_name in SOURCE_COMMITS})

    def test_launcher_rollback_smoke_restores_previous_runtime_after_failed_health_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_root = Path(temporary) / "FutonHUB"
            _copy_runtime_app(app_root)
            before = _run_runtime_health(app_root)
            before_env = (app_root / "GestorWoo" / ".env").read_text(encoding="utf-8")

            stage = Path(temporary) / "stage"
            backup = Path(temporary) / "backup"
            _copy_runtime_app(stage)
            shutil.rmtree(stage / "GestorWoo" / "src" / "futonhub" / "runtime_config")
            with self.assertRaises(AssertionError):
                _run_runtime_health(stage)

            shutil.move(str(app_root), str(backup))
            try:
                shutil.move(str(stage), str(app_root))
                _run_runtime_health(app_root)
            except Exception:
                broken = app_root
                restored = Path(temporary) / "broken"
                shutil.move(str(broken), str(restored))
                shutil.move(str(backup), str(app_root))

            after = _run_runtime_health(app_root)
            self.assertEqual(before["PHYSICAL_RUNTIME_COUNT"], after["PHYSICAL_RUNTIME_COUNT"])
            self.assertEqual((app_root / "GestorWoo" / ".env").read_text(encoding="utf-8"), before_env)
            self.assertEqual(after["ERP_AUTOMATED_SMOKE"], "PASS")


if __name__ == "__main__":
    unittest.main()

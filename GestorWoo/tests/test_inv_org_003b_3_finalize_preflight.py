from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def load_finalizer():
    spec = importlib.util.spec_from_file_location("inv_org_003b_3_finalize_preflight", REPOSITORY_ROOT / "auditoria" / "inv_org_003b_3_finalize.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InvOrg003B3FinalizePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.finalizer = load_finalizer()

    def test_only_approved_leading_zero_equivalence_is_normalized(self) -> None:
        self.assertEqual(self.finalizer.comparison_code("302018"), "302018")
        self.assertEqual(self.finalizer.comparison_code("0302018"), "302018")
        self.assertEqual(self.finalizer.comparison_code("0758001"), "0758001")
        self.assertEqual(self.finalizer.comparison_code("000123"), "000123")

    def test_contractual_group_counts_use_only_eligible_item_ids(self) -> None:
        live = {
            "eligible-1": {"filter_group": "Algodón Lana"},
            "eligible-2": {"filter_group": "Algodón Lana"},
            "excluded": {"filter_group": "Algodón + Lana"},
        }
        counts = self.finalizer.eligible_group_counts(live, {"eligible-1", "eligible-2"})
        self.assertEqual(counts["Algodón Lana"], 2)
        self.assertEqual(counts["Algodón + Lana"], 0)

    def test_null_empty_and_missing_remain_distinct_for_diagnostics(self) -> None:
        self.assertEqual(self.finalizer.value_state({"field": None}, "field"), "NULL")
        self.assertEqual(self.finalizer.value_state({"field": ""}, "field"), "EMPTY")
        self.assertEqual(self.finalizer.value_state({}, "field"), "MISSING")
        self.assertEqual(self.finalizer.value_state({"field": "value"}, "field"), "VALUE")

    def test_zip_member_names_are_relative_and_stable_for_all_required_roots(self) -> None:
        expected = {
            REPOSITORY_ROOT / "auditoria" / "out" / "physical_catalog_snapshot_manifest.json": "auditoria/out/physical_catalog_snapshot_manifest.json",
            REPOSITORY_ROOT / "auditoria" / "inv_org_003b_3_finalize.py": "auditoria/inv_org_003b_3_finalize.py",
            REPOSITORY_ROOT / "GestorWoo" / "tests" / "test_inv_org_003b_3_finalization.py": "GestorWoo/tests/test_inv_org_003b_3_finalization.py",
        }
        for source, member in expected.items():
            self.assertEqual(self.finalizer.archive_member_name(source), member)
            self.assertFalse(Path(member).is_absolute())
            self.assertNotIn("..", Path(member).parts)


if __name__ == "__main__":
    unittest.main()

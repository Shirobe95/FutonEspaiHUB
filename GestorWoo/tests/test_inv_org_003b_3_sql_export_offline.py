from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def load_finalizer():
    spec = importlib.util.spec_from_file_location("inv_org_003b_3_finalize_sql_export", REPOSITORY_ROOT / "auditoria" / "inv_org_003b_3_finalize.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class InvOrg003B3SqlExportOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.finalizer = load_finalizer()

    def write_export(self, path: Path, *, timestamps: tuple[str, ...] = ("2026-08-03 10:27:26.171696",), code: str = "0758001") -> None:
        fields = list(self.finalizer.EXPORT_REQUIRED_COLUMNS)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for index in range(716):
                timestamp = timestamps[index % len(timestamps)]
                writer.writerow({
                    "export_generated_at_utc": timestamp, "item_id": str(index + 1), "heca_reference": code if index == 0 else f"0{index + 1:06d}",
                    "hub_item_code": f"0{index + 1:06d}", "base_item_code": "null", "item_record_type": "simple", "is_pack": "false",
                    **{field: "null" for field in self.finalizer.LIVE_FIELD_NAMES if field not in {"item_id", "heca_reference", "hub_item_code", "base_item_code", "item_record_type", "is_pack"}},
                })

    def test_export_parser_accepts_exact_716_rows_and_preserves_null_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "live.csv"
            self.write_export(path)
            rows, metadata = self.finalizer.read_live_export(path)
        self.assertEqual(len(rows), 716)
        self.assertIsNone(rows[0]["base_item_code"])
        self.assertEqual(metadata["source"], "SUPABASE_SQL_EDITOR_MANUAL_EXPORT")
        self.assertGreater(metadata["null_state_counts"]["NULL"], 0)

    def test_export_parser_rejects_non_uniform_timestamp_and_scientific_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            non_uniform = root / "non_uniform.csv"
            self.write_export(non_uniform, timestamps=("2026-08-03 10:27:26.171696", "2026-08-03 10:27:27.171696"))
            with self.assertRaises(self.finalizer.FinalizationAbort):
                self.finalizer.read_live_export(non_uniform)
            scientific = root / "scientific.csv"
            self.write_export(scientific, code="7.58001E+05")
            with self.assertRaises(self.finalizer.FinalizationAbort):
                self.finalizer.read_live_export(scientific)


if __name__ == "__main__":
    unittest.main()

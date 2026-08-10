from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
OUT = REPOSITORY_ROOT / "auditoria" / "out"
FINAL = OUT / "inv_org_003b_3"
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import CatalogFilterConfigurationError, PhysicalCatalogSnapshot  # noqa: E402


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_finalizer():
    spec = importlib.util.spec_from_file_location("inv_org_003b_3_finalize", REPOSITORY_ROOT / "auditoria" / "inv_org_003b_3_finalize.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class InvOrg003B3FinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot_path = FINAL / "dat_catalog_003b_ui_eligible_254.csv"
        cls.exclusions_path = FINAL / "dat_catalog_003b_ui_exclusions_462.csv"
        cls.manifest_path = OUT / "physical_catalog_snapshot_manifest.json"
        cls.snapshot = read_csv(cls.snapshot_path)
        cls.exclusions = read_csv(cls.exclusions_path)
        cls.rows = {row["item_id"]: row for row in cls.snapshot}
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))
        cls.finalizer = load_finalizer()

    def test_resnapshot_reconciles_and_checksum_is_reproducible(self) -> None:
        self.assertEqual(self.manifest["cut"], "INV-ORG-003B.3")
        self.assertEqual(len(self.snapshot), 254)
        self.assertEqual(len(self.exclusions), 462)
        self.assertEqual(len(self.snapshot) + len(self.exclusions), 716)
        self.assertEqual(len(self.rows), 254)
        self.assertFalse(set(self.rows) & {row["item_id"] for row in self.exclusions})
        self.assertEqual(hashlib.sha256(self.snapshot_path.read_bytes()).hexdigest(), self.manifest["snapshot_sha256"])
        self.assertNotEqual(self.manifest["snapshot_sha256"], self.manifest["previous_snapshot_sha256"])

    def test_post_apply_normalizations_are_frozen_in_snapshot(self) -> None:
        premium = {"758001": "90x200x17", "758087": "120x200x17", "758002": "140x200x17", "758003": "150x200x17", "758004": "160x200x17", "758005": "180x200x17", "758006": "200x200x17"}
        self.assertEqual(len(premium), 7)
        for item_id, size in premium.items():
            row = self.rows[item_id]
            self.assertEqual((row["family"], row["filter_family"], row["filter_group"], row["filter_size"], row["filter_gama"]), ("Futones", "Futones", "Premium", size, "Invierno/Verano"))
        self.assertEqual(sum(row["filter_group"] == "Algodón Lana" for row in self.snapshot), 7)
        self.assertFalse(any(row["filter_group"] in {"Algodón + Lana", "Algodon Lana", "Algodon + Lana"} for row in self.snapshot))
        for item_id, size in (("770002", "120x200x14"), ("770008", "200x200x14")):
            row = self.rows[item_id]
            self.assertEqual((row["size"], row["filter_size"], row["filter_group"]), (size, size, "Algodón Lana"))
            self.assertEqual(row["dimensions_notes"].count("size_original_pre_INV-ORG-003B.3="), 1)
        self.assertEqual(self.rows["780006"]["name"], "Futón Lana 180x200x14 cm")
        self.assertNotIn("1800x200x14", self.rows["780006"]["name"])

    def test_loader_and_finalizer_fail_closed_for_missing_or_corrupt_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot.csv"
            exclusions = root / "exclusions.csv"
            manifest = root / "manifest.json"
            snapshot.write_bytes(self.snapshot_path.read_bytes())
            exclusions.write_bytes(self.exclusions_path.read_bytes())
            payload = dict(self.manifest)
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(self.finalizer.verify_manifest_snapshot(manifest, snapshot, exclusions)["rows"], 254)
            payload["snapshot_sha256"] = "0" * 64
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(self.finalizer.FinalizationAbort):
                self.finalizer.verify_manifest_snapshot(manifest, snapshot, exclusions)
            with self.assertRaises(self.finalizer.FinalizationAbort):
                self.finalizer.verify_manifest_snapshot(root / "missing.json", snapshot, exclusions)
            with self.assertRaises(CatalogFilterConfigurationError):
                with patch("futonhub.ui.erp.catalog_filters.physical_catalog_snapshot_manifest_path", return_value=root / "missing.json"):
                    PhysicalCatalogSnapshot.load()


if __name__ == "__main__":
    unittest.main()

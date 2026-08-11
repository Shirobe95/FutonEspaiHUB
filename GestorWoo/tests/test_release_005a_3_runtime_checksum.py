from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterConfigurationError,
    PhysicalCatalogSnapshot,
    canonical_text_sha256,
)


RUNTIME_CONFIG = ROOT / "src" / "futonhub" / "runtime_config"
SNAPSHOT_PATH = RUNTIME_CONFIG / "physical_catalog_snapshot.csv"
MANIFEST_PATH = RUNTIME_CONFIG / "physical_catalog_snapshot_manifest.json"


class Release005A3RuntimeChecksumTests(unittest.TestCase):
    def _load_with_bytes(self, snapshot_bytes: bytes, *, manifest_sha256: str | None = None, checksum_mode: str = "utf8_text_lf_v1") -> PhysicalCatalogSnapshot:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["checksum_mode"] = checksum_mode
        manifest["snapshot_sha256"] = manifest_sha256 or canonical_text_sha256(
            snapshot_bytes,
            "utf8_text_lf_v1",
        )

        with tempfile.TemporaryDirectory() as directory:
            runtime_config = Path(directory)
            snapshot_path = runtime_config / "physical_catalog_snapshot.csv"
            temporary_manifest = runtime_config / "physical_catalog_snapshot_manifest.json"
            snapshot_path.write_bytes(snapshot_bytes)
            temporary_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with patch(
                "futonhub.ui.erp.catalog_filters.physical_catalog_snapshot_manifest_path",
                return_value=temporary_manifest,
            ):
                return PhysicalCatalogSnapshot.load()

    def test_lf_snapshot_matches_canonical_checksum(self) -> None:
        text = SNAPSHOT_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        snapshot = self._load_with_bytes(text.encode("utf-8"))
        self.assertEqual(len(snapshot.item_ids), 254)

    def test_crlf_snapshot_matches_canonical_checksum(self) -> None:
        text = SNAPSHOT_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        snapshot = self._load_with_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(len(snapshot.item_ids), 254)

    def test_utf8_bom_snapshot_matches_canonical_checksum(self) -> None:
        text = SNAPSHOT_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        snapshot = self._load_with_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        self.assertEqual(len(snapshot.item_ids), 254)

    def test_real_cell_change_fails_closed(self) -> None:
        original = SNAPSHOT_PATH.read_bytes()
        changed = original.replace(b"PHYSICAL_UI_ELIGIBLE", b"PHYSICAL_UI_ELIGIBLE_CHANGED", 1)
        self.assertNotEqual(changed, original)
        with self.assertRaises(CatalogFilterConfigurationError):
            self._load_with_bytes(changed, manifest_sha256=canonical_text_sha256(original, "utf8_text_lf_v1"))

    def test_incorrect_manifest_checksum_fails_closed(self) -> None:
        with self.assertRaises(CatalogFilterConfigurationError):
            self._load_with_bytes(SNAPSHOT_PATH.read_bytes(), manifest_sha256="0" * 64)

    def test_invalid_manifest_checksum_mode_fails_closed(self) -> None:
        with self.assertRaises(CatalogFilterConfigurationError):
            self._load_with_bytes(SNAPSHOT_PATH.read_bytes(), checksum_mode="raw_bytes_v0")


if __name__ == "__main__":
    unittest.main()

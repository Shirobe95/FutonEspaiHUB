from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
ARTIFACTS = REPOSITORY_ROOT / "auditoria" / "out"
B2B = ARTIFACTS / "inv_org_003b_2b"
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterConfigurationError,
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    filter_catalog_rows,
)


LOW_CODES = {"0606011", "0607011", "0608011", "0609011", "0615011", "0616011"}
DUO_ITEM_IDS = {"78009", "78012", "78013", "780008", "780009", "780010", "780012", "780013", "780014"}
SOURCE_BACKED_ITEM_IDS = {
    "406006", "607019", "608018", "608019", "616019", "617018", "1002011", "619002", "619004",
    "780001", "780002", "780003", "780004", "780005", "780006", "780007", "903001", "201006",
    "201007", "201014",
}
LIVE_ONLY_ITEM_IDS = {
    "619007", "619009", "619010", "619011", "619013", "619014", "770002", "770008", "78009", "78012",
    "78013", "780008", "780009", "780010", "780012", "780013", "780014", "818001", "818002", "758087",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class InvOrg003B2BPhysicalPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = PhysicalCatalogSnapshot.load()
        cls.snapshot_rows = list(cls.snapshot.rows_by_item_id.values())
        cls.rows_by_id = cls.snapshot.rows_by_item_id
        cls.rows_by_code = {
            row["hub_item_code"]: row
            for row in cls.snapshot_rows
            if row.get("hub_item_code")
        }
        cls.precheck = read_csv(B2B / "INV_ORG_003B_2B_PROMOTION_PRECHECK.csv")
        cls.exclusions = read_csv(B2B / "dat_catalog_003b_ui_exclusions_462.csv")
        cls.duo_matrix = read_csv(B2B / "INV_ORG_003B_2B_DUO_LATEX_IDENTITY_MATRIX.csv")
        cls.pre_woo = read_csv(B2B / "dat_catalog_003b_pre_woo_readiness_final.csv")
        cls.manifest = json.loads((ARTIFACTS / "physical_catalog_snapshot_manifest.json").read_text(encoding="utf-8"))

    def test_current_snapshot_reconciles_all_716_records(self) -> None:
        self.assertEqual(self.snapshot.expected_count, 254)
        self.assertEqual(len(self.snapshot_rows), 254)
        self.assertEqual(len(self.exclusions), 462)
        self.assertEqual(len(self.snapshot_rows) + len(self.exclusions), 716)
        self.assertEqual(len({row["item_id"] for row in self.snapshot_rows}), 254)
        self.assertEqual(len({row["item_id"] for row in self.exclusions}), 462)
        self.assertFalse({row["item_id"] for row in self.snapshot_rows} & {row["item_id"] for row in self.exclusions})

    def test_all_40_approved_promotions_are_eligible_and_removed_from_exclusions(self) -> None:
        self.assertEqual(len(self.precheck), 40)
        self.assertEqual({row["precheck_result"] for row in self.precheck}, {"YES_SAFE_PROMOTE"})
        promoted_ids = {row["item_id"] for row in self.precheck}
        self.assertEqual(len(promoted_ids), 40)
        self.assertTrue(promoted_ids <= set(self.rows_by_id))
        self.assertFalse(promoted_ids & {row["item_id"] for row in self.exclusions})

    def test_source_backed_and_live_only_inputs_are_exactly_twenty_each(self) -> None:
        source_rows = [row for row in self.precheck if row["source_group"] == "SOURCE_BACKED"]
        live_rows = [row for row in self.precheck if row["source_group"] == "LIVE_ONLY"]
        self.assertEqual(len(source_rows), 20)
        self.assertEqual(len(live_rows), 20)
        self.assertEqual({row["item_id"] for row in source_rows}, SOURCE_BACKED_ITEM_IDS)
        self.assertEqual({row["item_id"] for row in live_rows}, LIVE_ONLY_ITEM_IDS)
        self.assertEqual({row["physical_validation_source"] for row in source_rows}, {"MAESTRO"})
        self.assertEqual({row["physical_validation_source"] for row in live_rows}, {"USER_CONFIRMED"})

    def test_duo_latex_keeps_nine_distinct_human_approved_identities(self) -> None:
        self.assertEqual(len(self.duo_matrix), 9)
        self.assertEqual({row["item_id"] for row in self.duo_matrix}, DUO_ITEM_IDS)
        self.assertEqual({row["identidad_propia_confirmada"] for row in self.duo_matrix}, {"YES"})
        self.assertTrue(DUO_ITEM_IDS <= set(self.rows_by_id))
        for item_id in DUO_ITEM_IDS:
            row = self.rows_by_id[item_id]
            self.assertEqual(row["filter_family"], "Futones")
            self.assertEqual(row["filter_group"], "Dúo Látex")
            self.assertEqual(row["filter_gama"], "NO_GAMA")

    def test_fundas_and_cotton_lana_use_single_approved_filter_groups(self) -> None:
        promoted = {row["item_id"] for row in self.precheck}
        promoted_rows = [self.rows_by_id[item_id] for item_id in promoted]
        funda_rows = [row for row in promoted_rows if row["filter_family"] == "Fundas"]
        self.assertEqual({row["filter_group"] for row in funda_rows}, {"Funda Almohada", "Funda Futón"})
        self.assertNotIn("Funda Sofá", {row["filter_group"] for row in promoted_rows})
        cotton_lana = [row for row in promoted_rows if row["filter_group"] == "Algodón Lana"]
        self.assertEqual({row["item_id"] for row in cotton_lana}, {"770002", "770008"})

    def test_promoted_snapshot_rows_remain_physical_and_nonblocked(self) -> None:
        snapshot_codes = {
            row.get("heca_reference") or row.get("hub_item_code") or row.get("base_item_code")
            for row in self.snapshot_rows
        }
        self.assertFalse(LOW_CODES & snapshot_codes)
        for row in self.snapshot_rows:
            self.assertEqual(row["item_record_type"].casefold(), "simple")
            self.assertEqual(row["is_pack"].casefold(), "false")
            self.assertNotEqual(row["physical_validation_source"].casefold(), "")
            self.assertTrue(all(row[field] for field in ("filter_family", "filter_group", "filter_size", "filter_gama")))

    def test_pre_woo_mapping_has_one_ready_row_per_eligible_item(self) -> None:
        self.assertEqual(len(self.pre_woo), 254)
        self.assertEqual({row["ready_for_woo_mapping"] for row in self.pre_woo}, {"READY_FOR_WOO_MAPPING"})
        self.assertEqual({row["canonical_item_id"] for row in self.pre_woo}, set(self.rows_by_id))
        duo_rows = [row for row in self.pre_woo if row["canonical_item_id"] in DUO_ITEM_IDS]
        self.assertEqual(len(duo_rows), 9)

    def test_cascade_filters_include_new_groups_without_approximate_identity_matching(self) -> None:
        promoted_rows = [self.rows_by_id[row["item_id"]] for row in self.precheck]
        duo_rows = filter_catalog_rows(
            promoted_rows,
            CatalogFilterSelection(filter_family="Futones", filter_group="Dúo Látex"),
        )
        self.assertEqual({row["item_id"] for row in duo_rows}, DUO_ITEM_IDS)
        portable_rows = filter_catalog_rows(
            promoted_rows,
            CatalogFilterSelection(filter_family="Futones", filter_group="Portátil"),
        )
        self.assertEqual({row["item_id"] for row in portable_rows}, {"818001", "818002"})

    def test_manifest_checksum_matches_the_current_254_snapshot(self) -> None:
        self.assertEqual(self.manifest["cut"], "INV-ORG-003B.3")
        self.assertEqual(self.manifest["expected_count"], 254)
        source = ARTIFACTS / self.manifest["snapshot_relative_path"]
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), self.manifest["snapshot_sha256"])

    def test_manifest_checksum_mismatch_fails_closed(self) -> None:
        source = ARTIFACTS / self.manifest["snapshot_relative_path"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "snapshot.csv").write_bytes(source.read_bytes())
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({
                    "snapshot_relative_path": "snapshot.csv",
                    "expected_count": 254,
                    "snapshot_sha256": "0" * 64,
                    "approved_leading_zero_comparison_keys": ["302018"],
                }),
                encoding="utf-8",
            )
            with patch(
                "futonhub.ui.erp.catalog_filters.physical_catalog_snapshot_manifest_path",
                return_value=manifest,
            ):
                with self.assertRaises(CatalogFilterConfigurationError):
                    PhysicalCatalogSnapshot.load()


if __name__ == "__main__":
    unittest.main()

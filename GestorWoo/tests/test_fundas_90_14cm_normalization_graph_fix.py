from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_catalog_reconciliation import price_proposal_selectable_catalogue_rows  # noqa: E402
from futonhub.services.price_proposal_live_context import _graph_coverage_for_changes  # noqa: E402
from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot  # noqa: E402


AFFECTED_FUNDAS = {
    "0619014": ("619014", "Beige jaspeado", "14030"),
    "0619013": ("619013", "Gris jaspeado", "14029"),
    "0619008": ("619011", "Marrón Chocolate", "11115"),
}

WORKING_90X200X14_FUNDAS = {
    "0608001": ("608001", "Crudo", "3767"),
    "0616001": ("616001", "NO_GAMA", "3798"),
}

HISTORICAL_90X200X14_FUNDAS = {
    "0609001": ("609001", "Azul", "3779"),
    "0606001": ("606001", "Granate", "3755"),
    "0615001": ("615001", "NO_GAMA", "3791"),
    "0607001": ("607001", "Rojo", "3761"),
    "0614001": ("614001", "Verde", ""),
}


def _live_price_row(snapshot: PhysicalCatalogSnapshot, sku: str, *, normal: bool) -> dict[str, object]:
    item_id, _gama, woo_id = {
        **AFFECTED_FUNDAS,
        **WORKING_90X200X14_FUNDAS,
        **HISTORICAL_90X200X14_FUNDAS,
    }[sku]
    row = dict(snapshot.rows_by_item_id[item_id])
    row.update(
        {
            "item_id": item_id,
            "physical_item_id": item_id,
            "physical_sku": sku,
            "commercial_status": "Normal" if normal else "Descatalogado",
            "item_record_type": "simple",
            "is_pack": False,
            "woo_item_kind": "variation" if woo_id else "",
            "woo_id": woo_id,
            "woo_parent_id": "3631" if woo_id else "",
            "woo_sku": sku if woo_id else "",
            "woo_link_status": "Enlazado" if woo_id else "Sin Woo",
            "price_operable": True if normal else False,
            "sale_item": "YES" if normal else "NO",
        }
    )
    return row


class Fundas90x200x14NormalizationGraphFixTests(unittest.TestCase):
    def test_affected_fundas_are_grouped_under_canonical_14cm_filter_size(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()

        for sku, (item_id, _gama, _woo_id) in AFFECTED_FUNDAS.items():
            with self.subTest(sku=sku):
                row = snapshot.rows_by_item_id[item_id]
                self.assertEqual(row["hub_item_code"], sku)
                self.assertEqual(row["filter_family"], "Fundas")
                self.assertEqual(row["filter_group"], "Funda Futón")
                self.assertEqual(row["filter_size"], "90x200x14")

    def test_operational_funda_selector_has_five_current_90x200x14_rows(self) -> None:
        snapshot = PhysicalCatalogSnapshot.load()
        rows = [
            *(_live_price_row(snapshot, sku, normal=True) for sku in WORKING_90X200X14_FUNDAS),
            *(_live_price_row(snapshot, sku, normal=True) for sku in AFFECTED_FUNDAS),
            *(_live_price_row(snapshot, sku, normal=False) for sku in HISTORICAL_90X200X14_FUNDAS),
        ]

        selectable = [
            row
            for row in price_proposal_selectable_catalogue_rows(rows)
            if row["filter_family"] == "Fundas"
            and row["filter_group"] == "Funda Futón"
            and row["filter_size"] in {"90x200x14", "90x200x14,5", "90x200x14.5"}
        ]

        self.assertEqual([row["hub_item_code"] for row in selectable], [
            "0608001",
            "0616001",
            "0619014",
            "0619013",
            "0619008",
        ])
        self.assertEqual(sum(1 for row in selectable if row["filter_size"] == "90x200x14"), 5)
        self.assertEqual(sum(1 for row in selectable if row["filter_size"] in {"90x200x14,5", "90x200x14.5"}), 0)

    def test_direct_only_affected_fundas_are_known_graph_identities_without_edges(self) -> None:
        service = CombinationPriceImpactService()

        for sku, (item_id, _gama, _woo_id) in AFFECTED_FUNDAS.items():
            with self.subTest(sku=sku):
                change = {
                    "physical_item_id": item_id,
                    "physical_sku": sku,
                    "old_price": "10.00",
                    "new_price": "11.00",
                }
                expected = service.affected_destinations_for_identity(change)
                impact = service.impact_for_changes([change])
                coverage = _graph_coverage_for_changes(service, [change], impact)[0]

                self.assertEqual(expected["resolution_status"], "RESOLVED_EXACT")
                self.assertEqual(expected["status"], "NO_COMBINATIONS_BY_DESIGN")
                self.assertEqual(expected["expected_count"], 0)
                self.assertEqual(impact["included_combinations"], [])
                self.assertEqual(coverage["status"], "NO_COMBINATIONS_BY_DESIGN")
                self.assertNotEqual(coverage["status"], "BLOCKED_GRAPH_COVERAGE")

    def test_existing_14cm_graph_fundas_still_return_their_expected_combinations(self) -> None:
        service = CombinationPriceImpactService()

        for sku, (item_id, _gama, _woo_id) in WORKING_90X200X14_FUNDAS.items():
            with self.subTest(sku=sku):
                change = {
                    "physical_item_id": item_id,
                    "physical_sku": sku,
                    "old_price": "10.00",
                    "new_price": "11.00",
                }
                expected = service.affected_destinations_for_identity(change)
                impact = service.impact_for_changes([change])

                self.assertEqual(expected["resolution_status"], "RESOLVED_EXACT")
                self.assertEqual(expected["status"], "HAS_AFFECTED")
                self.assertEqual(expected["expected_count"], 3)
                self.assertEqual(len(impact["included_combinations"]), 3)


if __name__ == "__main__":
    unittest.main()

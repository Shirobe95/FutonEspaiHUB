from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402
from futonhub.ui.erp.shared_ui import ProposalLine  # noqa: E402


def inventory_item(code: str, name: str, price: str = "20.00", raw: dict | None = None) -> InventoryItem:
    return InventoryItem(
        code=code,
        name=name,
        price=price,
        stock="-",
        status="Info",
        family="-",
        provider="-",
        m3="-",
        sku_woo="-",
        measures="-",
        material="-",
        sync_woo="-",
        notes="-",
        raw=raw or {},
    )


class PriceProposalPackCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = object.__new__(FutonHubErpPrototype)

    def test_normal_item_keeps_current_name(self) -> None:
        item = inventory_item("0201001", "Tatami normal")

        self.assertEqual(self.app._price_display_name_for_inventory_item(item), "Tatami normal")

    def test_pack_with_components_shows_readable_multiline_composition(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components": [
                    {"component_item_code": "0728003", "component_name": "Futon", "quantity": 1},
                    {"component_item_code": "0201001", "component_name": "Tatami", "quantity": 2},
                ],
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "2 × 0201001 · Tatami\n1 × 0728003 · Futon",
        )

    def test_repeated_components_are_grouped_and_sorted_by_component_code(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components": [
                    {"component_item_code": "0728003", "component_name": "Futon", "quantity": 1},
                    {"component_item_code": "0201001", "component_name": "Tatami", "quantity": 2},
                    {"component_item_code": "0201001", "component_name": "Tatami", "quantity": 3},
                ],
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "5 × 0201001 · Tatami\n1 × 0728003 · Futon",
        )

    def test_integer_and_decimal_quantities_do_not_show_unnecessary_decimals(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components": [
                    {"component_item_code": "0201001", "component_name": "Tatami", "quantity": "1.50"},
                    {"component_item_code": "0728003", "component_name": "Futon", "quantity": "2.00"},
                ],
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "1.5 × 0201001 · Tatami\n2 × 0728003 · Futon",
        )

    def test_component_without_name_omits_separator_and_name(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components": [
                    {"component_item_code": "0201001", "component_name": "", "quantity": 2},
                ],
            },
        )

        self.assertEqual(self.app._price_display_name_for_inventory_item(item), "2 × 0201001")

    def test_pack_without_composition_uses_technical_name_fallback(self) -> None:
        item = inventory_item("1111191", "PackWoo1111191", raw={"item_record_type": "woo_pack"})

        self.assertEqual(self.app._price_display_name_for_inventory_item(item), "PackWoo1111191")

    def test_cached_text_composition_is_reused_without_queries(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components_multiline": "- 0728003 x1 · Futon\n- 0201001 x2 · Tatami",
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "2 × 0201001 · Tatami\n1 × 0728003 · Futon",
        )

    def test_add_rows_preserves_proposal_line_name_id_and_price(self) -> None:
        self.app._price_edit_lines = []
        self.app._price_line_sources = {"1111191": {"item_kind": "product", "woo_id": 1111191}}
        self.app._price_available_items = []
        self.app._inventory_items = []
        self.app._show_view = lambda _view: None

        name = "2 × 0201001 · Tatami\n1 × 0728003 · Futon"
        self.app._price_add_rows_to_proposal([("1111191", name, "20.00")], "10", "")

        self.assertEqual(
            self.app._price_edit_lines,
            [ProposalLine("1111191", name, "20.00", "22.00", "+2.00 (+10.00%)", "up")],
        )

    def test_cloud_row_reuses_saved_readable_line_name(self) -> None:
        proposal = self.app._price_proposal_from_cloud_row(
            {
                "id": "p-1",
                "item_kind": "product",
                "item_woo_id": 1111191,
                "name": "PackWoo1111191",
                "old_price": 20,
                "new_price": 22,
                "status": "pending",
                "source_row": {
                    "ui_line_name": "2 × 0201001 · Tatami\n1 × 0728003 · Futon",
                    "ui_proposal_name": "Pack test",
                },
            }
        )

        self.assertEqual(proposal.lines[0].code, "product:1111191")
        self.assertEqual(proposal.lines[0].name, "2 × 0201001 · Tatami\n1 × 0728003 · Futon")
        self.assertEqual(proposal.lines[0].new_price, "22.00")


if __name__ == "__main__":
    unittest.main()

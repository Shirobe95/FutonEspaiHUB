from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.inventory import search_cloud_inventory_items  # noqa: E402
from futonhub.cloud.services import inventory  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402
from futonhub.ui.erp.shared_ui import ProposalLine  # noqa: E402


class Response:
    def __init__(self, data=None) -> None:
        self.data = data or []


class Query:
    def __init__(self, table_name: str, data_by_table: dict[str, list[dict]]) -> None:
        self.table_name = table_name
        self.data_by_table = data_by_table
        self.filters: list[tuple[str, object]] = []
        self.in_filters: list[tuple[str, tuple[object, ...]]] = []
        self.ilike_filters: list[tuple[str, str]] = []
        self.data_by_table.setdefault("__calls__", []).append((self.table_name, self.filters, self.in_filters))

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column: str, value: object):
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values):
        self.in_filters.append((column, tuple(values)))
        return self

    def ilike(self, column: str, pattern: str):
        self.ilike_filters.append((column, pattern))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        rows = [dict(row) for row in self.data_by_table.get(self.table_name, [])]
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        for column, pattern in self.ilike_filters:
            needle = pattern.replace("%", "").lower()
            if pattern.startswith("%") and not pattern.endswith("%"):
                rows = [row for row in rows if str(row.get(column) or "").lower().endswith(needle)]
            elif pattern.startswith("%") and pattern.endswith("%"):
                rows = [row for row in rows if needle in str(row.get(column) or "").lower()]
            else:
                rows = [row for row in rows if str(row.get(column) or "").lower().startswith(needle)]
        return Response(rows)


class Client:
    def __init__(self, data_by_table: dict[str, list[dict]]) -> None:
        self.data_by_table = data_by_table

    def table(self, table_name: str) -> Query:
        return Query(table_name, self.data_by_table)


class Session:
    def __init__(self, data_by_table: dict[str, list[dict]]) -> None:
        self.client = Client(data_by_table)


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

    def test_pack_with_components_shows_readable_compact_composition(self) -> None:
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
            "2x0201001xTatami | 1x0728003xFuton",
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
            "5x0201001xTatami | 1x0728003xFuton",
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
            "1.5x0201001xTatami | 2x0728003xFuton",
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

        self.assertEqual(self.app._price_display_name_for_inventory_item(item), "2x0201001")

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
            "2x0201001xTatami | 1x0728003xFuton",
        )

    def test_add_rows_preserves_proposal_line_name_id_and_price(self) -> None:
        self.app._price_edit_lines = []
        self.app._price_line_sources = {"1111191": {"item_kind": "product", "woo_id": 1111191}}
        self.app._price_available_items = []
        self.app._inventory_items = []
        self.app._show_view = lambda _view: None

        name = "2x0201001xTatami | 1x0728003xFuton"
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
                    "ui_line_name": "2x0201001xTatami | 1x0728003xFuton",
                    "ui_proposal_name": "Pack test",
                },
            }
        )

        self.assertEqual(proposal.lines[0].code, "product:1111191")
        self.assertEqual(proposal.lines[0].name, "2x0201001xTatami | 1x0728003xFuton")
        self.assertEqual(proposal.lines[0].new_price, "22.00")

    def test_compact_cached_text_is_reused(self) -> None:
        item = inventory_item(
            "1111191",
            "PackWoo1111191",
            raw={
                "item_record_type": "woo_pack",
                "hub_pack_components_text": "2x0201001xTatami | 1x0728003xFuton",
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "2x0201001xTatami | 1x0728003xFuton",
        )

    def test_component_search_returns_simple_item_and_packs_containing_component(self) -> None:
        session = Session(
            {
                "v_inventory_hub_search_ranked": [
                    {
                        "search_token_norm": "0201001",
                        "result_item_id": 201001,
                        "result_item_code": "0201001",
                        "result_name": "Tatami 80",
                        "result_record_type": "simple",
                        "match_priority": 1,
                    },
                    {
                        "search_token_norm": "0201001",
                        "result_item_id": 1111191,
                        "result_item_code": "WOO-PACK-1111191",
                        "result_name": "PackWoo1111191",
                        "result_record_type": "woo_pack",
                        "related_item_code": "0201001",
                        "related_name": "Tatami 80",
                        "relation_quantity": 2,
                        "match_priority": 2,
                    },
                ],
                "inventory_items": [
                    {"item_id": 201001, "name": "Tatami 80", "item_record_type": "simple", "heca_reference": "0201001"},
                    {"item_id": 728003, "name": "Futon Algodon", "item_record_type": "simple", "heca_reference": "0728003"},
                    {
                        "item_id": 1111191,
                        "name": "PackWoo1111191",
                        "item_record_type": "woo_pack",
                        "hub_item_code": "WOO-PACK-1111191",
                    },
                ],
                "inventory_item_components": [
                    {
                        "parent_item_code": "WOO-PACK-1111191",
                        "component_item_code": "0201001",
                        "component_name": "",
                        "quantity": 2,
                        "relation_type": "component",
                    },
                    {
                        "parent_item_code": "WOO-PACK-1111191",
                        "component_item_code": "0728003",
                        "component_name": "",
                        "quantity": 1,
                        "relation_type": "component",
                    },
                ],
            }
        )

        rows = search_cloud_inventory_items(session, "0201001", limit=10)

        self.assertEqual([row["item_id"] for row in rows], [201001, 1111191])
        self.assertEqual(rows[1]["hub_pack_components"][0]["component_item_code"], "0201001")
        self.assertEqual(rows[1]["hub_pack_components"][0]["component_name"], "Tatami 80")
        self.assertEqual(rows[1]["hub_pack_components"][1]["component_name"], "Futon Algodon")
        self.assertEqual(
            self.app._price_display_name_for_inventory_item(self.app._inventory_item_from_cloud_row(rows[1])),
            "2x0201001xTatami 80 | 1x0728003xFuton Algodon",
        )

    def test_missing_component_names_are_resolved_in_bulk_without_component_searches(self) -> None:
        data = {
            "inventory_items": [
                {"item_id": 201001, "name": "Tatami 80", "heca_reference": "201001"},
                {"item_id": 728003, "name": "Futon Algodon", "heca_reference": "0728003"},
            ]
        }
        session = Session(data)
        components = [
            {"component_item_code": "0201001", "component_name": "", "quantity": 2},
            {"component_item_code": "0728003", "component_name": "", "quantity": 1},
            {"component_item_code": "9999999", "component_name": "", "quantity": 1},
        ]

        enriched = inventory._fill_component_names_from_inventory(session, components)

        self.assertEqual(enriched[0]["component_name"], "Tatami 80")
        self.assertEqual(enriched[1]["component_name"], "Futon Algodon")
        self.assertEqual(enriched[2]["component_name"], "")
        self.assertEqual(enriched[2]["component_name_lookup_source"], "inventory_bulk_no_result")
        self.assertFalse(any(call[0] == "v_inventory_hub_search_ranked" for call in data["__calls__"]))
        self.assertLessEqual(sum(1 for call in data["__calls__"] if call[0] == "inventory_items"), 4)

    def test_component_code_without_leading_zero_resolves_inventory_saved_with_leading_zero(self) -> None:
        session = Session(
            {
                "inventory_items": [
                    {"item_id": 201001, "name": "Tatami 80", "heca_reference": "0201001"},
                ]
            }
        )
        components = [{"component_item_code": "201001", "component_name": "", "quantity": 2}]

        enriched = inventory._fill_component_names_from_inventory(session, components)

        self.assertEqual(enriched[0]["component_name"], "Tatami 80")

    def test_numeric_code_normalization_keeps_alphanumeric_codes_intact_and_zeros_safe(self) -> None:
        self.assertEqual(inventory._normalize_inventory_numeric_code("0201001"), "201001")
        self.assertEqual(inventory._normalize_inventory_numeric_code("201001"), "201001")
        self.assertEqual(inventory._normalize_inventory_numeric_code("0000"), "0")
        self.assertEqual(inventory._normalize_inventory_numeric_code("AB0201001"), "AB0201001")

    def test_component_search_by_normalized_code_returns_simple_item_and_pack_with_names(self) -> None:
        session = Session(
            {
                "v_inventory_hub_search_ranked": [],
                "inventory_items": [
                    {"item_id": 201001, "name": "Tatami 80", "item_record_type": "simple", "heca_reference": "201001"},
                    {"item_id": 728003, "name": "Futon Algodon", "item_record_type": "simple", "heca_reference": "0728003"},
                    {
                        "item_id": 1111191,
                        "name": "PackWoo1111191",
                        "item_record_type": "woo_pack",
                        "hub_item_code": "WOO-PACK-1111191",
                    },
                ],
                "inventory_item_components": [
                    {
                        "parent_item_code": "WOO-PACK-1111191",
                        "component_item_code": "0201001",
                        "component_name": "",
                        "quantity": 2,
                        "relation_type": "component",
                    },
                    {
                        "parent_item_code": "WOO-PACK-1111191",
                        "component_item_code": "0728003",
                        "component_name": "",
                        "quantity": 1,
                        "relation_type": "component",
                    },
                ],
            }
        )

        rows = search_cloud_inventory_items(session, "201001", limit=10)

        self.assertEqual([row["item_id"] for row in rows], [201001, 1111191])
        self.assertEqual(
            self.app._price_display_name_for_inventory_item(self.app._inventory_item_from_cloud_row(rows[1])),
            "2x0201001xTatami 80 | 1x0728003xFuton Algodon",
        )

    def test_added_line_display_breaks_compact_composition_into_visible_lines(self) -> None:
        name = "2x0201001xTatami 80 | 1x0728003xFuton Algodon"

        self.assertEqual(
            self.app._price_line_display_name(name),
            "2x0201001xTatami 80\n1x0728003xFuton Algodon",
        )

    def test_pack_id_search_still_returns_pack(self) -> None:
        session = Session(
            {
                "v_inventory_hub_search_ranked": [
                    {
                        "search_token_norm": "woo-pack-1111191",
                        "result_item_id": 1111191,
                        "result_item_code": "WOO-PACK-1111191",
                        "result_name": "PackWoo1111191",
                        "result_record_type": "woo_pack",
                        "match_priority": 1,
                    }
                ],
                "inventory_items": [
                    {
                        "item_id": 1111191,
                        "name": "PackWoo1111191",
                        "item_record_type": "woo_pack",
                        "hub_item_code": "WOO-PACK-1111191",
                    }
                ],
                "inventory_item_components": [],
            }
        )

        rows = search_cloud_inventory_items(session, "WOO-PACK-1111191", limit=10)

        self.assertEqual([row["item_id"] for row in rows], [1111191])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.inventory import search_cloud_inventory_items  # noqa: E402
from futonhub.cloud.services.price_proposals import (  # noqa: E402
    _is_ui_deleted,
    analyze_price_proposal_soft_deletes,
    build_price_proposal_restore_plan,
    diagnose_real_price_proposals,
    preview_real_price_proposal,
)
from futonhub.cloud.services import inventory  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402
from futonhub.ui.erp.shared_ui import PriceProposal, ProposalLine  # noqa: E402


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
        self.limit_value: int | None = None
        self.range_value: tuple[int, int] | None = None
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
        self.limit_value = int(_args[0])
        return self

    def range(self, start: int, end: int):
        self.range_value = (start, end)
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
        if self.range_value is not None:
            start, end = self.range_value
            rows = rows[start : end + 1]
        elif self.limit_value is not None:
            rows = rows[: self.limit_value]
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
        self.app._price_edit_lines = []
        self.app._price_proposal_model = {}
        self.app._price_line_sources = {}
        self.app._price_proposal_line_sources = {}
        self.app._price_available_items = []
        self.app._inventory_items = []
        self.app._price_search_query = ""

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
            "2xTatami | 1xFuton",
        )
        self.assertEqual(item.raw["hub_pack_components"][0]["component_item_code"], "0728003")

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
            "5xTatami | 1xFuton",
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
            "1.5xTatami | 2xFuton",
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
                "hub_pack_components_multiline": "- 0728003 x1 - Futon\n- 0201001 x2 - Tatami",
            },
        )

        self.assertEqual(
            self.app._price_display_name_for_inventory_item(item),
            "2xTatami | 1xFuton",
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
            "2xTatami | 1xFuton",
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
            "2xTatami 80 | 1xFuton Algodon",
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

    def test_compound_woo_sku_builds_grouped_structured_components(self) -> None:
        components = inventory._components_from_woo_sku(
            "0201001|0201001|0728003",
            "WOO-PACK-3720",
        )

        self.assertEqual(
            components,
            [
                {
                    "parent_item_code": "WOO-PACK-3720",
                    "component_item_code": "0201001",
                    "component_name": "",
                    "quantity": 2,
                    "relation_type": "component",
                    "token_type": "woo_sku",
                },
                {
                    "parent_item_code": "WOO-PACK-3720",
                    "component_item_code": "0728003",
                    "component_name": "",
                    "quantity": 1,
                    "relation_type": "component",
                    "token_type": "woo_sku",
                },
            ],
        )

    def test_real_shape_woo_sku_fallback_returns_same_named_pack_for_both_code_forms(self) -> None:
        data = {
            "v_inventory_hub_search_ranked": [
                {
                    "search_token_norm": "0201001",
                    "result_item_id": 201001,
                    "result_item_code": "0201001",
                    "result_name": "Tatami, 80 x 200 x 5,5 cm.",
                    "result_record_type": "simple",
                    "match_priority": 1,
                },
                {
                    "search_token_norm": "0201001",
                    "result_item_id": 900000003720,
                    "result_item_code": "WOO-PACK-3720",
                    "result_name": "Pack Woo 3720",
                    "result_record_type": "woo_pack",
                    "match_priority": 2,
                },
                {
                    "search_token_norm": "201001",
                    "result_item_id": 201001,
                    "result_item_code": "0201001",
                    "result_name": "Tatami, 80 x 200 x 5,5 cm.",
                    "result_record_type": "simple",
                    "match_priority": 1,
                },
            ],
            "inventory_items": [
                {
                    "item_id": 201001,
                    "name": "Tatami, 80 x 200 x 5,5 cm.",
                    "item_record_type": "simple",
                    "heca_reference": "0201001",
                    "hub_item_code": "0201001",
                    "woo_sku": "0201001",
                },
                {
                    "item_id": 728003,
                    "name": "Futon Algodon",
                    "item_record_type": "simple",
                    "heca_reference": "0728003",
                    "hub_item_code": "0728003",
                    "woo_sku": "0728003",
                },
                {
                    "item_id": 900000003720,
                    "name": "Pack Woo 3720",
                    "item_record_type": "woo_pack",
                    "hub_item_code": "WOO-PACK-3720",
                    "woo_sku": "0201001|0201001|0728003",
                },
            ],
            "inventory_item_components": [],
        }

        rows_with_zero = search_cloud_inventory_items(Session(data), "0201001", limit=10)
        rows_without_zero = search_cloud_inventory_items(Session(data), "201001", limit=10)

        self.assertEqual([row["item_id"] for row in rows_with_zero], [201001, 900000003720])
        self.assertEqual([row["item_id"] for row in rows_without_zero], [201001, 900000003720])
        for rows in (rows_with_zero, rows_without_zero):
            pack = rows[1]
            self.assertEqual(
                [(component["component_item_code"], component["quantity"], component["component_name"]) for component in pack["hub_pack_components"]],
                [
                    ("0201001", 2, "Tatami, 80 x 200 x 5,5 cm."),
                    ("0728003", 1, "Futon Algodon"),
                ],
            )
            self.assertEqual(
                self.app._price_display_name_for_inventory_item(self.app._inventory_item_from_cloud_row(pack)),
                "2xTatami, 80 x 200 x 5,5 cm. | 1xFuton Algodon",
            )

        inventory_calls = [call for call in data["__calls__"] if call[0] == "inventory_items"]
        self.assertLess(len(inventory_calls), 20)

    def test_woo_sku_pack_lookup_pages_beyond_first_500_candidates(self) -> None:
        false_positive_packs = [
            {
                "item_id": 900000000000 + index,
                "name": f"False positive {index}",
                "item_record_type": "woo_pack",
                "hub_item_code": f"WOO-PACK-{index}",
                "woo_sku": "12010010",
            }
            for index in range(500)
        ]
        expected_pack = {
            "item_id": 900000003720,
            "name": "Pack Woo 3720",
            "item_record_type": "woo_pack",
            "hub_item_code": "WOO-PACK-3720",
            "woo_sku": "0201001|0201001|0728003",
        }
        session = Session({"inventory_items": [*false_positive_packs, expected_pack]})

        rows = inventory._find_inventory_pack_rows_by_woo_sku_token(session, "201001", limit=10)

        self.assertEqual([row["item_id"] for row in rows], [900000003720])

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
            "2xTatami 80 | 1xFuton Algodon",
        )

    def test_ranked_search_by_item_id_also_merges_packs_with_leading_zero_component(self) -> None:
        data = {
            "v_inventory_hub_search_ranked": [
                {
                    "search_token_norm": "201001",
                    "result_item_id": 201001,
                    "result_item_code": "201001",
                    "result_name": "Tatami 80",
                    "result_record_type": "simple",
                    "match_priority": 1,
                }
            ],
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
        session = Session(data)

        rows = search_cloud_inventory_items(session, "201001", limit=10)

        self.assertEqual([row["item_id"] for row in rows], [201001, 1111191])
        self.assertEqual(rows[1]["hub_pack_components"][0]["component_item_code"], "0201001")
        self.assertEqual(rows[1]["hub_pack_components"][0]["component_name"], "Tatami 80")
        self.assertEqual(
            self.app._price_display_name_for_inventory_item(self.app._inventory_item_from_cloud_row(rows[1])),
            "2xTatami 80 | 1xFuton Algodon",
        )
        self.assertTrue(any(call[0] == "v_inventory_hub_search_ranked" for call in data["__calls__"]))
        self.assertTrue(any(call[0] == "inventory_item_components" for call in data["__calls__"]))

    def test_added_line_display_breaks_compact_composition_into_visible_lines(self) -> None:
        name = "2x0201001xTatami 80 | 1x0728003xFuton Algodon"

        self.assertEqual(
            self.app._price_line_display_name(name),
            "2xTatami 80\n1xFuton Algodon",
        )

    def test_long_pick_table_rows_use_multiline_text_and_taller_rows(self) -> None:
        rows = [
            (
                "WOO-PACK-1",
                "2xTatami 80x200x5,5 | 1xFuton algodon 150x200x14 | 2xCojin",
                "100.00",
            )
        ]

        self.assertEqual(
            self.app._price_pick_table_display_name(rows[0][1]),
            "2xTatami 80x200x5,5\n1xFuton algodon 150x200x14\n2xCojin",
        )
        self.assertGreaterEqual(self.app._price_pick_table_rowheight(rows), 68)

    def test_item_results_use_compact_simple_rows_and_multiline_pack_rows(self) -> None:
        self.assertEqual(self.app._price_item_result_line_count("Tatami normal"), 1)
        self.assertEqual(
            self.app._price_item_result_line_count("2xTatami 80x200x5,5 | 1xFuton algodon 150x200x14"),
            2,
        )

    def test_item_results_viewport_is_bounded_and_scrollable_controls_remain_outside(self) -> None:
        rows = [
            (str(index), "2xTatami | 1xFuton | 2xCojin", "100.00")
            for index in range(20)
        ]
        source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)

        self.assertIn("tk.Canvas(viewport", source)
        self.assertIn("orient=tk.VERTICAL", source)
        self.assertIn("orient=tk.HORIZONTAL", source)
        self.assertIn('text="Subida %"', source)
        self.assertIn('text="Valor"', source)
        self.assertIn('"Anadir"', source)
        self.assertIn('"Anadir todos"', source)
        self.assertLess(source.index("tk.Canvas(viewport"), source.index("footer = tk.Frame(card"))

    def test_item_result_selection_double_click_and_add_preserve_original_row_values(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)
        row = ("900000003720", "2xTatami | 1xFuton", "245.00")

        self.assertIn('widget.bind("<Button-1>"', source)
        self.assertIn('widget.bind("<Double-Button-1>"', source)
        self.assertIn("self._price_add_rows_to_proposal(selected_rows()", source)
        self.assertEqual(row, ("900000003720", "2xTatami | 1xFuton", "245.00"))

    def test_only_items_use_variable_height_widget_list(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_pick_table)

        self.assertIn('if title == "Items":', source)
        self.assertIn("self._price_items_pick_list(", source)
        self.assertIn("ttk.Treeview", source)

    def test_price_workspace_removes_items_label_and_variations_block(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._build_price_edit_workspace)

        self.assertNotIn('"Items"', source)
        self.assertNotIn("variations_host", source)
        self.assertNotIn("_render_price_variations_picker", source)
        self.assertIn("self._price_items_pick_list(left, results)", source)

    def test_price_view_separates_saved_list_and_compact_editor_headings(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._build_prices)

        self.assertIn('text="Nueva Propuesta"', source)
        self.assertIn('text="Cambio de Precios"', source)
        self.assertIn('"Nueva propuesta"', source)
        self.assertIn("command=self._start_new_price_proposal", source)
        self.assertLess(source.index('if self._price_mode == "edit":'), source.index('text="Nueva Propuesta"'))
        self.assertLess(source.index("else:"), source.index('text="Cambio de Precios"'))
        self.assertNotIn('self._page_header(', source)
        self.assertNotIn('"Operaciones"', source)
        self.assertNotIn('"Propuestas, validacion, aprobacion y publicacion protegida."', source)
        self.assertIn('pady=(0, 10)', source)

    def test_new_proposal_action_opens_editor_without_saved_list_workspace(self) -> None:
        self.app._selected_price_proposal = object()
        self.app._proposal_source_item = object()
        self.app._price_edit_initialized = True
        self.app._price_edit_selected_code = "old"
        self.app._price_edit_notice = "old"
        self.app._price_search_query = "old"
        self.app._price_search_results = [{"code": "old"}]
        shown: list[str] = []
        self.app._show_view = shown.append

        self.app._start_new_price_proposal()

        self.assertEqual(self.app._price_mode, "edit")
        self.assertIsNone(self.app._selected_price_proposal)
        self.assertEqual(shown, ["precios"])

    def test_cancel_editor_resets_draft_and_returns_to_saved_list(self) -> None:
        self.app._price_mode = "edit"
        self.app._price_edit_lines = [ProposalLine("1", "Draft", "10", "11", "+1", "up")]
        self.app._price_edit_initialized = True
        self.app._price_edit_selected_code = "1"
        self.app._price_edit_notice = "draft"
        self.app._price_search_query = "draft"
        self.app._price_search_results = [{"code": "1"}]
        shown: list[str] = []
        self.app._show_view = shown.append

        self.app._cancel_price_edit()

        self.assertEqual(self.app._price_mode, "saved")
        self.assertEqual(self.app._price_edit_lines, [])
        self.assertEqual(shown, ["precios"])

    def test_save_success_keeps_previous_return_and_refresh_flow(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._finish_price_edit_saved)

        self.assertIn("self._price_reset_edit_state()", source)
        self.assertIn("self._price_loaded_once = False", source)
        self.assertIn('self._set_price_mode("saved")', source)

    def test_saved_and_editor_workspaces_are_rendered_in_exclusive_branches(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._build_prices)

        edit_call = source.index("self._build_price_edit_workspace(parent)")
        else_branch = source.index("else:", edit_call)
        saved_call = source.index("self._build_saved_proposals_workspace(parent)")
        self.assertLess(edit_call, else_branch)
        self.assertLess(else_branch, saved_call)

    def test_unified_results_are_base_variations_packs_and_deduplicated(self) -> None:
        base = inventory_item(
            "201001",
            "Futon base",
            raw={"woo_item_kind": "product", "woo_id": 100, "item_record_type": "simple"},
        )
        variation = inventory_item(
            "101",
            "Futon base - 90x200",
            raw={"woo_item_kind": "variation", "woo_id": 101, "woo_parent_id": 100, "item_record_type": "woo_variation"},
        )
        duplicate_variation = inventory_item(
            "101-copy",
            "Duplicada",
            raw={"woo_item_kind": "variation", "woo_id": 101, "woo_parent_id": 100, "item_record_type": "woo_variation"},
        )
        pack = inventory_item(
            "9001",
            "Pack Woo",
            raw={"woo_item_kind": "product", "woo_id": 9001, "item_record_type": "woo_pack"},
        )

        results = self.app._price_results_from_items([pack, variation, base, duplicate_variation])

        self.assertEqual([row["type"] for row in results], ["Simple", "Variacion", "Pack"])
        self.assertEqual([row["code"] for row in results], ["201001", "101", "9001"])

    def test_unified_search_loads_related_variations_in_one_batch(self) -> None:
        data = {
            "product_variations": [
                {
                    "woo_id": 101,
                    "parent_woo_id": 100,
                    "parent_name": "Futon base",
                    "attributes_label": "90x200",
                    "price": 120,
                },
                {
                    "woo_id": 102,
                    "parent_woo_id": 100,
                    "parent_name": "Futon base",
                    "attributes_label": "140x200",
                    "price": 150,
                },
            ]
        }
        self.app._cloud_session = Session(data)
        rows = [
            {
                "item_id": 201001,
                "name": "Futon base",
                "woo_item_kind": "product",
                "woo_id": 100,
                "woo_price": 110,
                "item_record_type": "simple",
            },
            {
                "item_id": 9001,
                "name": "Pack Woo",
                "woo_item_kind": "product",
                "woo_id": 9001,
                "woo_price": 200,
                "item_record_type": "woo_pack",
            },
        ]

        unified = self.app._price_unified_search_rows(rows)
        items = [self.app._inventory_item_from_cloud_row(row) for row in unified]
        results = self.app._price_results_from_items(items)

        self.assertEqual([row["type"] for row in results], ["Simple", "Variacion", "Variacion", "Pack"])
        self.assertEqual([row["code"] for row in results], ["201001", "101", "102", "9001"])
        variation_calls = [call for call in data["__calls__"] if call[0] == "product_variations"]
        self.assertEqual(len(variation_calls), 1)

    def test_pack_with_woo_source_is_safe_for_bulk_preview(self) -> None:
        self.app._price_search_query = "futon"
        pack = inventory_item(
            "9001",
            "Pack Woo",
            "200.00",
            raw={"woo_item_kind": "product", "woo_id": 9001, "item_record_type": "woo_pack"},
        )
        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([pack]), "10", "")

        self.assertEqual(preview["rows"][0]["status"], "VALIDO")
        self.assertEqual(preview["rows"][0]["key"], "pack:9001")
        self.assertEqual(preview["rows"][0]["source"]["item_kind"], "pack")
        self.assertEqual(preview["counts"]["packs_included"], 1)
        self.assertEqual(preview["rows"][0]["new_price_value"], 220.0)

    def test_pack_product_and_variation_with_same_visible_code_do_not_collide(self) -> None:
        product = inventory_item(
            "930000010533",
            "Producto",
            "100",
            raw={"woo_item_kind": "product", "woo_id": 100, "item_record_type": "simple"},
        )
        variation = inventory_item(
            "930000010533",
            "Variacion",
            "110",
            raw={"woo_item_kind": "variation", "woo_id": 101, "item_record_type": "woo_variation"},
        )
        pack = inventory_item(
            "930000010533",
            "Pack",
            "120",
            raw={"woo_item_kind": "product", "woo_id": 930000010533, "item_record_type": "woo_pack"},
        )

        results = self.app._price_results_from_items([product, variation, pack])

        self.assertEqual(
            [row["key"] for row in results],
            ["product:100", "variation:101", "pack:930000010533"],
        )

    def test_pack_930000010533_keeps_type_through_model_validation_and_persistence(self) -> None:
        self.app._price_search_query = "tatami"
        pack = inventory_item(
            "930000010533",
            "Pack Tatamis",
            "120",
            raw={
                "woo_item_kind": "product",
                "woo_id": 930000010533,
                "item_record_type": "woo_pack",
                "hub_item_code": "WOO-PACK-930000010533",
            },
        )
        preview = self.app._price_build_bulk_preview(
            self.app._price_results_from_items([pack]),
            "10",
            "",
        )
        row = preview["accepted_lines"][0]
        self.assertEqual(row["source"]["item_kind"], "pack")

        self.app._price_model_put(row["line"], row["source"])
        self.app._price_sync_legacy_model_views()
        entries = self.app._price_model_entries()
        self.app._price_rendered_model_keys = ("pack:930000010533",)
        self.app._price_rendered_model_types = (("pack:930000010533", "pack"),)
        validated_kinds: list[str] = []
        persisted_kinds: list[str] = []
        self.app._cloud_session = object()

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                side_effect=lambda _session, kind, _woo_id, _price, **_kwargs: (
                    validated_kinds.append(kind)
                    or {"price_safety": {"status": "OK", "messages": []}}
                ),
            ),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                side_effect=lambda _session, kind, woo_id, _price, **_kwargs: (
                    persisted_kinds.append(kind)
                    or {"proposal": {"id": f"{kind}-{woo_id}"}}
                ),
            ),
        ):
            saved, _counts = self.app._price_validate_and_persist_entries(
                entries,
                "Tatamis",
                "token",
            )

        self.assertEqual([entry["key"] for entry in entries], ["pack:930000010533"])
        self.assertEqual(validated_kinds, ["pack"])
        self.assertEqual(persisted_kinds, ["pack"])
        self.assertEqual(saved, ["pack-930000010533"])

    def test_panel_snapshot_type_mismatch_blocks_before_write(self) -> None:
        line = ProposalLine("930000010533", "Pack", "100", "110", "+10%", "up")
        self.app._price_model_put(
            line,
            {"item_kind": "pack", "woo_id": 930000010533},
        )
        self.app._price_rendered_model_keys = ("pack:930000010533",)
        self.app._price_rendered_model_types = (("pack:930000010533", "product"),)

        with self.assertRaisesRegex(ValueError, "tipo del panel"):
            self.app._price_canonical_snapshot()

    def test_pack_validator_fetches_product_but_applies_pack_rules(self) -> None:
        session = Session({
            "inventory_items": [{
                "item_id": 900000003662,
                "woo_id": 930000010533,
                "name": "Pack Tatamis",
                "item_record_type": "woo_pack",
                "woo_price": 120,
                "hub_item_code": "WOO-PACK-930000010533",
            }],
        })
        settings = SimpleNamespace(
            price_drop_warning_percent=30.0,
            price_drop_block_percent=60.0,
        )

        preview = preview_real_price_proposal(
            session,
            "pack",
            930000010533,
            132,
            settings=settings,
        )

        self.assertEqual(preview["item_kind"], "pack")
        self.assertEqual(preview["price_safety"]["status"], "OK")
        self.assertNotIn(
            "padre variable",
            " ".join(preview["price_safety"]["messages"]).lower(),
        )

    def test_pack_3662_resolves_from_synthetic_inventory_snapshot(self) -> None:
        snapshot = {
            "item_id": 900000003662,
            "woo_id": 3662,
            "name": "Pack Woo 3662",
            "item_record_type": "woo_pack",
            "hub_item_code": "WOO-PACK-3662",
            "woo_price": 240,
            "hub_pack_components": [
                {"component_item_code": "0201001", "quantity": 2},
            ],
        }
        settings = SimpleNamespace(
            price_drop_warning_percent=30.0,
            price_drop_block_percent=60.0,
        )

        preview = preview_real_price_proposal(
            Session({}),
            "pack",
            3662,
            250,
            settings=settings,
            item_snapshot=snapshot,
        )

        self.assertEqual(preview["item_kind"], "pack")
        self.assertEqual(preview["item"]["item_id"], 900000003662)
        self.assertEqual(preview["item"]["hub_item_code"], "WOO-PACK-3662")
        self.assertEqual(len(preview["item"]["hub_pack_components"]), 1)

    def test_mixed_variation_and_pack_preflight_failure_persists_zero_rows(self) -> None:
        variation = ProposalLine("variation:3662", "Variacion", "100", "110", "+10%", "up")
        pack = ProposalLine("900000003662", "Pack", "200", "220", "+10%", "up")
        self.app._price_model_put(
            variation,
            {"item_kind": "variation", "woo_id": 3662},
        )
        self.app._price_model_put(
            pack,
            {
                "item_kind": "pack",
                "woo_id": 3662,
                "item_snapshot": {
                    "item_id": 900000003662,
                    "woo_id": 3662,
                    "item_record_type": "woo_pack",
                    "hub_item_code": "WOO-PACK-3662",
                    "woo_price": 200,
                },
            },
        )
        entries = self.app._price_model_entries()
        self.app._cloud_session = object()
        writes: list[str] = []

        def preview(_session, kind, _woo_id, _price, **_kwargs):
            if kind == "pack":
                raise ValueError("pack:3662 no resoluble")
            return {"price_safety": {"status": "OK", "messages": []}}

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch("futonhub.ui.erp.prototype.preview_real_price_proposal", side_effect=preview),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                side_effect=lambda *_args, **_kwargs: writes.append("write"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "pack:3662"):
                self.app._price_validate_and_persist_entries(
                    entries,
                    "Mixta",
                    "token",
                )

        self.assertEqual(writes, [])
        self.assertEqual(
            [entry["key"] for entry in entries],
            ["variation:3662", "pack:3662"],
        )

    def test_mixed_variation_and_pack_persist_with_distinct_kinds(self) -> None:
        variation = ProposalLine("variation:3662", "Variacion", "100", "110", "+10%", "up")
        pack = ProposalLine("900000003662", "Pack", "200", "220", "+10%", "up")
        self.app._price_model_put(
            variation,
            {"item_kind": "variation", "woo_id": 3662},
        )
        self.app._price_model_put(
            pack,
            {
                "item_kind": "pack",
                "woo_id": 3662,
                "hub_item_code": "WOO-PACK-3662",
                "item_snapshot": {
                    "item_id": 900000003662,
                    "woo_id": 3662,
                    "item_record_type": "woo_pack",
                    "hub_item_code": "WOO-PACK-3662",
                    "woo_price": 200,
                    "hub_pack_components": [{"component_item_code": "0201001"}],
                },
            },
        )
        entries = self.app._price_model_entries()
        self.app._cloud_session = object()
        persisted: list[tuple[str, int, dict]] = []

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                return_value={"price_safety": {"status": "OK", "messages": []}},
            ),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                side_effect=lambda _session, kind, woo_id, _price, **kwargs: (
                    persisted.append((kind, woo_id, kwargs))
                    or {"proposal": {"id": f"{kind}-{woo_id}"}}
                ),
            ),
        ):
            saved, _counts = self.app._price_validate_and_persist_entries(
                entries,
                "Mixta",
                "token",
            )

        self.assertEqual(saved, ["variation-3662", "pack-3662"])
        self.assertEqual(
            [(kind, woo_id) for kind, woo_id, _kwargs in persisted],
            [("variation", 3662), ("pack", 3662)],
        )
        self.assertEqual(
            persisted[1][2]["item_snapshot"]["hub_item_code"],
            "WOO-PACK-3662",
        )

    def test_historical_pack_reload_prefers_canonical_source_metadata(self) -> None:
        proposal = self.app._price_proposal_from_cloud_row({
            "id": "row-pack",
            "item_kind": "product",
            "item_woo_id": 3662,
            "name": "Pack historico",
            "old_price": 200,
            "new_price": 220,
            "status": "pending",
            "created_at": "2025-01-01T10:00:00+00:00",
            "source_row": {
                "ui_canonical_item_kind": "pack",
                "ui_canonical_woo_id": 3662,
                "ui_hub_item_code": "WOO-PACK-3662",
            },
        })

        self.assertEqual(proposal.lines[0].code, "pack:3662")
        self.assertEqual(proposal.lines[0].old_price, "200.00")
        self.assertEqual(proposal.lines[0].new_price, "220.00")

    def test_pack_without_woo_source_is_excluded_from_bulk_preview(self) -> None:
        self.app._price_search_query = "futon"
        pack = inventory_item("WOO-PACK-X", "Pack Woo", "200.00", raw={"item_record_type": "woo_pack"})

        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([pack]), "10", "")

        self.assertEqual(preview["rows"][0]["status"], "EXCLUIDO")
        self.assertEqual(preview["rows"][0]["reason"], "Pack pendiente de logica masiva")
        self.assertEqual(preview["counts"]["packs_excluded"], 1)

    def test_bulk_preview_does_not_modify_proposal_and_marks_existing(self) -> None:
        self.app._price_search_query = "futon"
        existing = ProposalLine("201001", "Existente", "100.00", "110.00", "+10%", "up")
        self.app._price_model_put(existing, {"item_kind": "product", "woo_id": 100})
        self.app._price_sync_legacy_model_views()
        item = inventory_item(
            "201001",
            "Futon",
            "100.00",
            raw={"woo_item_kind": "product", "woo_id": 100, "item_record_type": "simple"},
        )
        before = list(self.app._price_edit_lines)

        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([item]), "10", "")

        self.assertEqual(self.app._price_edit_lines, before)
        self.assertEqual(preview["rows"][0]["status"], "YA EXISTE")
        self.assertEqual(preview["counts"]["total_add"], 0)

    def test_bulk_preview_includes_warning_and_excludes_error(self) -> None:
        self.app._price_search_query = "futon"
        warning_item = inventory_item(
            "201001",
            "Sin precio",
            "0",
            raw={"woo_item_kind": "variation", "woo_id": 100, "woo_parent_id": 10, "item_record_type": "woo_variation"},
        )
        error_item = inventory_item(
            "201002",
            "Error",
            "10",
            raw={"woo_item_kind": "product", "woo_id": 101, "item_record_type": "simple"},
        )

        preview = self.app._price_build_bulk_preview(
            self.app._price_results_from_items([warning_item, error_item]),
            "",
            "5",
        )
        warning_row = next(row for row in preview["rows"] if row["code"] == "201001")
        self.assertEqual(warning_row["status"], "WARNING")
        with patch.object(self.app, "_price_validate_proposed_price", side_effect=[("Critical", "bloqueado"), ("Critical", "bloqueado")]):
            error_preview = self.app._price_build_bulk_preview(
                self.app._price_results_from_items([error_item]),
                "",
                "5",
            )
        self.assertEqual(error_preview["rows"][0]["status"], "ERROR")
        self.assertEqual(error_preview["counts"]["total_add"], 0)

    def test_both_adjustment_fields_are_rejected_without_changes(self) -> None:
        self.app._price_search_query = "futon"
        item = inventory_item(
            "201001",
            "Futon",
            "100",
            raw={"woo_item_kind": "product", "woo_id": 100, "item_record_type": "simple"},
        )

        with self.assertRaisesRegex(ValueError, "No se pueden usar Subida % y Valor"):
            self.app._price_build_bulk_preview(self.app._price_results_from_items([item]), "10", "5")
        self.assertEqual(self.app._price_edit_lines, [])

    def test_bulk_confirmation_adds_only_valid_and_warning_rows(self) -> None:
        self.app._price_search_query = "futon"
        self.app._show_view = lambda _view: None
        valid = inventory_item(
            "201001",
            "Futon",
            "100",
            raw={"woo_item_kind": "product", "woo_id": 100, "item_record_type": "simple"},
        )
        warning = inventory_item(
            "201002",
            "Nuevo",
            "0",
            raw={"woo_item_kind": "variation", "woo_id": 101, "woo_parent_id": 10, "item_record_type": "woo_variation"},
        )
        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([valid, warning]), "", "5")

        class Window:
            def grab_release(self):
                return None

            def destroy(self):
                return None

        with patch("futonhub.ui.erp.prototype.messagebox.showinfo"):
            self.app._confirm_price_bulk_add(Window(), preview)

        self.assertEqual([line.code for line in self.app._price_edit_lines], ["201001", "201002"])
        self.assertEqual(self.app._price_edit_lines[1].direction, "warning")
        self.assertIn("Anadidos: 1", self.app._price_edit_notice)
        self.assertIn("Warnings anadidos: 1", self.app._price_edit_notice)

    def test_bulk_preview_modal_uses_fixed_header_expandable_table_and_fixed_footer(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._open_price_bulk_add_preview)

        self.assertIn("win.rowconfigure(1, weight=1)", source)
        self.assertIn('summary.grid(row=0, column=0, sticky="ew"', source)
        self.assertIn('table_host.grid(row=1, column=0, sticky="nsew"', source)
        self.assertIn('footer.grid(row=2, column=0, sticky="ew"', source)
        self.assertIn("table_host.rowconfigure(0, weight=1)", source)
        self.assertIn("orient=tk.VERTICAL", source)
        self.assertIn("orient=tk.HORIZONTAL", source)
        self.assertNotIn("table_host.pack(", source)
        self.assertNotIn("footer.pack(", source)

    def test_bulk_preview_dimensions_scale_and_remain_inside_screen(self) -> None:
        laptop = self.app._price_bulk_preview_dimensions(1366, 768)
        desktop = self.app._price_bulk_preview_dimensions(2560, 1440)

        self.assertEqual(laptop, (1147, 599, 760, 500))
        self.assertEqual(desktop, (2150, 1123, 760, 500))
        self.assertLessEqual(laptop[0], 1366 - 80)
        self.assertLessEqual(laptop[1], 768 - 80)
        self.assertGreater(desktop[0], laptop[0])
        self.assertGreater(desktop[1], laptop[1])

    def test_bulk_preview_footer_stays_outside_scroll_for_more_than_100_results(self) -> None:
        self.app._price_search_query = "futon"
        items = [
            inventory_item(
                str(200000 + index),
                f"Futon {index}",
                "100",
                raw={"woo_item_kind": "product", "woo_id": 1000 + index, "item_record_type": "simple"},
            )
            for index in range(120)
        ]

        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items(items), "10", "")
        source = inspect.getsource(FutonHubErpPrototype._open_price_bulk_add_preview)

        self.assertEqual(len(preview["rows"]), 120)
        self.assertEqual(preview["counts"]["total_add"], 120)
        self.assertLess(source.index("table_host = tk.Frame"), source.index("footer = tk.Frame"))
        self.assertIn('footer.grid(row=2', source)

    def test_bulk_preview_close_and_escape_use_cancel_without_confirming(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._open_price_bulk_add_preview)

        self.assertIn('win.protocol("WM_DELETE_WINDOW", cancel_preview)', source)
        self.assertIn('win.bind("<Escape>", cancel_preview)', source)
        self.assertIn('command=cancel_preview', source)
        self.assertIn("win.after_idle(cancel_button.focus_set)", source)
        self.assertNotIn('win.bind("<Return>"', source)

    def test_bulk_preview_is_modal_resizable_and_confirmation_flow_is_unchanged(self) -> None:
        modal_source = inspect.getsource(FutonHubErpPrototype._open_price_bulk_add_preview)
        confirm_source = inspect.getsource(FutonHubErpPrototype._confirm_price_bulk_add)

        self.assertIn("win.transient(self)", modal_source)
        self.assertIn("win.grab_set()", modal_source)
        self.assertIn("win.resizable(True, True)", modal_source)
        self.assertIn("self._price_bulk_preview_dimensions", modal_source)
        self.assertIn('preview.get("accepted_lines")', confirm_source)
        self.assertIn("self._price_model_put(line, source)", confirm_source)

    def test_variable_parent_without_unique_price_is_error_and_variation_remains_valid(self) -> None:
        parent = inventory_item(
            "200",
            "Tatami variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        variation = inventory_item(
            "201",
            "Tatami 90x200",
            "120",
            raw={"woo_item_kind": "variation", "woo_id": 201, "woo_parent_id": 200, "item_record_type": "woo_variation"},
        )
        results = self.app._price_results_from_items([parent, variation])

        parent_status = self.app._price_classify_result(results[0])
        variation_status = self.app._price_classify_result(results[1])
        preview = self.app._price_build_bulk_preview(results, "10", "")

        self.assertEqual(parent_status[:2], ("ERROR", "Producto padre sin precio unico"))
        self.assertEqual(variation_status[0], "VALIDO")
        self.assertEqual([row["status"] for row in preview["rows"]], ["ERROR", "VALIDO"])
        self.assertEqual(preview["counts"]["total_add"], 1)

    def test_pending_empty_and_non_numeric_prices_are_never_eligible(self) -> None:
        for value in ("Pendiente", "", "NO ESTA"):
            item = inventory_item(
                f"item-{value}",
                "Sin precio",
                value,
                raw={"woo_item_kind": "product", "woo_id": 10, "item_record_type": "simple"},
            )
            result = self.app._price_results_from_items([item])[0]
            status, reason, price = self.app._price_classify_result(result)
            self.assertEqual(status, "ERROR")
            self.assertIn("Precio Woo pendiente", reason)
            self.assertIsNone(price)

    def test_individual_add_rejects_ineligible_parent_before_proposal_mutation(self) -> None:
        parent = inventory_item(
            "200",
            "Tatami variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        self.app._price_search_results = self.app._price_results_from_items([parent])
        self.app._show_view = lambda _view: None

        with patch("futonhub.ui.erp.prototype.messagebox.showerror") as error:
            self.app._price_add_rows_to_proposal([("200", "Tatami variable", "Pendiente")], "10", "")

        self.assertEqual(self.app._price_edit_lines, [])
        self.assertEqual(
            error.call_args.args[1],
            "Este producto padre no tiene un precio Woo unico.\nSelecciona una variacion concreta.",
        )

    def test_refresh_groups_same_save_token_and_deduplicates_same_real_id(self) -> None:
        rows = [
            {
                "id": "id-1",
                "item_kind": "product",
                "item_woo_id": 10,
                "name": "Tatami",
                "old_price": 100,
                "new_price": 110,
                "status": "pending",
                "created_at": "2026-06-22T10:00:00",
                "source_row": {"ui_proposal_name": "Grupo", "ui_save_token": "token-a", "ui_line_name": "Tatami"},
            },
            {
                "id": "id-2",
                "item_kind": "variation",
                "item_woo_id": 11,
                "name": "Tatami 90",
                "old_price": 120,
                "new_price": 130,
                "status": "pending",
                "created_at": "2026-06-22T10:00:00",
                "source_row": {"ui_proposal_name": "Grupo", "ui_save_token": "token-a", "ui_line_name": "Tatami 90"},
            },
        ]

        grouped = self.app._price_group_cloud_proposals([rows[0], rows[0], rows[1]])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].items, 2)
        self.assertEqual(grouped[0].raw["ui_member_ids"], ["id-1", "id-2"])

    def test_same_name_with_different_tokens_remains_independent(self) -> None:
        base = {
            "item_kind": "product",
            "name": "Tatami",
            "old_price": 100,
            "new_price": 110,
            "status": "pending",
            "created_at": "2026-06-22T10:00:00",
        }
        rows = [
            {**base, "id": "id-1", "item_woo_id": 10, "source_row": {"ui_proposal_name": "Mismo nombre", "ui_save_token": "token-a"}},
            {**base, "id": "id-2", "item_woo_id": 20, "source_row": {"ui_proposal_name": "Mismo nombre", "ui_save_token": "token-b"}},
        ]

        grouped = self.app._price_group_cloud_proposals(rows)

        self.assertEqual(len(grouped), 2)
        self.assertEqual([proposal.raw["ui_member_ids"] for proposal in grouped], [["id-1"], ["id-2"]])

    def test_empty_saved_proposal_detail_helper_exists_and_clears_panel(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._render_empty_saved_proposal_detail)

        self.assertIn("for child in parent.winfo_children()", source)
        self.assertIn("child.destroy()", source)
        self.assertIn("Selecciona una propuesta para ver sus detalles.", source)
        self.assertIn("expand=True", source)

    def test_saved_workspace_uses_empty_detail_for_zero_or_filtered_results(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._build_saved_proposals_workspace)

        self.assertIn("if not proposals:", source)
        self.assertIn("self._selected_price_proposal = None", source)
        self.assertIn("self._render_empty_saved_proposal_detail(detail_host)", source)

    def test_historical_rows_without_token_group_by_persisted_header_reference(self) -> None:
        rows = [
            {
                "id": "line-1",
                "item_kind": "product",
                "item_woo_id": 10,
                "name": "Tatami",
                "old_price": 100,
                "new_price": 110,
                "status": "pending",
                "created_at": "2025-06-01T10:00:00",
                "source_row": {"ui_proposal_name": "Historica", "ui_proposal_id": "header-1", "ui_line_name": "Tatami"},
            },
            {
                "id": "line-2",
                "item_kind": "variation",
                "item_woo_id": 11,
                "name": "Tatami 90",
                "old_price": 120,
                "new_price": 130,
                "status": "pending",
                "created_at": "2025-06-01T10:00:00",
                "source_row": {"ui_proposal_name": "Historica", "ui_proposal_id": "header-1", "ui_line_name": "Tatami 90"},
            },
        ]

        grouped = self.app._price_group_cloud_proposals(rows)

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].items, 2)
        self.assertEqual([line.name for line in grouped[0].lines], ["Tatami", "Tatami 90"])
        self.assertEqual(grouped[0].raw["ui_member_ids"], ["line-1", "line-2"])

    def test_historical_rows_without_reliable_reference_remain_separate_even_with_same_name(self) -> None:
        base = {
            "item_kind": "product",
            "name": "Tatami",
            "old_price": 100,
            "new_price": 110,
            "created_at": "2025-06-01T10:00:00",
            "source_row": {"ui_proposal_name": "Mismo nombre historico"},
        }
        rows = [
            {**base, "id": "legacy-1", "item_woo_id": 10, "status": "error"},
            {**base, "id": "legacy-2", "item_woo_id": 20, "status": "rolled_back"},
        ]

        grouped = self.app._price_group_cloud_proposals(rows)

        self.assertEqual(len(grouped), 2)
        self.assertEqual([proposal.raw["ui_member_ids"] for proposal in grouped], [["legacy-1"], ["legacy-2"]])
        self.assertEqual([proposal.status for proposal in grouped], ["Error critico", "Restaurada"])

    def test_historical_error_pending_and_restored_states_remain_visible(self) -> None:
        rows = [
            {
                "id": f"id-{status}",
                "item_kind": "product",
                "item_woo_id": index,
                "name": status,
                "old_price": 100,
                "new_price": 110,
                "status": status,
                "created_at": "2025-06-01T10:00:00",
                "source_row": {},
            }
            for index, status in enumerate(("pending", "error", "rolled_back"), start=1)
        ]

        grouped = self.app._price_group_cloud_proposals(rows)

        self.assertEqual(len(grouped), 3)
        self.assertEqual([proposal.status for proposal in grouped], ["Pendiente", "Error critico", "Restaurada"])

    def test_refresh_loads_maximum_service_window_and_renders_once_after_worker(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._refresh_price_proposals)
        before_worker, worker = source.split("def worker()", 1)

        self.assertIn('limit=200', worker)
        active_refresh = before_worker.split('overlay = self._price_start_working_overlay', 1)[1]
        self.assertNotIn('self._show_view("precios")', active_refresh)
        self.assertIn("_finish_price_proposals_refresh", worker)
        finish_source = inspect.getsource(FutonHubErpPrototype._finish_price_proposals_refresh)
        self.assertIn("_price_stop_working_overlay", finish_source)

    def test_repeated_refresh_is_guarded_and_grouping_deduplicates_real_ids(self) -> None:
        refresh_source = inspect.getsource(FutonHubErpPrototype._refresh_price_proposals)
        duplicate = {
            "id": "same-id",
            "item_kind": "product",
            "item_woo_id": 10,
            "name": "Tatami",
            "old_price": 100,
            "new_price": 110,
            "status": "pending",
            "created_at": "2025-06-01T10:00:00",
            "source_row": {},
        }

        grouped = self.app._price_group_cloud_proposals([duplicate, duplicate])

        self.assertIn("self._price_refresh_generation += 1", refresh_source)
        self.assertEqual(len(grouped), 1)

    def test_historical_group_delete_keeps_exact_member_ids(self) -> None:
        rows = [
            {
                "id": "line-1",
                "item_kind": "product",
                "item_woo_id": 10,
                "name": "Tatami",
                "old_price": 100,
                "new_price": 110,
                "status": "pending",
                "created_at": "2025-06-01T10:00:00",
                "source_row": {"ui_proposal_id": "header-1"},
            },
            {
                "id": "line-2",
                "item_kind": "variation",
                "item_woo_id": 11,
                "name": "Tatami 90",
                "old_price": 120,
                "new_price": 130,
                "status": "pending",
                "created_at": "2025-06-01T10:00:00",
                "source_row": {"ui_proposal_id": "header-1"},
            },
        ]

        grouped = self.app._price_group_cloud_proposals(rows)

        self.assertEqual(grouped[0].raw["ui_member_ids"], ["line-1", "line-2"])
        delete_source = inspect.getsource(FutonHubErpPrototype._open_delete_price_proposal_confirmation)
        self.assertIn("proposal_ids=member_ids", delete_source)

    def test_save_has_logical_double_click_guard_unique_token_and_exact_edit_id(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._save_price_edit)
        persist_source = inspect.getsource(FutonHubErpPrototype._price_validate_and_persist_entries)

        self.assertIn("if self._price_save_in_progress:", source)
        self.assertIn("self._price_save_in_progress = True", source)
        self.assertIn("self._price_save_token = uuid.uuid4().hex", source)
        self.assertIn('"ui_save_token": save_token', persist_source)
        self.assertIn("proposal_id=str(source.get(\"proposal_id\"))", persist_source)
        self.assertEqual(source.count("threading.Thread("), 1)

    def test_valid_save_plan_validates_all_variations_before_first_write(self) -> None:
        self.app._cloud_session = object()
        lines = [
            ProposalLine("101", "Tatami 90", "100", "110", "+10%", "up"),
            ProposalLine("102", "Tatami 140", "120", "130", "+8%", "up"),
        ]
        self.app._price_model_put(lines[0], {"item_kind": "variation", "woo_id": 101})
        self.app._price_model_put(lines[1], {"item_kind": "variation", "woo_id": 102})
        entries = self.app._price_model_entries()
        events: list[str] = []

        def preview(_session, _kind, woo_id, _price, **_kwargs):
            events.append(f"validate:{woo_id}")
            return {"price_safety": {"status": "OK", "messages": []}}

        def create(_session, _kind, woo_id, _price, **_kwargs):
            events.append(f"write:{woo_id}")
            return {"proposal": {"id": f"id-{woo_id}", "source_row": _kwargs.get("source_row_updates") or {}}}

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch("futonhub.ui.erp.prototype.preview_real_price_proposal", side_effect=preview),
            patch("futonhub.ui.erp.prototype.create_real_price_proposal", side_effect=create),
        ):
            saved, counts = self.app._price_validate_and_persist_entries(entries, "Tatamis", "token-1")

        self.assertEqual(events, ["validate:101", "validate:102", "write:101", "write:102"])
        self.assertEqual(saved, ["id-101", "id-102"])
        self.assertEqual(counts, {"up": 2, "down": 0, "flat": 0})

    def test_validation_error_on_later_line_persists_zero_rows(self) -> None:
        self.app._cloud_session = object()
        lines = [
            ProposalLine("101", "Tatami 90", "100", "110", "+10%", "up"),
            ProposalLine("200", "Padre variable", "-", "120", "-", "flat"),
        ]
        self.app._price_model_put(lines[0], {"item_kind": "variation", "woo_id": 101})
        self.app._price_model_put(lines[1], {"item_kind": "product", "woo_id": 200})
        entries = self.app._price_model_entries()
        writes: list[int] = []

        def preview(_session, _kind, woo_id, _price, **_kwargs):
            if woo_id == 200:
                return {
                    "price_safety": {
                        "status": "ERROR",
                        "messages": ["ERROR: el producto padre variable no tiene precio vendible unico."],
                    }
                }
            return {"price_safety": {"status": "OK", "messages": []}}

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch("futonhub.ui.erp.prototype.preview_real_price_proposal", side_effect=preview),
            patch("futonhub.ui.erp.prototype.create_real_price_proposal", side_effect=lambda *_args, **_kwargs: writes.append(1)),
        ):
            with self.assertRaisesRegex(ValueError, "Validacion de precio bloqueada"):
                self.app._price_validate_and_persist_entries(entries, "Tatamis", "token-1")

        self.assertEqual(writes, [])

    def test_search_results_and_excluded_bulk_rows_do_not_participate_in_save_validation(self) -> None:
        self.app._cloud_session = object()
        self.app._price_search_results = [
            {"code": "200", "type": "Simple", "price": "Pendiente"},
            {"code": "pack-x", "type": "Pack", "price": "Pendiente"},
        ]
        self.app._price_edit_notice = "Errores excluidos: 2"
        lines = [ProposalLine("101", "Tatami 90", "100", "110", "+10%", "up")]
        self.app._price_model_put(lines[0], {"item_kind": "variation", "woo_id": 101})
        entries = self.app._price_model_entries()
        validated_ids: list[int] = []

        def preview(_session, _kind, woo_id, _price, **_kwargs):
            validated_ids.append(woo_id)
            return {"price_safety": {"status": "OK", "messages": []}}

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch("futonhub.ui.erp.prototype.preview_real_price_proposal", side_effect=preview),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                return_value={"proposal": {"id": "id-101", "source_row": {}}},
            ),
        ):
            saved, _counts = self.app._price_validate_and_persist_entries(entries, "Tatamis", "token-1")

        self.assertEqual(validated_ids, [101])
        self.assertEqual(saved, ["id-101"])

    def test_successful_write_persists_group_metadata_in_same_service_call(self) -> None:
        self.app._cloud_session = object()
        line = ProposalLine("101", "Tatami 90", "100", "110", "+10%", "up")
        self.app._price_model_put(line, {"item_kind": "variation", "woo_id": 101})
        entries = self.app._price_model_entries()

        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                return_value={"price_safety": {"status": "OK", "messages": []}},
            ),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                return_value={"proposal": {"id": "id-101", "source_row": {}}},
            ) as create,
        ):
            self.app._price_validate_and_persist_entries(entries, "Tatamis", "token-1")

        updates = create.call_args.kwargs["source_row_updates"]
        self.assertEqual(updates["ui_proposal_name"], "Tatamis")
        self.assertEqual(updates["ui_line_code"], "101")
        self.assertEqual(updates["ui_save_token"], "token-1")

    def test_refresh_failure_is_not_reported_as_save_failure(self) -> None:
        success_source = inspect.getsource(FutonHubErpPrototype._finish_price_edit_saved)
        refresh_source = inspect.getsource(FutonHubErpPrototype._finish_price_proposals_refresh)

        self.assertNotIn("_finish_price_edit_save_error", success_source)
        self.assertIn('self._set_price_mode("saved")', success_source)
        self.assertIn("self._price_error = error", refresh_source)

    def test_save_success_and_error_release_guard_and_overlay(self) -> None:
        success = inspect.getsource(FutonHubErpPrototype._finish_price_edit_saved)
        failure = inspect.getsource(FutonHubErpPrototype._finish_price_edit_save_error)

        for source in (success, failure):
            self.assertIn("self._price_stop_working_overlay(overlay)", source)
            self.assertIn("self._price_save_in_progress = False", source)
        self.assertIn("Items:", success)
        self.assertIn("Suben:", success)
        self.assertIn("Bajan:", success)
        self.assertIn("Sin cambio:", success)

    def test_delete_uses_only_exact_member_ids_and_has_double_click_guard(self) -> None:
        open_source = inspect.getsource(FutonHubErpPrototype._open_delete_price_proposal_confirmation)
        finish_source = inspect.getsource(FutonHubErpPrototype._finish_delete_price_proposal)

        self.assertIn("if self._price_delete_in_progress:", open_source)
        self.assertIn("proposal_ids=member_ids", open_source)
        self.assertIn("Referencia:", open_source)
        self.assertNotIn("mismo nombre", open_source)
        self.assertIn("proposal_ids & deleted_ids", finish_source)
        self.assertNotIn("row_name", finish_source)

    def test_delete_service_never_expands_selection_by_name(self) -> None:
        from futonhub.cloud.services.price_proposals import delete_real_price_proposal_group

        source = inspect.getsource(delete_real_price_proposal_group)
        self.assertIn("requested_ids", source)
        self.assertNotIn("ui_proposal_name\") or \"\").strip() == group_name", source)
        self.assertNotIn(".limit(500)", source)

    def test_price_operations_use_specific_non_overlapping_overlays(self) -> None:
        search = inspect.getsource(FutonHubErpPrototype._refresh_price_edit_items)
        add = inspect.getsource(FutonHubErpPrototype._price_add_rows_to_proposal)
        add_all = inspect.getsource(FutonHubErpPrototype._confirm_price_bulk_add)
        save = inspect.getsource(FutonHubErpPrototype._save_price_edit)
        delete = inspect.getsource(FutonHubErpPrototype._open_delete_price_proposal_confirmation)
        overlay = inspect.getsource(FutonHubErpPrototype._price_start_working_overlay)

        self.assertIn("Buscando articulos, variaciones y packs", search)
        self.assertIn("Anadiendo articulo a la propuesta", add)
        self.assertIn("Procesando", add_all)
        self.assertIn("Validando y registrando los cambios", save)
        self.assertIn("Eliminando propuesta", delete)
        self.assertIn("if current.winfo_exists()", overlay)
        self.assertIn("return None", overlay)

    def test_new_search_clears_previous_contextual_notice_without_global_parent_error(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._refresh_price_edit_items)

        self.assertIn('self._price_edit_notice = ""', source)
        self.assertNotIn("Producto padre sin precio unico", source)
        self.assertNotIn("producto padre", source.lower())

    def test_parent_remains_visible_as_non_publishable_without_search_banner(self) -> None:
        parent = inventory_item(
            "200",
            "Tatami variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        results = self.app._price_results_from_items([parent])
        render_source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["code"], "200")
        self.assertIn("No publicable", render_source)
        self.assertIn('fg=ROSE if eligibility == "ERROR" else MUTED', render_source)

    def test_bulk_preview_uses_short_contextual_parent_reason_and_keeps_valid_variation(self) -> None:
        parent = inventory_item(
            "200",
            "Tatami variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        variation = inventory_item(
            "201",
            "Tatami 90",
            "120",
            raw={"woo_item_kind": "variation", "woo_id": 201, "woo_parent_id": 200, "item_record_type": "woo_variation"},
        )

        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([parent, variation]), "10", "")

        self.assertEqual(preview["rows"][0]["status"], "ERROR")
        self.assertEqual(preview["rows"][0]["reason"], "Producto padre sin precio unico")
        self.assertEqual(preview["rows"][1]["status"], "VALIDO")
        self.assertEqual(preview["counts"]["total_add"], 1)

    def test_successful_individual_add_clears_previous_banner(self) -> None:
        item = inventory_item(
            "201",
            "Tatami 90",
            "120",
            raw={"woo_item_kind": "variation", "woo_id": 201, "woo_parent_id": 200, "item_record_type": "woo_variation"},
        )
        self.app._price_search_results = self.app._price_results_from_items([item])
        self.app._price_edit_notice = "ERROR anterior"
        self.app._show_view = lambda _view: None

        self.app._price_add_rows_to_proposal([("201", "Tatami 90", "120")], "10", "")

        self.assertEqual(self.app._price_edit_notice, "")
        self.assertEqual([line.code for line in self.app._price_edit_lines], ["201"])

    def test_valid_selection_clears_notice_and_pending_rows_never_enter(self) -> None:
        render_source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)
        add_source = inspect.getsource(FutonHubErpPrototype._price_add_rows_to_proposal)

        self.assertIn('if self._price_classify_result(result)[0] == "VALIDO":', render_source)
        self.assertIn('self._price_edit_notice = ""', render_source)
        self.assertIn('if status in {"ERROR", "EXCLUIDO"}:', add_source)
        self.assertLess(add_source.index('if status in {"ERROR", "EXCLUIDO"}:'), add_source.index("self._price_model_put("))

    def test_save_validates_only_current_proposal_lines_not_search_results(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._save_price_edit)

        self.assertIn("model_entries = self._price_canonical_snapshot()", source)
        self.assertIn("entries = tuple(model_entries)", source)
        self.assertNotIn("_price_search_results", source)
        self.assertNotIn("_price_available_items", source)

    def test_inventory_carry_does_not_insert_pending_parent_into_right_panel(self) -> None:
        parent = inventory_item(
            "200",
            "Tatami variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        self.app._price_edit_initialized = False
        self.app._selected_price_proposal = None
        self.app._proposal_source_item = parent

        self.app._prepare_price_edit_state()

        self.assertEqual(self.app._price_edit_lines, [])
        self.assertEqual(self.app._price_edit_notice, "Producto padre sin precio unico")

    def test_stale_empty_refresh_cannot_overwrite_newer_historical_results(self) -> None:
        historical = PriceProposal("Historica", "2025-01-01", 1, 1, 0, 0, "+10%", "Pendiente", ())
        self.app._cloud_session = type("Session", (), {"user_id": "user-1"})()
        self.app._price_refresh_generation = 2
        self.app._price_refresh_diagnostics = []
        self.app._price_proposals = [historical]
        self.app._price_loading = True
        self.app._current_key = "precios"
        self.app._price_mode = "saved"
        self.app._show_view = lambda _view: None

        self.app._finish_price_proposals_refresh(
            [],
            "No hay propuestas reales visibles.",
            generation=1,
            source="inicial",
            received_rows=0,
        )

        self.assertEqual(self.app._price_proposals, [historical])
        self.assertEqual(self.app._price_refresh_diagnostics[-1]["result"], "descartado_obsoleto")

    def test_overlapping_manual_and_automatic_refresh_only_applies_latest_generation(self) -> None:
        old = PriceProposal("Antigua", "2025-01-01", 1, 0, 0, 1, "0", "Pendiente", ())
        new = PriceProposal("Nueva", "2026-01-01", 1, 1, 0, 0, "+10", "Pendiente", ())
        self.app._cloud_session = type("Session", (), {"user_id": "user-1"})()
        self.app._price_refresh_generation = 4
        self.app._price_refresh_diagnostics = []
        self.app._price_proposals = [old]
        self.app._price_loading = True
        self.app._price_loaded_once = False
        self.app._price_refresh_preferred_token = ""
        self.app._selected_price_proposal = old
        self.app._current_key = "precios"
        self.app._price_mode = "saved"
        self.app._show_view = lambda _view: None

        self.app._finish_price_proposals_refresh([old], "", generation=3, source="automatico", received_rows=1)
        self.app._finish_price_proposals_refresh([new], "", generation=4, source="manual", received_rows=1)

        self.assertEqual(self.app._price_proposals, [new])
        self.assertEqual([entry["result"] for entry in self.app._price_refresh_diagnostics[-2:]], ["descartado_obsoleto", "aplicado"])

    def test_refresh_callback_from_previous_view_is_discarded(self) -> None:
        current = PriceProposal("Actual", "2026-01-01", 1, 1, 0, 0, "+10", "Pendiente", ())
        self.app._cloud_session = type("Session", (), {"user_id": "user-1"})()
        self.app._price_refresh_generation = 1
        self.app._price_refresh_diagnostics = []
        self.app._price_proposals = [current]
        self.app._price_loading = True
        self.app._current_key = "inventario"
        self.app._price_mode = "saved"

        self.app._finish_price_proposals_refresh([], "", generation=1, source="inicial", received_rows=0)

        self.assertEqual(self.app._price_proposals, [current])
        self.assertEqual(self.app._price_refresh_diagnostics[-1]["result"], "descartado_vista_inactiva")

    def test_current_authenticated_zero_result_applies_empty_state(self) -> None:
        current = PriceProposal("Actual", "2026-01-01", 1, 1, 0, 0, "+10", "Pendiente", ())
        self.app._cloud_session = type("Session", (), {"user_id": "user-1"})()
        self.app._price_refresh_generation = 1
        self.app._price_refresh_diagnostics = []
        self.app._price_proposals = [current]
        self.app._price_loading = True
        self.app._price_loaded_once = False
        self.app._price_refresh_preferred_token = ""
        self.app._selected_price_proposal = current
        self.app._current_key = "precios"
        self.app._price_mode = "saved"
        self.app._show_view = lambda _view: None

        self.app._finish_price_proposals_refresh(
            [],
            "No hay propuestas reales visibles.",
            generation=1,
            source="manual",
            received_rows=0,
        )

        self.assertEqual(self.app._price_proposals, [])
        self.assertIsNone(self.app._selected_price_proposal)
        self.assertEqual(self.app._price_refresh_diagnostics[-1]["result"], "aplicado")

    def test_unverified_empty_result_does_not_erase_cached_history(self) -> None:
        historical = PriceProposal("Historica", "2025-01-01", 1, 1, 0, 0, "+10", "Pendiente", ())
        self.app._cloud_session = object()
        self.app._price_refresh_generation = 1
        self.app._price_refresh_diagnostics = []
        self.app._price_proposals = [historical]
        self.app._price_loading = True
        self.app._current_key = "precios"
        self.app._price_mode = "saved"
        self.app._show_view = lambda _view: None

        self.app._finish_price_proposals_refresh([], "", generation=1, source="inicial", received_rows=0)

        self.assertEqual(self.app._price_proposals, [historical])
        self.assertEqual(self.app._price_refresh_diagnostics[-1]["result"], "descartado_vacio_no_autorizado")

    def test_all_refresh_origins_use_same_loader_and_generation(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._refresh_price_proposals)
        build_source = inspect.getsource(FutonHubErpPrototype._build_prices)
        workspace_source = inspect.getsource(FutonHubErpPrototype._build_saved_proposals_workspace)
        delete_source = inspect.getsource(FutonHubErpPrototype._finish_delete_price_proposal)
        save_source = inspect.getsource(FutonHubErpPrototype._finish_price_edit_saved)

        self.assertIn("self._price_refresh_generation += 1", source)
        self.assertEqual(source.count("diagnose_real_price_proposals("), 1)
        self.assertIn('source="manual"', workspace_source)
        self.assertIn('"borrado"', delete_source)
        self.assertIn('"guardado"', save_source)
        self.assertIn('"inicial"', build_source)

    def test_failed_non_publishable_add_leaves_no_hidden_proposal_source(self) -> None:
        parent = inventory_item(
            "200",
            "Padre variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        self.app._price_search_results = self.app._price_results_from_items([parent])
        self.app._show_view = lambda _view: None

        with patch("futonhub.ui.erp.prototype.messagebox.showerror"):
            self.app._price_add_rows_to_proposal([("200", "Padre variable", "Pendiente")], "10", "")

        self.assertEqual(self.app._price_edit_lines, [])
        self.assertEqual(self.app._price_proposal_line_sources, {})

    def test_failed_add_then_bulk_validations_use_only_visible_variations(self) -> None:
        parent = inventory_item(
            "200",
            "Padre variable",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 200, "type": "variable", "item_record_type": "simple"},
        )
        variation = inventory_item(
            "201",
            "Tatami 90",
            "120",
            raw={"woo_item_kind": "variation", "woo_id": 201, "woo_parent_id": 200, "item_record_type": "woo_variation"},
        )
        self.app._price_search_results = self.app._price_results_from_items([parent])
        self.app._show_view = lambda _view: None
        with patch("futonhub.ui.erp.prototype.messagebox.showerror"):
            self.app._price_add_rows_to_proposal([("200", "Padre variable", "Pendiente")], "10", "")

        results = self.app._price_results_from_items([parent, variation])
        preview = self.app._price_build_bulk_preview(results, "10", "")

        class Window:
            def grab_release(self):
                return None

            def destroy(self):
                return None

        with patch("futonhub.ui.erp.prototype.messagebox.showinfo"):
            self.app._confirm_price_bulk_add(Window(), preview)

        validated: list[int] = []
        self.app._cloud_session = object()
        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                side_effect=lambda _session, _kind, woo_id, _price, **_kwargs: (
                    validated.append(woo_id) or {"price_safety": {"status": "OK", "messages": []}}
                ),
            ),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                return_value={"proposal": {"id": "id-201"}},
            ),
        ):
            entries = self.app._price_model_entries()
            self.app._price_validate_and_persist_entries(entries, "Tatamis", "token")

        self.assertEqual([line.code for line in self.app._price_edit_lines], ["201"])
        self.assertEqual(set(self.app._price_proposal_line_sources), {"201"})
        self.assertEqual(validated, [201])

    def test_validator_ids_match_visible_panel_ids_exactly(self) -> None:
        self.app._cloud_session = object()
        lines = [
            ProposalLine("201", "Tatami 90", "120", "132", "+10%", "up"),
            ProposalLine("202", "Tatami 140", "150", "165", "+10%", "up"),
        ]
        self.app._price_model_put(lines[0], {"item_kind": "variation", "woo_id": 201})
        self.app._price_model_put(lines[1], {"item_kind": "variation", "woo_id": 202})
        self.app._price_sync_legacy_model_views()
        entries = self.app._price_model_entries()
        validated: list[int] = []
        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=object()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                side_effect=lambda _session, _kind, woo_id, _price, **_kwargs: (
                    validated.append(woo_id) or {"price_safety": {"status": "OK", "messages": []}}
                ),
            ),
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                side_effect=lambda _session, _kind, woo_id, _price, **_kwargs: {"proposal": {"id": f"id-{woo_id}"}},
            ),
        ):
            self.app._price_validate_and_persist_entries(entries, "Tatamis", "token")

        self.assertEqual(validated, [201, 202])
        self.assertEqual(len(validated), len(self.app._price_edit_lines))

    def test_authoritative_history_diagnostic_reports_raw_filtered_and_reasons(self) -> None:
        session = Session({
            "price_change_proposals": [
                {"id": "visible", "status": "pending", "source_row": {}},
                {"id": "test", "status": "pending", "source_row": {"test": True}},
                {"id": "deleted", "status": "rejected", "source_row": {"ui_deleted": True}},
            ]
        })

        diagnostic = diagnose_real_price_proposals(session, status="all", limit=200)

        self.assertEqual(diagnostic["raw_count"], 3)
        self.assertEqual(diagnostic["filtered_count"], 1)
        self.assertEqual([row["id"] for row in diagnostic["rows"]], ["visible"])
        self.assertEqual(diagnostic["discarded"], [
            {"id": "test", "reason": "test"},
            {"id": "deleted", "reason": "ui_deleted"},
        ])

    def test_ui_deleted_normalization_only_accepts_explicit_true(self) -> None:
        visible_values = [
            {},
            {"ui_deleted": None},
            {"ui_deleted": False},
            {"ui_deleted": 0},
            {"ui_deleted": ""},
            {"ui_deleted": "false"},
        ]
        deleted_values = [
            {"ui_deleted": True},
            {"ui_deleted": 1},
            {"ui_deleted": "true"},
        ]

        for source in visible_values:
            self.assertFalse(_is_ui_deleted({"source_row": source}), source)
        for source in deleted_values:
            self.assertTrue(_is_ui_deleted({"source_row": source}), source)

    def test_ui_deleted_diagnostic_counts_200_mixed_formats_exactly(self) -> None:
        sources = (
            [{}] * 20
            + [{"ui_deleted": None}] * 20
            + [{"ui_deleted": False}] * 20
            + [{"ui_deleted": True}] * 20
            + [{"ui_deleted": 0}] * 20
            + [{"ui_deleted": 1}] * 20
            + [{"ui_deleted": ""}] * 20
            + [{"ui_deleted": "false"}] * 20
            + [{"ui_deleted": "true"}] * 20
            + [{"ui_deleted": "legacy"}] * 20
        )
        rows = [
            {"id": str(index), "status": "pending", "source_row": source}
            for index, source in enumerate(sources)
        ]

        diagnostic = diagnose_real_price_proposals(
            Session({"price_change_proposals": rows}),
            status="all",
            limit=200,
        )

        self.assertEqual(diagnostic["raw_count"], 200)
        self.assertEqual(diagnostic["filtered_count"], 140)
        self.assertEqual(len(diagnostic["discarded"]), 60)
        self.assertEqual(diagnostic["ui_deleted_distribution"], {
            "absent": 20,
            "bool_false": 20,
            "bool_true": 20,
            "null": 20,
            "number_0": 20,
            "number_1": 20,
            "string_empty": 20,
            "string_false": 20,
            "string_other": 20,
            "string_true": 20,
        })

    def test_real_true_deletion_pattern_is_diagnostic_only(self) -> None:
        rows = [
            {
                "id": str(index),
                "status": "rejected",
                "source_row": {
                    "ui_deleted": True,
                    "ui_deleted_at": "2026-06-22T10:00:00+00:00",
                    "ui_deleted_by_email": "admin@example.invalid",
                    "ui_delete_operation_id": "PRICEDEL-ONE",
                },
            }
            for index in range(200)
        ]

        diagnostic = diagnose_real_price_proposals(
            Session({"price_change_proposals": rows}),
            status="all",
            limit=200,
        )

        self.assertEqual(diagnostic["filtered_count"], 0)
        self.assertEqual(diagnostic["ui_deleted_distribution"], {"bool_true": 200})
        self.assertEqual(diagnostic["deletion_patterns"][0]["count"], 200)
        self.assertEqual(diagnostic["deletion_patterns"][0]["operation_id"], "PRICEDEL-ONE")
        self.assertTrue(diagnostic["deletion_patterns"][0]["actor_ref"].startswith("actor:"))
        self.assertEqual(rows[0]["source_row"]["ui_deleted"], True)

    def test_soft_delete_analysis_groups_operations_and_detects_overreach(self) -> None:
        rows = [
            {
                "id": f"id-{index}",
                "created_at": "2025-01-01T10:00:00+00:00",
                "status": "rejected",
                "item_kind": "variation",
                "source_row": {
                    "ui_deleted": True,
                    "ui_deleted_at": "2026-06-22T12:46:18+00:00",
                    "ui_delete_operation_id": "PRICEDEL-MULTI",
                    "ui_save_token": "token-a" if index < 2 else "token-b",
                    "ui_proposal_name": "Historica A" if index < 2 else "Historica B",
                },
            }
            for index in range(4)
        ]
        audit_rows = [{
            "operation_id": "PRICEDEL-MULTI",
            "before_data": [{"id": "id-0"}, {"id": "id-1"}],
        }]

        analysis = analyze_price_proposal_soft_deletes(rows, audit_rows, [])

        self.assertEqual(analysis[0]["logical_count"], 2)
        self.assertFalse(analysis[0]["affected_ids_match_requested"])
        self.assertEqual(
            analysis[0]["classification"],
            "varias_propuestas_por_error",
        )
        self.assertEqual(analysis[0]["item_kinds"], {"variation": 4})

    def test_restore_plan_is_reversible_and_performs_no_writes(self) -> None:
        analysis = [{
            "operation_id": "PRICEDEL-ONE",
            "row_count": 35,
            "logical_groups": [{"identity": "ui_save_token:token-a"}],
            "classification": "borrado_correcto_una_propuesta",
        }]

        plan = build_price_proposal_restore_plan(analysis)

        self.assertFalse(plan["write_performed"])
        self.assertEqual(
            plan["selectors"],
            ["price_delete_operation_id", "logical_token", "exact_ids"],
        )
        self.assertTrue(any("snapshot" in step for step in plan["steps"]))
        self.assertTrue(any("rollback" in step for step in plan["steps"]))

    def test_confirmed_four_price_delete_operations_group_to_200_rows(self) -> None:
        operation_counts = {
            "PRICEDEL-20260622-122910-EA4E5159": 35,
            "PRICEDEL-20260622-124618-1223F549": 82,
            "PRICEDEL-20260622-125410-5DA0B4A4": 82,
            "PRICEDEL-20260622-125646-AB215A8A": 1,
        }
        rows = []
        for operation_id, count in operation_counts.items():
            rows.extend({
                "id": f"{operation_id}-{index}",
                "created_at": "2025-01-01T00:00:00+00:00",
                "status": "rejected",
                "item_kind": "variation",
                "source_row": {
                    "ui_deleted": True,
                    "ui_deleted_at": "2026-06-22T12:00:00+00:00",
                    "ui_delete_operation_id": operation_id,
                    "ui_save_token": f"{operation_id}-token",
                    "ui_proposal_name": "Historica",
                },
            } for index in range(count))

        analysis = analyze_price_proposal_soft_deletes(rows)

        self.assertEqual(
            {row["operation_id"]: row["row_count"] for row in analysis},
            operation_counts,
        )
        self.assertEqual(sum(row["row_count"] for row in analysis), 200)

    def test_authenticated_initial_workspace_does_not_render_cached_proposals(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._build_saved_proposals_workspace)

        self.assertIn("source_proposals = self._price_proposals if self._price_loaded_once else []", source)
        self.assertNotIn(
            "self._price_proposals if (self._cloud_session is not None and self._price_loaded_once)",
            source,
        )

    def test_refresh_diagnostic_contains_safe_authoritative_counts(self) -> None:
        self.app._cloud_session = type("Session", (), {"user_id": "user", "role": "worker"})()
        self.app._price_proposals = []
        self.app._price_refresh_diagnostics = []

        with patch("builtins.print") as output:
            self.app._price_record_refresh_diagnostic(
                "manual",
                4,
                12,
                "aplicado",
                filtered_rows=10,
                groups=7,
                discarded=[{"id": "x", "reason": "test"}],
                repository="price_change_proposals",
            )

        diagnostic = self.app._price_refresh_diagnostics[-1]
        self.assertEqual(diagnostic["rows"], 12)
        self.assertEqual(diagnostic["filtered_rows"], 10)
        self.assertEqual(diagnostic["groups"], 7)
        self.assertTrue(diagnostic["authenticated_user"])
        self.assertTrue(diagnostic["role_known"])
        self.assertNotIn("token", diagnostic)
        output.assert_not_called()

    def test_initial_manual_and_automatic_refreshes_do_not_print_diagnostics(self) -> None:
        self.app._cloud_session = type("Session", (), {"user_id": "user", "role": "admin"})()
        self.app._price_proposals = []
        self.app._price_refresh_diagnostics = []

        with patch("builtins.print") as output:
            for generation, origin in enumerate(("inicial", "manual", "automatico"), start=1):
                self.app._price_record_refresh_diagnostic(origin, generation, 0, "aplicado")

        output.assert_not_called()

    def test_ui_deleted_distribution_is_retained_without_normal_output(self) -> None:
        self.app._cloud_session = type("Session", (), {"user_id": "user", "role": "admin"})()
        self.app._price_proposals = []
        self.app._price_refresh_diagnostics = []

        with patch("builtins.print") as output:
            self.app._price_record_refresh_diagnostic(
                "manual",
                4,
                200,
                "aplicado",
                filtered_rows=0,
                discarded=[
                    {"id": str(index), "reason": "ui_deleted"}
                    for index in range(200)
                ],
                ui_deleted_distribution={"bool_true": 200},
                deletion_patterns=[{
                    "deleted_at": "2026-06-22T10:00:00+00:00",
                    "operation_id": "PRICEDEL-ONE",
                    "actor_ref": "actor:0123456789",
                    "count": 200,
                }],
            )

        output.assert_not_called()
        diagnostic = self.app._price_refresh_diagnostics[-1]
        self.assertEqual(diagnostic["ui_deleted_distribution"], {"bool_true": 200})
        self.assertEqual(
            diagnostic["deletion_patterns"][0]["operation_id"],
            "PRICEDEL-ONE",
        )

    def test_refresh_query_error_prints_one_compact_safe_line(self) -> None:
        self.app._cloud_session = type("Session", (), {"user_id": "user", "role": "admin"})()
        self.app._price_proposals = []
        self.app._price_refresh_diagnostics = []

        with patch("builtins.print") as output:
            self.app._price_record_refresh_diagnostic(
                "manual",
                4,
                0,
                "consulta_error",
                query_ok=False,
                error_type="RuntimeError",
            )

        output.assert_called_once()
        rendered = output.call_args.args[0]
        self.assertIn("[PRICE_PROPOSALS]", rendered)
        self.assertIn("query=error", rendered)
        self.assertNotIn("token", rendered.lower())
        self.assertNotIn("http", rendered.lower())

    def test_session_absent_empty_query_and_query_error_are_distinct(self) -> None:
        self.app._price_proposals = []
        self.app._price_refresh_diagnostics = []

        with patch("builtins.print"):
            self.app._cloud_session = None
            self.app._price_record_refresh_diagnostic(
                "inicial", 1, 0, "sesion_ausente", query_ok=None
            )
            self.app._cloud_session = type("Session", (), {"user_id": "user"})()
            self.app._price_record_refresh_diagnostic(
                "manual", 2, 0, "aplicado", filtered_rows=0, query_ok=True
            )
            self.app._price_record_refresh_diagnostic(
                "automatico", 3, 0, "consulta_error", query_ok=False
            )

        states = self.app._price_refresh_diagnostics
        self.assertEqual(
            [(row["result"], row["query"]) for row in states],
            [
                ("sesion_ausente", "skipped"),
                ("aplicado", "ok"),
                ("consulta_error", "error"),
            ],
        )

    def test_save_has_no_legacy_reconstruction_path(self) -> None:
        save_source = inspect.getsource(FutonHubErpPrototype._save_price_edit)
        validate_source = inspect.getsource(FutonHubErpPrototype._price_validate_and_persist_entries)
        entries_source = inspect.getsource(FutonHubErpPrototype._price_model_entries)

        self.assertFalse(hasattr(FutonHubErpPrototype, "_price_validate_and_persist_lines"))
        for source in (save_source, validate_source, entries_source):
            self.assertNotIn("_price_edit_lines", source)
            self.assertNotIn("_price_line_sources", source)
            self.assertNotIn("_price_proposal_line_sources", source)
            self.assertNotIn("_price_search_results", source)

    def test_line_without_reliable_canonical_identity_is_rejected_before_model(self) -> None:
        line = ProposalLine("VISIBLE-ONLY", "Sin Woo", "10", "11", "+10%", "up")

        with self.assertRaisesRegex(ValueError, "identidad Woo canonica fiable"):
            self.app._price_model_put(line, {"item_kind": "variation"})

        self.assertEqual(self.app._price_model_entries(), ())

    def test_bulk_84_valid_and_10_rejected_only_populates_canonical_model_with_84(self) -> None:
        valid = [
            inventory_item(
                str(1000 + index),
                f"Variacion {index}",
                "100",
                raw={"woo_item_kind": "variation", "woo_id": 1000 + index, "woo_parent_id": 99, "item_record_type": "woo_variation"},
            )
            for index in range(84)
        ]
        rejected = [
            inventory_item(
                str(2000 + index),
                f"Padre {index}",
                "Pendiente",
                raw={"woo_item_kind": "product", "woo_id": 2000 + index, "type": "variable", "item_record_type": "simple"},
            )
            for index in range(10)
        ]
        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([*valid, *rejected]), "10", "")

        class Window:
            def grab_release(self):
                return None

            def destroy(self):
                return None

        self.app._show_view = lambda _view: None
        with patch("futonhub.ui.erp.prototype.messagebox.showinfo"):
            self.app._confirm_price_bulk_add(Window(), preview)

        self.assertEqual(len(preview["accepted_lines"]), 84)
        self.assertEqual(len(preview["rejected_lines"]), 10)
        self.assertEqual(len(self.app._price_model_entries()), 84)
        self.assertEqual(len(self.app._price_edit_lines), 84)
        self.assertEqual(len(self.app._price_proposal_line_sources), 84)

    def test_specific_rejected_parent_930000010533_never_enters_model_or_validator(self) -> None:
        parent = inventory_item(
            "930000010533",
            "UNICA UNIDAD - 2 Tatamis de 90 Futon Duo",
            "Pendiente",
            raw={"woo_item_kind": "product", "woo_id": 930000010533, "type": "variable", "item_record_type": "simple"},
        )
        variation = inventory_item(
            "930000010533",
            "Variacion valida",
            "120",
            raw={"woo_item_kind": "variation", "woo_id": 10533, "woo_parent_id": 930000010533, "item_record_type": "woo_variation"},
        )
        preview = self.app._price_build_bulk_preview(self.app._price_results_from_items([parent, variation]), "10", "")

        self.assertEqual(preview["rejected_lines"][0]["source"]["item_kind"], "product")
        self.assertEqual(preview["accepted_lines"][0]["source"]["item_kind"], "variation")
        self.assertEqual(self.app._price_model_target_state(preview["rejected_lines"]), "ERROR")
        self.assertEqual(self.app._price_model_target_state(preview["accepted_lines"]), "absent")

        class Window:
            def grab_release(self):
                return None

            def destroy(self):
                return None

        self.app._show_view = lambda _view: None
        with patch("futonhub.ui.erp.prototype.messagebox.showinfo"):
            self.app._confirm_price_bulk_add(Window(), preview)

        entries = self.app._price_model_entries()
        self.assertEqual([entry["key"] for entry in entries], ["variation:10533"])
        self.assertNotIn("product:930000010533", self.app._price_proposal_model)
        self.assertEqual(self.app._price_model_target_state(entries), "absent")

    def test_temporary_model_and_delete_diagnostics_are_removed(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype)

        self.assertNotIn("[PRICE_MODEL]", source)
        self.assertNotIn("[PRICE_DELETE_AUDIT]", source)
        self.assertNotIn("[PRICE_UI_DELETED]", source)
        self.assertNotIn("_price_print_model_diagnostic", source)
        self.assertNotIn("_price_print_delete_analysis", source)

    def test_integrity_mismatch_blocks_before_any_write(self) -> None:
        line = ProposalLine("201", "Tatami", "100", "110", "+10%", "up")
        self.app._price_model_put(line, {"item_kind": "variation", "woo_id": 201})
        snapshot = self.app._price_model_entries()
        self.app._price_model_put(
            ProposalLine("202", "Otra", "100", "110", "+10%", "up"),
            {"item_kind": "variation", "woo_id": 202},
        )
        writes: list[int] = []

        with patch("futonhub.ui.erp.prototype.create_real_price_proposal", side_effect=lambda *_args, **_kwargs: writes.append(1)):
            with self.assertRaisesRegex(ValueError, "integridad"):
                self.app._price_validate_and_persist_entries(snapshot, "Tatamis", "token")

        self.assertEqual(writes, [])

    def test_bulk_overlay_closes_before_summary_popup(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._confirm_price_bulk_add)

        self.assertLess(source.index("win.destroy()"), source.index("_price_start_working_overlay"))
        self.assertLess(source.index("_price_stop_working_overlay"), source.index("messagebox.showinfo"))
        self.assertLess(source.index('self._show_view("precios")'), source.index("_price_stop_working_overlay"))

    def test_unified_table_uses_blue_buttons_bordered_entries_and_all_results(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)

        self.assertIn('relief=tk.SOLID', source)
        self.assertIn('"Anadir", primary=True', source)
        self.assertIn('"Anadir todos"', source)
        self.assertIn("results, percent_entry.get(), exact_entry.get()", source)
        self.assertIn("state=tk.NORMAL if self._price_search_query.strip() and results else tk.DISABLED", source)

    def test_proposal_detail_places_actions_below_component_text(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._proposal_edit_line)

        self.assertIn('actions.grid(row=1, column=0', source)
        self.assertIn('text=self._price_line_display_name(line.name)', source)

    def test_equivalent_numeric_searches_return_same_unique_stable_set(self) -> None:
        data = {
            "v_inventory_hub_search_ranked": [
                {
                    "search_token_norm": "0201001",
                    "result_item_id": 900000003721,
                    "result_item_code": "WOO-PACK-3721",
                    "result_name": "Pack Woo 3721",
                    "result_record_type": "woo_pack",
                    "match_priority": 2,
                },
                {
                    "search_token_norm": "0201001",
                    "result_item_id": 201001,
                    "result_item_code": "0201001",
                    "result_name": "Tatami 80",
                    "result_record_type": "simple",
                    "match_priority": 1,
                },
                {
                    "search_token_norm": "201001",
                    "result_item_id": 201001,
                    "result_item_code": "0201001",
                    "result_name": "Tatami 80",
                    "result_record_type": "simple",
                    "match_priority": 1,
                },
            ],
            "inventory_items": [
                {
                    "item_id": 900000003721,
                    "name": "Pack Woo 3721",
                    "item_record_type": "woo_pack",
                    "hub_item_code": "WOO-PACK-3721",
                    "woo_sku": "0201001|0728001",
                },
                {
                    "item_id": 201001,
                    "name": "Tatami 80",
                    "item_record_type": "simple",
                    "hub_item_code": "0201001",
                    "woo_sku": "0201001",
                },
                {
                    "item_id": 900000003720,
                    "name": "Pack Woo 3720",
                    "item_record_type": "woo_pack",
                    "hub_item_code": "WOO-PACK-3720",
                    "woo_sku": "0201001|0201001|0728003",
                },
            ],
            "inventory_item_components": [],
        }

        with_zero = search_cloud_inventory_items(Session(data), "0201001", limit=10)
        without_zero = search_cloud_inventory_items(Session(data), "201001", limit=10)
        ids_with_zero = [row["item_id"] for row in with_zero]
        ids_without_zero = [row["item_id"] for row in without_zero]

        self.assertEqual(set(ids_with_zero), set(ids_without_zero))
        self.assertEqual(len(ids_with_zero), len(ids_without_zero))
        self.assertEqual(len(ids_with_zero), len(set(ids_with_zero)))
        self.assertEqual(ids_with_zero, ids_without_zero)
        self.assertEqual(ids_with_zero, [201001, 900000003720, 900000003721])

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

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services import inventory  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402


class Response:
    def __init__(self, data=None) -> None:
        self.data = data or []


class Query:
    def __init__(self, table_name: str, data_by_table: dict[str, list[dict] | Exception]) -> None:
        self.table_name = table_name
        self.data_by_table = data_by_table

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        result = self.data_by_table.get(self.table_name, [])
        if isinstance(result, Exception):
            raise result
        return Response(result)


class Client:
    def __init__(self, data_by_table: dict[str, list[dict] | Exception]) -> None:
        self.data_by_table = data_by_table

    def table(self, table_name: str) -> Query:
        return Query(table_name, self.data_by_table)


class Session:
    def __init__(self, data_by_table: dict[str, list[dict] | Exception]) -> None:
        self.client = Client(data_by_table)


class PackComponentServiceTests(unittest.TestCase):
    def test_fetch_pack_components_uses_live_component_view_and_deduplicates_rows(self) -> None:
        session = Session(
            {
                "v_inventory_component_search": [
                    {
                        "relation_id": "rel-1",
                        "parent_item_code": "WOO-PACK-1",
                        "component_item_code": "0201014",
                        "component_name": "Futon algodon",
                        "quantity": 1,
                        "relation_type": "component",
                        "token_type": "component_code",
                    },
                    {
                        "relation_id": "rel-1",
                        "parent_item_code": "WOO-PACK-1",
                        "component_item_code": "0201014",
                        "component_name": "Futon algodon duplicado",
                        "quantity": 1,
                        "relation_type": "component",
                        "token_type": "component_code",
                    },
                    {
                        "relation_id": "rel-2",
                        "parent_item_code": "WOO-PACK-1",
                        "component_item_code": "0302001",
                        "component_name": "Tatami",
                        "quantity": 2,
                        "relation_type": "component",
                        "token_type": "component_code",
                    },
                ]
            }
        )

        result = inventory.fetch_inventory_pack_components(session, "WOO-PACK-1")

        self.assertEqual(result["source"], "v_inventory_component_search")
        self.assertEqual([row["component_item_code"] for row in result["components"]], ["0201014", "0302001"])
        self.assertIn("0201014 x1 \u00b7 Futon algodon", result["text"])
        self.assertIn("0302001 x2 \u00b7 Tatami", result["text"])

    def test_fetch_pack_components_falls_back_to_relation_table_and_name_resolver(self) -> None:
        session = Session(
            {
                "v_inventory_component_search": RuntimeError("view missing"),
                "inventory_item_components": [
                    {
                        "parent_item_code": "WOO-PACK-2",
                        "component_item_code": "0201014",
                        "component_name": "",
                        "quantity": 1,
                        "relation_type": "component",
                    }
                ],
            }
        )

        def fill_names(_session, components):
            enriched = [dict(row) for row in components]
            enriched[0]["component_name"] = "Futon algodon resuelto"
            return enriched

        with patch.object(inventory, "_fill_component_names_from_inventory", side_effect=fill_names):
            result = inventory.fetch_inventory_pack_components(session, "WOO-PACK-2")

        self.assertEqual(result["source"], "inventory_item_components_fallback")
        self.assertIn("v_inventory_component_search: view missing", result["lookup_error"])
        self.assertEqual(result["components"][0]["component_name"], "Futon algodon resuelto")
        self.assertEqual(result["text"], "0201014 x1 \u00b7 Futon algodon resuelto")

    def test_fetch_pack_components_falls_back_to_compound_woo_sku_tokens(self) -> None:
        session = Session(
            {
                "v_inventory_component_search": [],
                "inventory_item_components": [],
            }
        )

        result = inventory.fetch_inventory_pack_components(
            session,
            "WOO-PACK-3",
            woo_sku="0201014|0302001|0201014",
        )

        self.assertEqual(result["source"], "woo_sku_fallback")
        self.assertEqual(result["components"], [])
        self.assertEqual(result["text"], "0201014 x2; 0302001 x1")
        self.assertEqual(result["multiline"], "- 0201014 x2\n- 0302001 x1")


class PackComponentUiHelperTests(unittest.TestCase):
    def test_inventory_pack_contents_text_uses_cached_text_before_sku_fallback(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        item = InventoryItem(
            code="WOO-PACK-1",
            name="Pack Woo",
            price="-",
            stock="-",
            status="Info",
            family="Packs",
            provider="-",
            m3="-",
            sku_woo="0201014|0302001",
            measures="-",
            material="-",
            sync_woo="-",
            notes="-",
            raw={
                "hub_pack_components_text": "0201014 x1 - Futon",
                "hub_pack_components_multiline": "- 0201014 x1 - Futon",
            },
        )

        self.assertEqual(app._inventory_pack_contents_text(item), "0201014 x1 - Futon")
        self.assertEqual(app._inventory_pack_contents_text(item, multiline=True), "- 0201014 x1 - Futon")

    def test_inventory_pack_contents_text_falls_back_to_compound_sku(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        item = InventoryItem(
            code="WOO-PACK-1",
            name="Pack Woo",
            price="-",
            stock="-",
            status="Info",
            family="Packs",
            provider="-",
            m3="-",
            sku_woo="0201014|0302001|0201014",
            measures="-",
            material="-",
            sync_woo="-",
            notes="-",
            raw={},
        )

        self.assertEqual(app._inventory_pack_contents_text(item), "0201014 x2; 0302001 x1")
        self.assertEqual(app._inventory_pack_contents_text(item, multiline=True), "- 0201014 x2\n- 0302001 x1")


if __name__ == "__main__":
    unittest.main()

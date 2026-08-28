from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.price_proposals import (  # noqa: E402
    create_real_price_proposal,
    diagnose_real_price_proposals,
    list_real_price_proposals,
)
from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_catalog_reconciliation import (  # noqa: E402
    operational_price_catalogue_rows,
    price_proposal_selectable_catalogue_rows,
)
from futonhub.services.price_woo_catalog_index import approved_local_combination_link_identity  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402


class HistoryQuery:
    def __init__(self, table_name: str, rows_by_table: dict[str, list[dict]]) -> None:
        self.table_name = table_name
        self.rows_by_table = rows_by_table
        self.filters: list[tuple[str, object]] = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_value: int | None = None
        self.range_value: tuple[int, int] | None = None
        self.mode = "select"
        self.payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column: str, value: object):
        self.filters.append((column, value))
        return self

    def in_(self, _column: str, _values):
        return self

    def order(self, column: str, desc: bool = False, **_kwargs):
        self.orders.append((column, bool(desc)))
        return self

    def limit(self, value: int, **_kwargs):
        self.limit_value = int(value)
        return self

    def range(self, start: int, end: int):
        self.range_value = (int(start), int(end))
        return self

    def insert(self, payload: dict):
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload: dict):
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def execute(self):
        source_rows = self.rows_by_table.setdefault(self.table_name, [])
        rows = [dict(row) for row in source_rows]
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.mode == "insert":
            row = {"id": f"proposal-{len(source_rows) + 1:03d}", **(self.payload or {})}
            source_rows.append(row)
            return SimpleNamespace(data=[dict(row)])
        if self.mode == "update":
            updated: list[dict] = []
            for row in source_rows:
                if all(row.get(column) == value for column, value in self.filters):
                    row.update(self.payload or {})
                    updated.append(dict(row))
            return SimpleNamespace(data=updated)
        for column, desc in reversed(self.orders):
            rows.sort(key=lambda row: str(row.get(column) or ""), reverse=desc)
        if self.range_value is not None:
            start, end = self.range_value
            rows = rows[start:end + 1]
        elif self.limit_value is not None:
            rows = rows[:self.limit_value]
        return SimpleNamespace(data=rows)


class HistoryClient:
    def __init__(self, rows_by_table: dict[str, list[dict]]) -> None:
        self.rows_by_table = rows_by_table

    def table(self, table_name: str) -> HistoryQuery:
        return HistoryQuery(table_name, self.rows_by_table)


class HistorySession:
    def __init__(self, proposal_rows: list[dict], product_rows: list[dict] | None = None) -> None:
        self.client = HistoryClient({
            "price_change_proposals": proposal_rows,
            "products": product_rows or [],
            "product_variations": [],
            "audit_logs": [],
            "operation_snapshots": [],
        })
        self.role = "worker"
        self.user_id = "worker-1"
        self.email = "worker1@example.invalid"


def inventory_item(code: str, name: str, raw: dict) -> InventoryItem:
    return InventoryItem(
        code=code,
        name=name,
        price="100.00",
        stock="-",
        status="Activo",
        family=str(raw.get("family") or "-"),
        provider="-",
        m3="-",
        sku_woo=str(raw.get("woo_sku") or "-"),
        measures=str(raw.get("size") or "-"),
        material="-",
        sync_woo="-",
        notes="-",
        raw=raw,
    )


class MaintenancePriceProposals003Tests(unittest.TestCase):
    def test_impact_only_plegable_rows_are_not_main_proposal_selectable(self) -> None:
        rows = [
            {"item_id": "201011", "physical_item_id": "201011", "hub_item_code": "0201011"},
            {"item_id": "208001", "physical_item_id": "208001", "hub_item_code": "0208001"},
            {"item_id": "216001", "physical_item_id": "216001", "hub_item_code": "0216001"},
            {"item_id": "402014", "physical_item_id": "402014", "commercial_status": "Descatalogado"},
        ]

        operational_ids = {row["item_id"] for row in operational_price_catalogue_rows(rows)}
        selectable_ids = {row["item_id"] for row in price_proposal_selectable_catalogue_rows(rows)}

        self.assertTrue({"201011", "208001", "216001"}.issubset(operational_ids))
        self.assertIn("201011", selectable_ids)
        self.assertNotIn("208001", selectable_ids)
        self.assertNotIn("216001", selectable_ids)
        self.assertNotIn("402014", selectable_ids)

    def test_prototype_picker_filters_search_source_to_selectable_rows(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        items = [
            inventory_item("0201011", "Tatami Plegable 90 base", {"item_id": "201011", "hub_item_code": "0201011"}),
            inventory_item("0208001", "Tatami Plegable combo Crudo", {"item_id": "208001", "hub_item_code": "0208001"}),
            inventory_item("0216001", "Tatami Plegable combo Negro", {"item_id": "216001", "hub_item_code": "0216001"}),
        ]

        selectable = app._price_selectable_catalog_items(items)

        self.assertEqual([item.raw["item_id"] for item in selectable], ["201011"])
        self.assertEqual([item.code for item in selectable], ["0201011"])

    def test_base_plegable_90_still_impacts_crudo_negro_and_marron_chocolate(self) -> None:
        service = CombinationPriceImpactService()

        impact = service.impact_for_changes([{
            "component_target_key": "201011",
            "sku": "0201011",
            "old_price": "100.00",
            "new_price": "101.00",
            "proposal_key": "base-plegable-90",
        }])

        by_woo_id = {row["combination_woo_id"]: row for row in impact["included_combinations"]}
        self.assertIn("4558", by_woo_id)
        self.assertIn("4561", by_woo_id)
        self.assertIn("13091", by_woo_id)
        self.assertEqual(by_woo_id["4558"]["combination_sku"], "0201011|0808001")
        self.assertEqual(by_woo_id["4561"]["combination_sku"], "0201011|0816001")
        self.assertEqual(by_woo_id["13091"]["combination_sku"], "0201011|0818001")
        for woo_id in ("4558", "4561", "13091"):
            components = by_woo_id[woo_id]["modified_components"]
            self.assertTrue(any(
                component["component_item_id"] == "201011"
                and component["component_sku"] == "0201011"
                for component in components
            ))

    def test_approved_plegable_impact_targets_keep_exact_remote_identity(self) -> None:
        self.assertTrue(approved_local_combination_link_identity(
            item_id="208001",
            sku="0208001",
            local_kind="variation",
            local_id="4558",
            local_parent="3657",
            local_woo_sku="0201011|0808001",
        ))
        self.assertTrue(approved_local_combination_link_identity(
            item_id="216001",
            sku="0216001",
            local_kind="variation",
            local_id="4561",
            local_parent="3657",
            local_woo_sku="0201011|0816001",
        ))

    def test_price_proposal_history_reads_all_available_rows_newest_first(self) -> None:
        rows = [
            {
                "id": f"proposal-{index:03d}",
                "status": "pending",
                "created_at": f"2026-08-28T10:{index // 60:02d}:{index % 60:02d}+00:00",
                "source_row": {},
            }
            for index in range(205)
        ]
        session = HistorySession(rows)

        diagnostic = diagnose_real_price_proposals(session, status="all")
        listed = list_real_price_proposals(session, status="all")

        self.assertEqual(diagnostic["raw_count"], 205)
        self.assertEqual(diagnostic["filtered_count"], 205)
        self.assertEqual(len(diagnostic["rows"]), 205)
        self.assertEqual(len(listed), 205)
        self.assertEqual(diagnostic["rows"][0]["id"], "proposal-204")
        self.assertEqual(diagnostic["rows"][-1]["id"], "proposal-000")

    def test_eleven_saved_proposals_remain_accessible_after_adding_next_one(self) -> None:
        rows = [
            {
                "id": f"proposal-{index:02d}",
                "status": "pending",
                "created_at": f"2026-08-28T11:00:{index:02d}+00:00",
                "source_row": {},
            }
            for index in range(10)
        ]
        first = rows[0]["id"]

        self.assertEqual(len(list_real_price_proposals(HistorySession(rows), status="all")), 10)
        rows.append({
            "id": "proposal-10",
            "status": "pending",
            "created_at": "2026-08-28T11:00:10+00:00",
            "source_row": {},
        })
        listed = list_real_price_proposals(HistorySession(rows), status="all")

        self.assertEqual(len(listed), 11)
        self.assertEqual(listed[0]["id"], "proposal-10")
        self.assertIn(first, {row["id"] for row in listed})

    def test_new_price_proposal_does_not_update_previous_saved_proposal_by_default(self) -> None:
        product = {"woo_id": 10, "name": "Tatami", "type": "simple", "price": 100}
        session = HistorySession([], product_rows=[product])

        with (
            patch("futonhub.cloud.services.price_proposals.write_audit_event"),
            patch("futonhub.cloud.services.price_proposals.write_snapshot"),
        ):
            first = create_real_price_proposal(
                session,
                "product",
                10,
                110,
                acknowledge_price_warning=True,
                price_at_creation=100,
                item_snapshot=product,
            )["proposal"]
            second = create_real_price_proposal(
                session,
                "product",
                10,
                120,
                acknowledge_price_warning=True,
                price_at_creation=100,
                item_snapshot=product,
            )["proposal"]

        proposals = session.client.rows_by_table["price_change_proposals"]
        self.assertEqual(len(proposals), 2)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual([row["new_price"] for row in proposals], [110.0, 120.0])


if __name__ == "__main__":
    unittest.main()

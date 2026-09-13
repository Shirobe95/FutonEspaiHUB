from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.price_proposals import (  # noqa: E402
    PRICE_PROPOSAL_HISTORY_COUNTER_COLUMNS,
    PRICE_PROPOSAL_HISTORY_DEFAULT_PAGE_SIZE,
    PRICE_PROPOSAL_HISTORY_SUMMARY_COLUMNS,
    create_real_price_proposal,
    diagnose_real_price_proposals,
    fetch_real_price_proposal_detail_rows,
    fetch_real_price_proposal_history_page,
    list_real_price_proposals,
)
from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_catalog_reconciliation import (  # noqa: E402
    audit_price_proposal_selectable_catalogue,
    is_price_proposal_selectable_catalogue_row,
    operational_price_catalogue_rows,
    price_proposal_non_selectable_reason,
    price_proposal_selectable_catalogue_rows,
)
from futonhub.services.price_woo_catalog_index import approved_local_combination_link_identity  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype, InventoryItem  # noqa: E402


class HistoryQuery:
    def __init__(self, table_name: str, rows_by_table: dict[str, list[dict]], calls: list[dict]) -> None:
        self.table_name = table_name
        self.rows_by_table = rows_by_table
        self.calls = calls
        self.filters: list[tuple[str, object]] = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_value: int | None = None
        self.range_value: tuple[int, int] | None = None
        self.mode = "select"
        self.payload: dict | None = None
        self.select_columns = "*"

    def select(self, *args, **_kwargs):
        self.select_columns = ",".join(str(arg) for arg in args) if args else "*"
        return self

    def eq(self, column: str, value: object):
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values):
        self.filters.append((f"{column}__in", tuple(values)))
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
            if column.endswith("__in"):
                key = column[:-4]
                rows = [row for row in rows if self._row_value(row, key) in value]
            elif "->>" in column:
                rows = [row for row in rows if str(self._row_value(row, column) or "") == str(value)]
            else:
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
        self.calls.append({
            "table": self.table_name,
            "select": self.select_columns,
            "filters": list(self.filters),
            "orders": list(self.orders),
            "limit": self.limit_value,
            "range": self.range_value,
            "mode": self.mode,
        })
        if self.mode == "select" and self.select_columns != "*":
            rows = [self._project_row(row) for row in rows]
        return SimpleNamespace(data=rows)

    def _row_value(self, row: dict, column: str) -> object:
        if "->>" in column:
            _json_column, key = column.split("->>", 1)
            return (row.get("source_row") or {}).get(key)
        return row.get(column)

    def _project_row(self, row: dict) -> dict:
        projected: dict = {}
        columns = [column.strip() for column in self.select_columns.split(",") if column.strip()]
        for column in columns:
            if "->>" in column:
                _json_column, key = column.split("->>", 1)
                projected[key] = self._row_value(row, column)
            else:
                projected[column] = self._row_value(row, column)
        return projected


class HistoryClient:
    def __init__(self, rows_by_table: dict[str, list[dict]]) -> None:
        self.rows_by_table = rows_by_table
        self.calls: list[dict] = []

    def table(self, table_name: str) -> HistoryQuery:
        return HistoryQuery(table_name, self.rows_by_table, self.calls)


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

    def test_confirmed_non_operable_fundas_are_not_main_proposal_selectable(self) -> None:
        rows = [
            {"item_id": "616008", "physical_item_id": "616008", "hub_item_code": "0616008", "filter_family": "Fundas"},
            {"item_id": "608012", "physical_item_id": "608012", "hub_item_code": "0608012", "filter_family": "Fundas"},
            {"item_id": "616012", "physical_item_id": "616012", "hub_item_code": "0616012", "filter_family": "Fundas"},
            {"item_id": "608010", "physical_item_id": "608010", "hub_item_code": "0608010", "filter_family": "Fundas"},
            {"item_id": "616010", "physical_item_id": "616010", "hub_item_code": "0616010", "filter_family": "Fundas"},
            {"item_id": "608019", "physical_item_id": "608019", "hub_item_code": "608019", "filter_family": "Fundas"},
            {"item_id": "616019", "physical_item_id": "616019", "hub_item_code": "616019", "filter_family": "Fundas"},
        ]

        selectable_ids = {row["item_id"] for row in price_proposal_selectable_catalogue_rows(rows)}

        self.assertEqual(selectable_ids, set())
        for row in rows:
            with self.subTest(item_id=row["item_id"]):
                self.assertFalse(is_price_proposal_selectable_catalogue_row(row))
                self.assertTrue(price_proposal_non_selectable_reason(row))

    def test_active_missing_woo_row_is_not_hidden_by_missing_mapping_alone(self) -> None:
        row = {
            "item_id": "999001",
            "physical_item_id": "999001",
            "hub_item_code": "0999001",
            "commercial_status": "Normal",
            "woo_id": "",
            "woo_parent_id": "",
            "woo_item_kind": "",
            "woo_sku": "",
            "woo_link_status": "Sin enlace Woo",
        }

        self.assertTrue(is_price_proposal_selectable_catalogue_row(row))
        self.assertEqual(price_proposal_non_selectable_reason(row), "")

    def test_confirmed_active_missing_woo_codes_are_not_selectable(self) -> None:
        rows = [
            {
                "item_id": "758087",
                "physical_item_id": "758087",
                "hub_item_code": "0758087",
                "commercial_status": "Normal",
                "woo_id": "",
            },
            {
                "item_id": "780002",
                "physical_item_id": "780002",
                "hub_item_code": "0780002",
                "commercial_status": "Normal",
                "woo_id": "",
            },
            {
                "item_id": "780007",
                "physical_item_id": "780007",
                "hub_item_code": "0780007",
                "commercial_status": "Normal",
                "woo_id": "",
            },
            {
                "item_id": "999001",
                "physical_item_id": "999001",
                "hub_item_code": "0999001",
                "commercial_status": "Normal",
                "woo_id": "",
            },
        ]

        selectable_codes = {row["hub_item_code"] for row in price_proposal_selectable_catalogue_rows(rows)}
        audit = audit_price_proposal_selectable_catalogue(rows)

        self.assertEqual(selectable_codes, {"0999001"})
        self.assertEqual(audit["counts"]["ACTIVE_MISSING_WOO"], 4)
        self.assertEqual(audit["selectable_counts"].get("ACTIVE_MISSING_WOO"), 1)
        self.assertEqual(audit["total_selectable"], 1)
        for row in rows[:3]:
            with self.subTest(code=row["hub_item_code"]):
                self.assertFalse(is_price_proposal_selectable_catalogue_row(row))
                self.assertEqual(
                    price_proposal_non_selectable_reason(row),
                    "ACTIVE_MISSING_WOO_CONFIRMED_NOT_PRICE_SOURCE",
                )

    def test_confirmed_codes_with_direct_woo_are_not_hidden_unexpectedly(self) -> None:
        row = {
            "item_id": "758087",
            "physical_item_id": "758087",
            "hub_item_code": "0758087",
            "commercial_status": "Normal",
            "woo_id": "9999",
            "woo_sku": "0758087",
        }

        self.assertTrue(is_price_proposal_selectable_catalogue_row(row))
        self.assertEqual(price_proposal_non_selectable_reason(row), "")

    def test_non_operable_metadata_blocks_selectable_without_using_missing_woo_as_gate(self) -> None:
        row = {
            "item_id": "888001",
            "physical_item_id": "888001",
            "hub_item_code": "0888001",
            "commercial_status": "Normal",
            "woo_id": "",
            "price_operable": False,
            "sale_item": "NO",
        }

        self.assertFalse(is_price_proposal_selectable_catalogue_row(row))
        self.assertEqual(price_proposal_non_selectable_reason(row), "NON_OPERATIONAL_PRICE_POLICY")

    def test_selectable_catalogue_audit_classifies_noise_without_hiding_missing_woo(self) -> None:
        rows = [
            {"item_id": "100001", "physical_item_id": "100001", "hub_item_code": "0100001", "woo_id": "9001"},
            {"item_id": "100002", "physical_item_id": "100002", "hub_item_code": "0100002", "woo_id": ""},
            {"item_id": "402014", "physical_item_id": "402014", "hub_item_code": "0402014", "commercial_status": "Descatalogado"},
            {"item_id": "208001", "physical_item_id": "208001", "hub_item_code": "0208001", "woo_id": "4558"},
            {"item_id": "608019", "physical_item_id": "608019", "hub_item_code": "608019"},
            {"item_id": "999003", "physical_item_id": "999003", "hub_item_code": "0999003", "woo_id": "123", "woo_link_status": "Recuperar enlace"},
            {"item_id": "999004", "physical_item_id": "999004", "hub_item_code": "0999004", "catalog_live_status": "LIVE_DUPLICATE"},
        ]

        audit = audit_price_proposal_selectable_catalogue(rows)

        self.assertEqual(audit["total"], len(rows))
        self.assertEqual(sum(audit["counts"].values()), len(rows))
        self.assertEqual(audit["counts"]["ACTIVE_DIRECT_WOO"], 1)
        self.assertEqual(audit["counts"]["ACTIVE_MISSING_WOO"], 1)
        self.assertEqual(audit["counts"]["DESCATALOGADO"], 1)
        self.assertEqual(audit["counts"]["DERIVED_ONLY_NOT_PRICE_SOURCE"], 1)
        self.assertEqual(audit["counts"]["COMBINATION_COMPONENT_ONLY"], 1)
        self.assertEqual(audit["counts"]["STALE_WOO_LINK"], 1)
        self.assertEqual(audit["counts"]["AMBIGUOUS_IDENTITY"], 1)
        safe_hide_codes = {row["code"] for row in audit["safe_hide_candidates"]}
        self.assertEqual(safe_hide_codes, {"0402014", "0208001", "608019"})
        missing = next(row for row in audit["rows"] if row["code"] == "0100002")
        self.assertEqual(missing["recommended_selectable"], "YES")

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

    def test_prototype_picker_filters_confirmed_fundas_from_search_source(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        items = [
            inventory_item("0616008", "Funda Figo antigua", {"item_id": "616008", "hub_item_code": "0616008", "filter_family": "Fundas"}),
            inventory_item("608019", "Funda cilindrica componente", {"item_id": "608019", "hub_item_code": "608019", "filter_family": "Fundas"}),
            inventory_item("0999001", "Funda activa sin Woo", {"item_id": "999001", "hub_item_code": "0999001", "filter_family": "Fundas", "woo_id": ""}),
        ]

        selectable = app._price_selectable_catalog_items(items)

        self.assertEqual([item.raw["item_id"] for item in selectable], ["999001"])

    def test_prototype_picker_filters_confirmed_active_missing_woo_codes_only(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        items = [
            inventory_item("0758087", "Futon coco Premium 120", {"item_id": "758087", "hub_item_code": "0758087", "woo_id": ""}),
            inventory_item("0780002", "Futon Duo Latex 80", {"item_id": "780002", "hub_item_code": "0780002", "woo_id": ""}),
            inventory_item("0780007", "Futon Duo Latex 200", {"item_id": "780007", "hub_item_code": "0780007", "woo_id": ""}),
            inventory_item("0999001", "Activo sin Woo revisable", {"item_id": "999001", "hub_item_code": "0999001", "woo_id": ""}),
            inventory_item("0100001", "Activo Woo directo", {"item_id": "100001", "hub_item_code": "0100001", "woo_id": "9001"}),
        ]

        selectable = app._price_selectable_catalog_items(items)

        self.assertEqual([item.code for item in selectable], ["0999001", "0100001"])

    def test_finish_price_edit_items_replaces_restored_forbidden_selection(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        app._cloud_session = None
        app._current_key = "dashboard"
        app._price_items_generation = 1
        app._price_edit_selected_code = "0616008"
        app._price_live_price_context_by_physical_item = {}
        app._price_live_price_traces = []
        app._price_live_sync_required = False
        items = [
            inventory_item("0616008", "Funda antigua", {"item_id": "616008", "hub_item_code": "0616008"}),
            inventory_item("0999001", "Funda activa sin Woo", {"item_id": "999001", "hub_item_code": "0999001"}),
        ]

        app._finish_price_edit_items(items, "", 1)

        self.assertEqual(app._price_edit_selected_code, "0999001")
        self.assertEqual([item.raw["item_id"] for item in app._price_available_items], ["999001"])

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

    def test_history_summary_page_is_bounded_projected_and_newest_first(self) -> None:
        rows = [
            {
                "id": f"proposal-{index:03d}",
                "status": "pending",
                "created_at": f"2026-08-28T12:{index // 60:02d}:{index % 60:02d}+00:00",
                "item_kind": "product",
                "item_woo_id": index,
                "name": f"Articulo {index}",
                "old_price": 100,
                "new_price": 101,
                "delta": 1,
                "source_row": {
                    "ui_save_token": f"token-{index:03d}",
                    "ui_proposal_name": f"Propuesta {index}",
                    "ui_line_name": f"Linea {index}",
                    "workflow_state": "DRAFT",
                    "big_payload": "x" * 5000,
                },
            }
            for index in range(100)
        ]
        session = HistorySession(rows)

        page = fetch_real_price_proposal_history_page(session, status="all", page=1)

        self.assertEqual(page["page"], 1)
        self.assertEqual(page["page_size"], PRICE_PROPOSAL_HISTORY_DEFAULT_PAGE_SIZE)
        self.assertEqual(page["pagination_unit"], "proposal")
        self.assertTrue(page["has_next"])
        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(page["rows"][0]["id"], "proposal-099")
        self.assertEqual(page["rows"][-1]["id"], "proposal-090")
        self.assertTrue(page["rows"][0]["ui_history_summary"])
        self.assertNotIn("big_payload", page["rows"][0]["source_row"])
        self.assertEqual(page["initial_history_query_count"], 2)
        self.assertEqual(page["counter_query_count"], 1)
        self.assertEqual(page["counter_query_columns"], PRICE_PROPOSAL_HISTORY_COUNTER_COLUMNS)
        self.assertEqual(page["rows"][0]["ui_history_counts"], {"items": 1, "up": 1, "down": 0, "flat": 0})
        page_call = session.client.calls[0]
        counter_call = session.client.calls[1]
        self.assertEqual(page_call["select"], PRICE_PROPOSAL_HISTORY_SUMMARY_COLUMNS)
        self.assertNotEqual(page_call["select"], "*")
        self.assertEqual(page_call["range"], (0, 499))
        self.assertEqual(page_call["orders"], [("created_at", True), ("id", True)])
        self.assertEqual(counter_call["select"], PRICE_PROPOSAL_HISTORY_COUNTER_COLUMNS)
        self.assertEqual(counter_call["filters"][0][0], "source_row->>ui_save_token__in")
        self.assertNotIn("token-089", counter_call["filters"][0][1])

    def test_hundred_proposal_history_is_accessible_by_server_pages(self) -> None:
        rows = [
            {
                "id": f"proposal-{index:03d}",
                "status": "pending",
                "created_at": f"2026-08-28T13:{index // 60:02d}:{index % 60:02d}+00:00",
                "item_kind": "product",
                "item_woo_id": index,
                "name": f"Articulo {index}",
                "old_price": 100,
                "new_price": 101,
                "delta": 1,
                "source_row": {"ui_save_token": f"token-{index:03d}"},
            }
            for index in range(100)
        ]
        session = HistorySession(rows)

        collected: list[str] = []
        for page_number in range(1, 6):
            page = fetch_real_price_proposal_history_page(session, status="all", page=page_number, page_size=20)
            collected.extend(str(row["id"]) for row in page["rows"])

        self.assertEqual(len(collected), 100)
        self.assertEqual(len(set(collected)), 100)
        self.assertEqual(collected[0], "proposal-099")
        self.assertEqual(collected[-1], "proposal-000")
        self.assertTrue(all(call["select"] != "*" for call in session.client.calls))
        page_calls = [call for call in session.client.calls if call["range"] is not None]
        counter_calls = [call for call in session.client.calls if call["range"] is None]
        self.assertTrue(all(call["select"] == PRICE_PROPOSAL_HISTORY_SUMMARY_COLUMNS for call in page_calls))
        self.assertTrue(all(call["select"] == PRICE_PROPOSAL_HISTORY_COUNTER_COLUMNS for call in counter_calls))
        self.assertTrue(all(call["select"] != "*" for call in session.client.calls))
        self.assertTrue(all((call["range"][1] - call["range"][0] + 1) <= 500 for call in page_calls))

    def test_history_page_contains_twenty_unique_proposals_when_latest_has_many_rows(self) -> None:
        rows: list[dict] = []
        for line in range(30):
            rows.append({
                "id": f"proposal-099-line-{line:02d}",
                "status": "pending",
                "created_at": f"2026-08-28T16:59:{line:02d}+00:00",
                "item_kind": "product",
                "item_woo_id": line,
                "name": f"Linea pesada {line}",
                "old_price": 100,
                "new_price": 101,
                "delta": 1,
                "source_row": {
                    "ui_save_token": "token-099",
                    "ui_proposal_name": "Propuesta pesada",
                },
            })
        for index in range(99):
            rows.append({
                "id": f"proposal-{index:03d}-line-00",
                "status": "pending",
                "created_at": f"2026-08-28T16:{index // 60:02d}:{index % 60:02d}+00:00",
                "item_kind": "product",
                "item_woo_id": index,
                "name": f"Articulo {index}",
                "old_price": 100,
                "new_price": 101,
                "delta": 1,
                "source_row": {"ui_save_token": f"token-{index:03d}"},
            })
        session = HistorySession(rows)

        page_1 = fetch_real_price_proposal_history_page(session, status="all", page=1, page_size=20)
        page_2 = fetch_real_price_proposal_history_page(session, status="all", page=2, page_size=20)

        page_1_tokens = [row["source_row"]["ui_save_token"] for row in page_1["rows"]]
        page_2_tokens = [row["source_row"]["ui_save_token"] for row in page_2["rows"]]
        self.assertEqual(len(page_1_tokens), 20)
        self.assertEqual(len(set(page_1_tokens)), 20)
        self.assertEqual(page_1_tokens[0], "token-099")
        self.assertEqual(page_1_tokens[-1], "token-080")
        self.assertEqual(len(page_2_tokens), 20)
        self.assertEqual(page_2_tokens[0], "token-079")
        self.assertEqual(page_2_tokens[-1], "token-060")
        self.assertEqual(set(page_1_tokens).intersection(page_2_tokens), set())
        self.assertEqual(page_1["rows_per_logical_proposal_sample"]["ui_save_token:token-099"], 30)

    def test_price_history_ui_has_no_pagination_controls(self) -> None:
        render_source = inspect.getsource(FutonHubErpPrototype._build_saved_proposals_workspace)
        class_source = inspect.getsource(FutonHubErpPrototype)

        self.assertNotIn('"Anterior"', render_source)
        self.assertNotIn('"Siguiente"', render_source)
        self.assertNotIn("_set_price_history_page", class_source)

    def test_history_summary_counters_are_real_before_detail_load_and_match_detail(self) -> None:
        app = object.__new__(FutonHubErpPrototype)

        def proposal_rows(token: str, name: str, total: int, up: int, down: int, minute: int) -> list[dict]:
            rows: list[dict] = []
            for index in range(total):
                is_up = index < up
                is_down = up <= index < up + down
                rows.append({
                    "id": f"{token}-line-{index:02d}",
                    "status": "pending",
                    "created_at": f"2026-08-28T14:{minute:02d}:{index:02d}+00:00",
                    "item_kind": "product",
                    "item_woo_id": f"{token}-{index}",
                    "name": f"{name} linea {index}",
                    "old_price": 100,
                    "new_price": 110 if is_up else 90 if is_down else 100,
                    "delta": 10 if is_up else -10 if is_down else 0,
                    "source_row": {
                        "ui_save_token": token,
                        "ui_proposal_name": name,
                        "ui_line_name": f"{name} linea {index}",
                        "workflow_state": "DRAFT",
                    },
                })
            return rows

        rows = (
            proposal_rows("proposal-a", "Proposal A", 15, 12, 3, 59)
            + proposal_rows("proposal-b", "Proposal B", 7, 2, 5, 58)
            + proposal_rows("proposal-c", "Proposal C", 1, 1, 0, 57)
        )
        session = HistorySession(rows)

        page = fetch_real_price_proposal_history_page(session, status="all", page=1, page_size=3)
        summary_proposals = app._price_group_cloud_proposals(page["rows"])
        summary_by_name = {proposal.name: proposal for proposal in summary_proposals}

        self.assertEqual((summary_by_name["Proposal A"].items, summary_by_name["Proposal A"].up, summary_by_name["Proposal A"].down), (15, 12, 3))
        self.assertEqual((summary_by_name["Proposal B"].items, summary_by_name["Proposal B"].up, summary_by_name["Proposal B"].down), (7, 2, 5))
        self.assertEqual((summary_by_name["Proposal C"].items, summary_by_name["Proposal C"].up, summary_by_name["Proposal C"].down), (1, 1, 0))
        self.assertEqual(app._price_proposal_list_count_text(summary_by_name["Proposal A"], summary_by_name["Proposal A"].items), "15")
        self.assertEqual(app._price_proposal_list_count_text(summary_by_name["Proposal A"], summary_by_name["Proposal A"].up), "12")
        self.assertEqual(app._price_proposal_list_count_text(summary_by_name["Proposal A"], summary_by_name["Proposal A"].down), "3")

        mismatches = []
        for summary_row in page["rows"]:
            summary_proposal = summary_by_name[str(summary_row["source_row"]["ui_proposal_name"])]
            detail_rows = fetch_real_price_proposal_detail_rows(
                session,
                str(summary_row["id"]),
                group_key=str(summary_row["ui_history_group_key"]),
            )
            detail_proposal = app._price_group_cloud_proposals(detail_rows)[0]
            if (
                summary_proposal.items,
                summary_proposal.up,
                summary_proposal.down,
            ) != (
                detail_proposal.items,
                detail_proposal.up,
                detail_proposal.down,
            ):
                mismatches.append(summary_proposal.name)

        self.assertEqual(mismatches, [])

    def test_only_visible_ten_receive_initial_counter_query(self) -> None:
        rows = []
        for index in range(100):
            rows.append({
                "id": f"proposal-{index:03d}",
                "status": "pending",
                "created_at": f"2026-08-28T15:{index // 60:02d}:{index % 60:02d}+00:00",
                "item_kind": "product",
                "item_woo_id": index,
                "name": f"Linea {index}",
                "old_price": 100,
                "new_price": 101,
                "delta": 1,
                "source_row": {
                    "ui_save_token": f"token-{index:03d}",
                    "ui_proposal_name": f"Proposal {index}",
                    "ui_line_name": f"Linea {index}",
                    "workflow_state": "DRAFT",
                },
            })
        session = HistorySession(rows)

        page = fetch_real_price_proposal_history_page(session, status="all", page=1)

        self.assertEqual(len(page["rows"]), 10)
        self.assertEqual(page["initial_history_query_count"], 2)
        counter_call = session.client.calls[1]
        self.assertEqual(counter_call["filters"][0][0], "source_row->>ui_save_token__in")
        visible_tokens = counter_call["filters"][0][1]
        self.assertIn("token-099", visible_tokens)
        self.assertIn("token-090", visible_tokens)
        self.assertNotIn("token-089", visible_tokens)
        self.assertEqual(len(visible_tokens), 10)

    def test_history_detail_lazy_loads_only_selected_group_rows(self) -> None:
        rows = [
            {
                "id": "line-new",
                "status": "pending",
                "created_at": "2026-08-28T14:00:03+00:00",
                "item_kind": "product",
                "item_woo_id": 30,
                "name": "Otro",
                "old_price": 100,
                "new_price": 105,
                "delta": 5,
                "source_row": {"ui_save_token": "other", "big_payload": "z" * 5000},
            },
            {
                "id": "line-b",
                "status": "pending",
                "created_at": "2026-08-28T14:00:02+00:00",
                "item_kind": "product",
                "item_woo_id": 20,
                "name": "Linea B",
                "old_price": 100,
                "new_price": 108,
                "delta": 8,
                "source_row": {"ui_save_token": "group-a", "ui_proposal_name": "Grupo A", "big_payload": "y" * 5000},
            },
            {
                "id": "line-a",
                "status": "pending",
                "created_at": "2026-08-28T14:00:01+00:00",
                "item_kind": "product",
                "item_woo_id": 10,
                "name": "Linea A",
                "old_price": 100,
                "new_price": 110,
                "delta": 10,
                "source_row": {"ui_save_token": "group-a", "ui_proposal_name": "Grupo A", "big_payload": "x" * 5000},
            },
        ]
        session = HistorySession(rows)
        page = fetch_real_price_proposal_history_page(session, status="all", page=1, page_size=20)
        summary = next(row for row in page["rows"] if row["id"] == "line-b")

        detail = fetch_real_price_proposal_detail_rows(
            session,
            str(summary["id"]),
            group_key="ui_save_token:group-a",
        )

        self.assertEqual([row["id"] for row in detail], ["line-b", "line-a"])
        self.assertIn("big_payload", detail[0]["source_row"])
        detail_calls = session.client.calls[-2:]
        self.assertEqual(detail_calls[0]["select"], "*")
        self.assertEqual(detail_calls[0]["filters"], [("id", "line-b")])
        self.assertEqual(detail_calls[1]["select"], "*")
        self.assertEqual(detail_calls[1]["filters"], [("source_row->>ui_save_token", "group-a")])
        self.assertEqual(detail_calls[1]["limit"], 500)

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

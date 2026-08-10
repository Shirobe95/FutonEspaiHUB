from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.woo_map_001a_7_reconciliation import _entity_fingerprint
from futonhub.services.woo_map_001a_8_preflight import evaluate_preflight, safe_master_rows


class FakeWooIndex:
    def __init__(self, entity: dict[str, object] | None, *, parent_exists: bool = True) -> None:
        self.entity_value = entity
        self.products_by_id = {"101": {"woo_id": "101"}} if parent_exists else {}

    def entity(self, *, kind: str, woo_id: object, parent_woo_id: object = "") -> dict[str, object] | None:
        if self.entity_value is None:
            return None
        if (kind, str(woo_id), str(parent_woo_id)) != ("variation", "11", "101"):
            return None
        return self.entity_value


def entity(*, status: str = "publish") -> dict[str, object]:
    return {
        "woo_id": "11",
        "parent_woo_id": "101",
        "woo_item_kind": "variation",
        "woo_sku": "0201001",
        "name": "Tatami 80 x 200",
        "status": status,
        "date_modified": "2026-08-10T00:00:00",
        "raw": {"status": status, "date_modified_gmt": "2026-08-10T00:00:00"},
    }


def plan() -> dict[str, str]:
    live_entity = entity()
    return {
        "physical_item_id": "1",
        "physical_sku": "0201001",
        "woo_resolution_status": "ACTIVE_DIRECT_WOO_VERIFIED",
        "woo_id": "11",
        "woo_parent_id": "101",
        "woo_kind": "variation",
        "woo_sku": "0201001",
        "woo_name": "Tatami 80 x 200",
        "woo_status": "publish",
        "woo_identity_sha256": _entity_fingerprint(live_entity),
        "physical_identity_sha256": "frozen-physical",
    }


def plans() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item_id in range(1, 178):
        row = plan()
        row["physical_item_id"] = str(item_id)
        rows.append(row)
    return rows


def live(**mapping: object) -> dict[str, object]:
    row: dict[str, object] = {
        "item_id": "1",
        "hub_item_code": "0201001",
        "heca_reference": "0201001",
        "name": "Tatami",
        "family": "Tatamis",
        "filter_family": "Tatamis",
        "brand": "",
        "filter_group": "Tatami",
        "size": "80x200",
        "filter_size": "80x200",
        "catalog_range": "Natural",
        "filter_gama": "Natural",
    }
    row.update(mapping)
    return row


class WooMap001A8PreflightTests(unittest.TestCase):
    columns = ("woo_item_kind", "woo_id", "woo_parent_id", "woo_sku", "woo_name", "woo_link_status")

    def evaluate(self, row: dict[str, object], index: FakeWooIndex | None = None):
        inventory = []
        for item_id in range(1, 178):
            item = live()
            item["item_id"] = str(item_id)
            inventory.append(item)
        inventory[0].update(row)
        return evaluate_preflight(plans(), inventory, woo_index=index or FakeWooIndex(entity()), mapping_columns=self.columns).rows[0]

    def test_safe_baseline_requires_exactly_177_unique_rows(self) -> None:
        with self.assertRaises(ValueError):
            safe_master_rows([plan()])

    def test_empty_mapping_needs_link(self) -> None:
        row = self.evaluate(live())
        self.assertEqual(row["current_mapping_state"], "NEEDS_INSERT_OR_LINK")
        self.assertEqual(row["safe_to_apply"], "YES_PREVIEW_ONLY")

    def test_matching_mapping_is_already_persisted(self) -> None:
        row = self.evaluate(live(woo_item_kind="variation", woo_id="11", woo_parent_id="101", woo_sku="0201001", woo_name="Tatami 80 x 200"))
        self.assertEqual(row["current_mapping_state"], "ALREADY_PERSISTED_EXACT")
        self.assertEqual(row["planned_action"], "NO_ACTION")

    def test_different_existing_woo_is_a_conflict(self) -> None:
        row = self.evaluate(live(woo_id="999"))
        self.assertEqual(row["current_mapping_state"], "CONFLICT_EXISTING_MAPPING")
        self.assertEqual(row["safe_to_apply"], "NO")

    def test_changed_woo_hash_blocks_future_apply(self) -> None:
        row = self.evaluate(live(), FakeWooIndex(entity(status="private")))
        self.assertEqual(row["current_mapping_state"], "WOO_CHANGED_SINCE_PLAN")
        self.assertEqual(row["safe_to_apply"], "NO")

    def test_literal_leading_zero_identity_is_required(self) -> None:
        row = self.evaluate(live(hub_item_code="201001", heca_reference="201001"))
        self.assertEqual(row["current_mapping_state"], "READ_ERROR")


if __name__ == "__main__":
    unittest.main()

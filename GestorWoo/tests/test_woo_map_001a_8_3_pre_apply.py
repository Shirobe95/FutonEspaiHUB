from __future__ import annotations

import csv
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_combination_live_reconciliation import _reconciliation_status  # noqa: E402
from futonhub.services.woo_map_001a_8_3_pre_apply import (  # noqa: E402
    PRE_APPLY_REQUIREMENTS,
    apply_ready_rows,
    build_master_pre_apply_rows,
    missing_direct_policy_rows,
    normalize_preflight_rows,
    preflight_summary,
)


REPO_ROOT = ROOT.parent
AUDIT_ROOT = REPO_ROOT / "auditoria" / "out"


def minimal_row(*, item_id: str, write_count: str) -> dict[str, str]:
    return {
        "physical_item_id": item_id,
        "physical_sku": f"0{item_id}",
        "field_write_count": write_count,
        "write_woo_id": "YES" if write_count != "0" else "NO",
        "woo_id_current": "",
        "woo_id_target": "123",
        "write_parent": "NO",
        "write_kind": "NO",
        "write_sku": "NO",
        "write_name": "NO",
        "write_link_status": "NO",
    }


def frozen_row(*, item_id: str, precondition_ok: str = "YES", safe_to_apply: str = "YES_PREVIEW_ONLY", reason: str = "") -> dict[str, str]:
    return {
        "physical_item_id": item_id,
        "current_mapping_state": "NEEDS_SAFE_UPDATE",
        "precondition_ok": precondition_ok,
        "safe_to_apply": safe_to_apply,
        "blocking_reason": reason,
        "physical_hash": "physical-hash",
        "woo_hash": "woo-hash",
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class WooMap001A83PreApplyTests(unittest.TestCase):
    def test_zero_field_write_is_no_action_without_blocking_reason(self) -> None:
        row = normalize_preflight_rows([minimal_row(item_id="1", write_count="0")], [frozen_row(item_id="1")])[0]
        self.assertEqual(row["plan_status"], "NO_ACTION_REQUIRED")
        self.assertEqual(row["blocking_reason"], "")
        self.assertEqual(row["pre_apply_requirement"], "")

    def test_actual_write_with_preconditions_is_ready(self) -> None:
        row = normalize_preflight_rows([minimal_row(item_id="2", write_count="1")], [frozen_row(item_id="2")])[0]
        self.assertEqual(row["plan_status"], "READY_FOR_APPLY")
        self.assertEqual(row["blocking_reason"], "")
        self.assertEqual(row["pre_apply_requirement"], PRE_APPLY_REQUIREMENTS)

    def test_failed_precondition_is_blocked_and_excluded_from_apply_csv(self) -> None:
        normalized = normalize_preflight_rows(
            [minimal_row(item_id="3", write_count="1")],
            [frozen_row(item_id="3", precondition_ok="NO", safe_to_apply="NO", reason="Woo hash changed.")],
        )
        self.assertEqual(normalized[0]["plan_status"], "BLOCKED")
        self.assertEqual(normalized[0]["blocking_reason"], "Woo hash changed.")
        self.assertEqual(apply_ready_rows(normalized), [])

    def test_apply_csv_never_contains_rows_without_changes(self) -> None:
        normalized = normalize_preflight_rows(
            [minimal_row(item_id="4", write_count="0"), minimal_row(item_id="5", write_count="1")],
            [frozen_row(item_id="4"), frozen_row(item_id="5")],
        )
        ready = apply_ready_rows(normalized)
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["physical_item_id"], "5")
        self.assertEqual(ready[0]["fields_to_write"], "woo_id")
        self.assertEqual(preflight_summary(normalized)["field_writes_total"], 1)

    def test_master_preserves_254_and_promotes_okinawa_only_as_technical_safe(self) -> None:
        master = read_csv(AUDIT_ROOT / "woo_map_001a_7_1_1" / "WOO_MAP_001A_7_1_1_MASTER_254.csv")
        private = read_csv(AUDIT_ROOT / "woo_map_001a_8_2" / "WOO_MAP_001A_8_2_PRIVATE_PRICE_ELIGIBILITY_AUDIT.csv")
        result = build_master_pre_apply_rows(master, private)
        self.assertEqual(len(result), 254)
        by_sku = {row["physical_sku"]: row for row in result}
        self.assertEqual(by_sku["0902005"]["woo_resolution_status"], "SAFE_TECHNICAL_APPROVED_EQUIVALENCE")
        self.assertEqual(by_sku["0902005"]["safe_to_persist"], "YES")
        self.assertEqual(by_sku["0902005"]["requires_user_review"], "NO")
        self.assertEqual(by_sku["0206001"]["price_change_eligible"], "NO")
        private_master = [row for row in result if row["woo_status"] == "private"]
        self.assertEqual(len(private_master), 9)
        self.assertTrue(all(row["price_change_eligible"] == "NO" for row in private_master))
        self.assertEqual(by_sku["0402014"]["woo_id"], "")
        self.assertNotEqual(by_sku["0402014"]["woo_id"], by_sku["0302009"]["woo_id"])

    def test_private_relation_is_retained_but_derived_target_is_not_publishable(self) -> None:
        status, reason = _reconciliation_status(
            {
                "combination_woo_id": "4557",
                "combination_parent_woo_id": "3657",
                "combination_sku": "0201011|0817001",
                "modified_components": [{"quantity": "1"}],
            },
            {
                "id": 4557,
                "parent_id": 3657,
                "sku": "0201011|0817001",
                "status": "private",
                "regular_price": "99.00",
                "price": "99.00",
            },
            "",
            duplicate=False,
        )
        self.assertEqual(status, "NOT_PUBLISHED")
        self.assertIn("private", reason)

    def test_macao_remains_separate_and_missing_64_have_no_relation_action(self) -> None:
        master = read_csv(AUDIT_ROOT / "woo_map_001a_7_1_1" / "WOO_MAP_001A_7_1_1_MASTER_254.csv")
        missing = read_csv(AUDIT_ROOT / "woo_map_001a_8_1" / "WOO_MAP_001A_8_1_MISSING_64_GROUPED.csv")
        policy = missing_direct_policy_rows(missing, master)
        self.assertEqual(len(policy), 64)
        self.assertTrue(all(row["relation_action"] == "DO_NOT_CREATE_OR_ASSIGN_WOO" for row in policy))
        self.assertEqual(sum(row["policy_classification"] == "LEGACY_OR_DISCONTINUED_CANDIDATE" for row in policy), 55)

    def test_planning_service_has_no_network_or_persistence_client(self) -> None:
        from futonhub.services import woo_map_001a_8_3_pre_apply

        source = inspect.getsource(woo_map_001a_8_3_pre_apply)
        for forbidden in ("WooCommerceClient", "create_supabase_client", ".post(", ".put(", ".patch(", ".delete(", ".insert(", ".upsert("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

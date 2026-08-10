from __future__ import annotations

import csv
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.woo_link_status_compat import (  # noqa: E402
    LINKED,
    NO_DIRECT_WOO,
    TEST_TECHNICAL,
    UNLINKED,
    canonical_woo_link_status,
)
from futonhub.services.woo_map_001a_8_3_1_preflight import (  # noqa: E402
    apply_ready_rows,
    build_preflight_rows,
    link_status_transition,
    preflight_summary,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


AUDIT_ROOT = ROOT.parent / "auditoria" / "out"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def safe_source(item_id: int, *, sku: str | None = None) -> dict[str, str]:
    code = sku or f"S{item_id:04d}"
    return {
        "physical_item_id": str(item_id),
        "physical_sku": code,
        "woo_resolution_status": "ACTIVE_DIRECT_WOO_VERIFIED",
        "woo_id": str(10000 + item_id),
        "woo_parent_id": str(9000 + item_id),
        "woo_kind": "variation",
        "woo_sku": code,
        "woo_name": f"Item {code}",
        "woo_status": "publish",
        "price_change_eligible": "YES",
        "physical_identity_sha256": f"physical-{item_id}",
        "woo_identity_sha256": f"woo-{item_id}",
    }


def live_for(source: dict[str, str], *, link_status: str = "Enlazado") -> dict[str, str]:
    return {
        "item_id": source["physical_item_id"],
        "woo_id": source["woo_id"],
        "woo_parent_id": source["woo_parent_id"],
        "woo_item_kind": source["woo_kind"],
        "woo_sku": source["woo_sku"],
        "woo_name": source["woo_name"],
        "woo_link_status": link_status,
    }


def valid_for(source: dict[str, str]) -> dict[str, str]:
    return {
        "physical_identity_verified": "YES",
        "woo_relation_verified": "YES",
        "live_physical_hash": source["physical_identity_sha256"],
        "live_woo_hash": source["woo_identity_sha256"],
    }


class WooMap001A831PreflightTests(unittest.TestCase):
    def test_live_spanish_link_statuses_are_known_to_the_semaphore(self) -> None:
        app = object.__new__(FutonHubErpPrototype)
        base = {
            "item_id": "1",
            "woo_id": "11",
            "woo_price": "99.00",
            "family": "Tatamis",
            "subgroup": "Tatami",
            "materials": "Algodon",
            "size": "80x200",
            "cubic_meters": "0.1",
        }
        expected = {
            "Enlazado": LINKED,
            "Enlazado manual": LINKED,
            "Sin enlazar": UNLINKED,
            "Sin Woo": UNLINKED,
            "Sin Woo directo": NO_DIRECT_WOO,
            "TEST_NO_WOO": TEST_TECHNICAL,
        }
        for value, canonical in expected.items():
            with self.subTest(value=value):
                self.assertEqual(canonical_woo_link_status(value), canonical)
                _status, reasons = app._inventory_status_analysis_from_row({**base, "woo_link_status": value})
                self.assertFalse(any("desconocido" in reason.lower() for reason in reasons))

    def test_unlinked_statuses_transition_to_enlazado_only_after_exact_direct_relation(self) -> None:
        for value in ("Sin enlazar", "Sin Woo"):
            with self.subTest(value=value):
                result = link_status_transition(value, direct_relation_verified=True)
                self.assertEqual(result["target_link_status"], "Enlazado")
                self.assertEqual(result["write_link_status"], "YES")

    def test_linked_manual_is_preserved_and_test_marker_is_never_automatic(self) -> None:
        manual = link_status_transition("Enlazado manual", direct_relation_verified=True)
        technical = link_status_transition("TEST_NO_WOO", direct_relation_verified=True)
        self.assertEqual(manual["target_link_status"], "Enlazado manual")
        self.assertEqual(manual["write_link_status"], "NO")
        self.assertEqual(technical["write_link_status"], "NO")
        self.assertEqual(technical["requires_review"], "YES")

    def test_no_direct_woo_transitions_only_with_exact_direct_evidence(self) -> None:
        absent = link_status_transition("Sin Woo directo", direct_relation_verified=False)
        verified = link_status_transition("Sin Woo directo", direct_relation_verified=True)
        self.assertEqual(absent["write_link_status"], "NO")
        self.assertEqual(verified["target_link_status"], "Enlazado")
        self.assertEqual(verified["write_link_status"], "YES")

    def test_no_action_row_never_writes_link_status(self) -> None:
        master = [safe_source(item_id) for item_id in range(1, 179)]
        live = {row["physical_item_id"]: live_for(row, link_status="Sin enlazar") for row in master}
        validations = {row["physical_item_id"]: valid_for(row) for row in master}
        rows = build_preflight_rows(master, live, validations)
        self.assertTrue(all(row["plan_status"] == "NO_ACTION_REQUIRED" for row in rows))
        self.assertTrue(all(row["write_link_status"] == "NO" for row in rows))
        self.assertEqual(apply_ready_rows(rows), [])

    def test_safe_master_178_is_fully_represented_and_okinawa_is_once(self) -> None:
        master = [safe_source(item_id, sku="0902005" if item_id == 1 else None) for item_id in range(1, 179)]
        live = {row["physical_item_id"]: live_for(row) for row in master}
        validations = {row["physical_item_id"]: valid_for(row) for row in master}
        rows = build_preflight_rows(master, live, validations)
        summary = preflight_summary(rows)
        self.assertEqual(summary["safe_master_count"], 178)
        self.assertEqual(summary["safe_master_count"], summary["rows_no_action"] + summary["rows_ready"] + summary["rows_blocked"])
        self.assertEqual(sum(row["physical_sku"] == "0902005" for row in rows), 1)

    def test_frozen_master_keeps_private_prices_and_macao_away_from_3661(self) -> None:
        master = read_csv(AUDIT_ROOT / "woo_map_001a_8_3" / "WOO_MAP_001A_8_3_MASTER_PRE_APPLY.csv")
        safe = [row for row in master if row["safe_to_persist"] == "YES"]
        self.assertEqual(len(safe), 178)
        self.assertEqual(sum(row["physical_sku"] == "0902005" for row in safe), 1)
        private = [row for row in master if row["woo_status"] == "private"]
        self.assertTrue(private)
        self.assertTrue(all(row["price_change_eligible"] == "NO" for row in private))
        macao = next(row for row in master if row["physical_sku"] == "0402014")
        self.assertNotEqual(macao["woo_id"], "3661")

    def test_planning_services_have_no_productive_clients_or_mutation_methods(self) -> None:
        from futonhub.services import woo_link_status_compat, woo_map_001a_8_3_1_preflight

        source = inspect.getsource(woo_link_status_compat) + inspect.getsource(woo_map_001a_8_3_1_preflight)
        for forbidden in ("WooCommerceClient", "create_supabase_client", ".post(", ".put(", ".patch(", ".delete(", ".insert(", ".upsert("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

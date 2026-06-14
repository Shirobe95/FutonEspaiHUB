from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gestorwoo.cloud.audit import CloudAuditError
from gestorwoo.cloud.operational import list_real_price_proposals
from gestorwoo.cloud.services.prices import price_safety_preview
from gestorwoo.cloud.services.rollback import rollback_update_payload
from gestorwoo.config import Settings


def _settings() -> Settings:
    return Settings(
        woocommerce_url="https://example.test",
        consumer_key="ck_test",
        consumer_secret="cs_test",
        db_path=ROOT / "data" / "gestorwoo.sqlite3",
        app_mode="supabase_guarded",
        machine_name="TEST",
        env_path=ROOT / ".env",
        supabase_url="https://example.supabase.co",
        supabase_anon_key="anon",
        supabase_service_key="",
        sync_role="admin",
        hub_user_email="admin@example.test",
        price_drop_warning_percent=30.0,
        price_drop_block_percent=60.0,
    )


class PriceSafetyPreviewTests(unittest.TestCase):
    def test_blocks_zero_or_negative_price(self) -> None:
        result = price_safety_preview({"price": "100", "type": "simple"}, "product", 0, _settings())

        self.assertEqual(result["status"], "ERROR")
        self.assertTrue(any("mayor que 0" in message for message in result["messages"]))

    def test_warns_on_large_drop_before_block_threshold(self) -> None:
        result = price_safety_preview({"price": "100", "type": "simple"}, "product", 60, _settings())

        self.assertEqual(result["status"], "WARNING")
        self.assertAlmostEqual(result["delta_percent"], -40.0)

    def test_blocks_drop_at_block_threshold(self) -> None:
        result = price_safety_preview({"price": "100", "type": "simple"}, "product", 40, _settings())

        self.assertEqual(result["status"], "ERROR")


class RollbackPayloadTests(unittest.TestCase):
    def test_inventory_rollback_preserves_keys_and_sets_traceability(self) -> None:
        payload = rollback_update_payload(
            "inventory_items",
            "item_id",
            {
                "id": "internal",
                "item_id": 123,
                "created_at": "old-created",
                "updated_at": "old-updated",
                "updated_by": "old-user",
                "store_stock": 5,
            },
            user_id="new-admin",
        )

        self.assertNotIn("id", payload)
        self.assertNotIn("item_id", payload)
        self.assertNotIn("created_at", payload)
        self.assertEqual(payload["updated_by"], "new-admin")
        self.assertNotEqual(payload["updated_at"], "old-updated")
        self.assertEqual(payload["store_stock"], 5)

    def test_price_proposal_rollback_does_not_add_missing_updated_columns(self) -> None:
        payload = rollback_update_payload(
            "price_change_proposals",
            "id",
            {
                "id": "proposal-id",
                "status": "approved",
                "new_price": 219,
            },
            user_id="new-admin",
        )

        self.assertNotIn("id", payload)
        self.assertNotIn("updated_at", payload)
        self.assertNotIn("updated_by", payload)
        self.assertEqual(payload["status"], "approved")


class PriceProposalListTests(unittest.TestCase):
    def test_rejects_unknown_status_before_querying_supabase(self) -> None:
        class Session:
            client = object()

        with self.assertRaises(CloudAuditError):
            list_real_price_proposals(Session(), status="unknown")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.audit import AuditEvent, CloudAuditError, OperationSnapshot  # noqa: E402
from futonhub.cloud.services import woocommerce_publish as publish  # noqa: E402
from gestorwoo.config import Settings  # noqa: E402


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


class WooBlackboxSnapshotPersistenceTests(unittest.TestCase):
    def test_snapshot_persistence_retries_before_success(self) -> None:
        snapshot = OperationSnapshot(
            operation_id="OP-SNAPSHOT",
            module="woocommerce_publish",
            action="publish_price",
            entity_type="price_change_proposal",
            entity_id="proposal-1",
            before_data={"regular_price": "150.00", "sale_price": "128.00"},
            reason="test",
        )

        with patch.object(publish, "write_snapshot", return_value={"ok": True}) as write_snapshot, patch.object(
            publish, "_blackbox_record_exists", side_effect=[False, True]
        ) as exists:
            result = publish._ensure_snapshot_persisted(Mock(), snapshot)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(write_snapshot.call_count, 2)
        self.assertEqual(exists.call_args_list[0].args[1:], ("operation_snapshots", "OP-SNAPSHOT"))
        self.assertEqual(exists.call_args_list[1].args[1:], ("operation_snapshots", "OP-SNAPSHOT"))

    def test_snapshot_persistence_blocks_when_not_confirmed(self) -> None:
        snapshot = OperationSnapshot(
            operation_id="OP-SNAPSHOT-MISSING",
            module="woocommerce_publish",
            action="publish_price",
            entity_type="price_change_proposal",
            entity_id="proposal-1",
            before_data={},
            reason="test",
        )

        with patch.object(publish, "write_snapshot", return_value={"ok": True}) as write_snapshot, patch.object(
            publish, "_blackbox_record_exists", return_value=False
        ):
            with self.assertRaises(CloudAuditError):
                publish._ensure_snapshot_persisted(Mock(), snapshot)

        self.assertEqual(write_snapshot.call_count, 2)


class WooBlackboxAuditPersistenceTests(unittest.TestCase):
    def test_audit_persistence_retries_before_success(self) -> None:
        event = AuditEvent(
            operation_id="OP-AUDIT",
            module="woocommerce_publish",
            action="publish_price",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id="proposal-1",
            before_data={"regular_price": "150.00"},
            after_data={"regular_price": "160.00"},
            message="test",
        )

        with patch.object(publish, "write_audit_event", return_value={"ok": True}) as write_audit, patch.object(
            publish, "_blackbox_record_exists", side_effect=[False, True]
        ) as exists:
            result = publish._ensure_audit_persisted(Mock(), event, _settings())

        self.assertEqual(result, {"ok": True})
        self.assertEqual(write_audit.call_count, 2)
        self.assertEqual(exists.call_args_list[0].args[1:], ("audit_logs", "OP-AUDIT"))
        self.assertEqual(exists.call_args_list[1].args[1:], ("audit_logs", "OP-AUDIT"))

    def test_audit_persistence_does_not_declare_closed_when_missing(self) -> None:
        event = AuditEvent(
            operation_id="OP-AUDIT-MISSING",
            module="woocommerce_publish",
            action="publish_price",
            status="OK",
            severity="INFO",
            entity_type="price_change_proposal",
            entity_id="proposal-1",
            before_data={},
            after_data={},
            message="test",
        )

        with patch.object(publish, "write_audit_event", return_value={"ok": True}) as write_audit, patch.object(
            publish, "_blackbox_record_exists", return_value=False
        ):
            with self.assertRaises(CloudAuditError):
                publish._ensure_audit_persisted(Mock(), event, _settings())

        self.assertEqual(write_audit.call_count, 2)


if __name__ == "__main__":
    unittest.main()


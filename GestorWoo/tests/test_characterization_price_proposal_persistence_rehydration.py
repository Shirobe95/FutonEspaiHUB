from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.audit import CloudAuditError  # noqa: E402
from futonhub.cloud.services import price_proposals, woocommerce_publish  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from futonhub.ui.erp.shared_ui import ProposalLine  # noqa: E402


def settings():
    return SimpleNamespace(
        price_drop_warning_percent=30.0,
        price_drop_block_percent=60.0,
        sync_role="worker",
        machine_name="TEST",
    )


class Response:
    def __init__(self, data=None):
        self.data = data or []


class Query:
    def __init__(self, session, table):
        self.session = session
        self.table_name = table
        self.equals = []
        self.payload = None
        self.mode = "select"

    def select(self, *_args, **_kwargs):
        self.mode = "select"
        return self

    def eq(self, column, value):
        self.equals.append((column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def insert(self, payload):
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload):
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def execute(self):
        rows = self.session.tables.setdefault(self.table_name, [])
        selected = list(rows)
        for column, value in self.equals:
            selected = [row for row in selected if row.get(column) == value]
        if self.mode == "insert":
            row = {"id": f"saved-{len(rows) + 1}", **(self.payload or {})}
            rows.append(row)
            self.session.writes.append((self.table_name, dict(row)))
            return Response([dict(row)])
        if self.mode == "update":
            for row in selected:
                row.update(self.payload or {})
                self.session.writes.append((self.table_name, dict(row)))
            return Response([dict(row) for row in selected])
        return Response([dict(row) for row in selected])


class Session:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.client = self
        self.role = "admin"
        self.user_id = "user"
        self.email = "admin@example.invalid"
        self.writes = []

    def table(self, name):
        return Query(self, name)


class PriceProposalPersistenceRehydrationTests(unittest.TestCase):
    def setUp(self):
        self.app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        self.app._price_proposal_model = {}
        self.app._price_edit_lines = []
        self.app._price_proposal_line_sources = {}
        self.app._price_search_results = []
        self.app._price_available_items = []
        self.app._inventory_items = []
        self.app._price_line_sources = {}

    def test_service_uses_authoritative_price_at_creation(self):
        session = Session({
            "products": [{"woo_id": 10, "name": "Tatami", "type": "simple", "price": 100}],
            "price_change_proposals": [],
        })
        with (
            patch.object(price_proposals, "write_audit_event"),
            patch.object(price_proposals, "write_snapshot"),
        ):
            result = price_proposals.create_real_price_proposal(
                session,
                "product",
                10,
                132,
                settings=settings(),
                acknowledge_price_warning=True,
                price_at_creation=120,
                source_row_updates={
                    "price_at_creation": 120,
                    "proposed_price": 132,
                },
            )
        row = result["proposal"]
        self.assertEqual(row["old_price"], 120)
        self.assertEqual(row["new_price"], 132)

    def test_payload_and_source_snapshot_keep_same_prices(self):
        session = Session({
            "products": [{"woo_id": 10, "name": "Tatami", "type": "simple", "price": 100}],
            "price_change_proposals": [],
        })
        with (
            patch.object(price_proposals, "write_audit_event"),
            patch.object(price_proposals, "write_snapshot"),
        ):
            row = price_proposals.create_real_price_proposal(
                session, "product", 10, 132,
                settings=settings(),
                acknowledge_price_warning=True,
                price_at_creation=120,
            )["proposal"]
        source = row["source_row"]
        self.assertEqual(source["price_at_creation"], row["old_price"])
        self.assertEqual(source["proposed_price"], row["new_price"])
        self.assertEqual(source["proposal_price_snapshot"]["price_at_creation"], 120)

    def test_creation_operation_snapshot_keeps_same_price(self):
        session = Session({
            "products": [{"woo_id": 10, "name": "Tatami", "type": "simple", "price": 100}],
            "price_change_proposals": [],
        })
        with (
            patch.object(price_proposals, "write_audit_event"),
            patch.object(price_proposals, "write_snapshot") as snapshot,
        ):
            price_proposals.create_real_price_proposal(
                session, "product", 10, 132,
                settings=settings(),
                acknowledge_price_warning=True,
                price_at_creation=120,
            )
        created_snapshot = snapshot.call_args.args[1]
        self.assertEqual(
            created_snapshot.before_data["proposal_price_snapshot"]["price_at_creation"],
            120,
        )

    def test_source_price_mismatch_blocks_before_write(self):
        session = Session({
            "products": [{"woo_id": 10, "name": "Tatami", "type": "simple", "price": 100}],
            "price_change_proposals": [],
        })
        with self.assertRaisesRegex(CloudAuditError, "price_at_creation"):
            price_proposals.create_real_price_proposal(
                session, "product", 10, 132,
                settings=settings(),
                acknowledge_price_warning=True,
                price_at_creation=120,
                source_row_updates={"price_at_creation": 100},
            )
        self.assertEqual(session.writes, [])

    def test_ui_save_passes_panel_old_price_to_preview_and_create(self):
        line = ProposalLine("10", "Tatami", "120.00", "132.00", "+10%", "up")
        self.app._price_model_put(line, {"item_kind": "product", "woo_id": 10})
        self.app._cloud_session = object()
        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=settings()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                return_value={
                    "old_price": 120,
                    "new_price": 132,
                    "price_safety": {"status": "OK", "messages": []},
                },
            ) as preview,
            patch(
                "futonhub.ui.erp.prototype.create_real_price_proposal",
                return_value={"proposal": {"id": "saved"}},
            ) as create,
        ):
            self.app._price_validate_and_persist_entries(
                self.app._price_model_entries(), "Nueva", "token"
            )
        self.assertEqual(preview.call_args.kwargs["price_at_creation"], 120)
        self.assertEqual(create.call_args.kwargs["price_at_creation"], 120)

    def test_panel_preview_mismatch_blocks_with_zero_writes(self):
        line = ProposalLine("10", "Tatami", "120.00", "132.00", "+10%", "up")
        self.app._price_model_put(line, {"item_kind": "product", "woo_id": 10})
        self.app._cloud_session = object()
        with (
            patch("futonhub.ui.erp.prototype.load_settings", return_value=settings()),
            patch(
                "futonhub.ui.erp.prototype.preview_real_price_proposal",
                return_value={
                    "old_price": 100,
                    "new_price": 132,
                    "price_safety": {"status": "OK", "messages": []},
                },
            ),
            patch("futonhub.ui.erp.prototype.create_real_price_proposal") as create,
        ):
            with self.assertRaisesRegex(ValueError, "integridad de precios"):
                self.app._price_validate_and_persist_entries(
                    self.app._price_model_entries(), "Nueva", "token"
                )
        create.assert_not_called()

    def test_rehydration_prefers_price_at_creation_over_stale_old_price(self):
        proposal = self.app._price_proposal_from_cloud_row({
            "id": "new",
            "item_kind": "product",
            "item_woo_id": 10,
            "old_price": 100,
            "new_price": 110,
            "status": "pending",
            "source_row": {
                "price_at_creation": 120,
                "proposed_price": 132,
                "ui_canonical_item_kind": "product",
                "ui_canonical_woo_id": 10,
            },
        })
        self.assertEqual(proposal.lines[0].old_price, "120.00")
        self.assertEqual(proposal.lines[0].new_price, "132.00")

    def test_rehydration_supports_snapshot_fields(self):
        proposal = self.app._price_proposal_from_cloud_row({
            "id": "new",
            "item_kind": "variation",
            "item_woo_id": 20,
            "old_price": 100,
            "new_price": 110,
            "status": "pending",
            "source_row": {
                "proposal_price_snapshot": {
                    "price_at_creation": 125,
                    "proposed_price": 140,
                },
                "ui_canonical_item_kind": "variation",
                "ui_canonical_woo_id": 20,
            },
        })
        self.assertEqual(proposal.lines[0].old_price, "125.00")
        self.assertEqual(proposal.lines[0].new_price, "140.00")

    def test_historical_row_falls_back_to_old_and_new_price(self):
        proposal = self.app._price_proposal_from_cloud_row({
            "id": "legacy",
            "item_kind": "product",
            "item_woo_id": 10,
            "old_price": 90,
            "new_price": 99,
            "status": "pending",
            "source_row": {},
        })
        self.assertEqual(proposal.lines[0].old_price, "90.00")
        self.assertEqual(proposal.lines[0].new_price, "99.00")

    def test_product_variation_and_pack_rehydrate_independently(self):
        for kind, woo_id, old_price in (
            ("product", 10, 120),
            ("variation", 20, 130),
            ("pack", 20, 140),
        ):
            proposal = self.app._price_proposal_from_cloud_row({
                "id": f"{kind}-{woo_id}",
                "item_kind": kind,
                "item_woo_id": woo_id,
                "old_price": 1,
                "new_price": 2,
                "status": "pending",
                "source_row": {
                    "price_at_creation": old_price,
                    "proposed_price": old_price + 10,
                    "ui_canonical_item_kind": kind,
                    "ui_canonical_woo_id": woo_id,
                },
            })
            self.assertEqual(proposal.lines[0].code, f"{kind}:{woo_id}")
            self.assertEqual(proposal.lines[0].old_price, f"{old_price:.2f}")

    def test_grouping_does_not_mix_same_name_without_shared_identity(self):
        rows = [
            {
                "id": "a", "item_kind": "variation", "item_woo_id": 20,
                "old_price": 120, "new_price": 130, "status": "pending",
                "source_row": {"ui_proposal_name": "Mismo nombre"},
            },
            {
                "id": "b", "item_kind": "pack", "item_woo_id": 20,
                "old_price": 140, "new_price": 150, "status": "pending",
                "source_row": {"ui_proposal_name": "Mismo nombre"},
            },
        ]
        grouped = self.app._price_group_cloud_proposals(rows)
        self.assertEqual(len(grouped), 2)

    def test_sync_service_does_not_update_proposal_history(self):
        source = inspect.getsource(
            woocommerce_publish.sync_price_proposal_inventory_prices
        )
        self.assertNotIn('table("price_change_proposals").update', source)
        self.assertIn("sync_woocommerce_price_inventory_state", source)

    def test_publish_records_distinct_publish_prices(self):
        source = inspect.getsource(
            woocommerce_publish.publish_price_proposal_group
        )
        self.assertIn('"price_before_publish"', source)
        self.assertIn('"published_price"', source)

    def test_restore_records_distinct_restored_price(self):
        source = inspect.getsource(
            woocommerce_publish.restore_price_proposal_group
        )
        self.assertIn('"restored_price"', source)
        self.assertIn('"rolled_back_from_operation_id"', source)

    def test_save_invalidates_inventory_proposal_and_detail_caches(self):
        source = inspect.getsource(FutonHubErpPrototype._finish_price_edit_saved)
        self.assertIn("_invalidate_price_inventory_caches", source)
        self.assertIn("_invalidate_price_proposal_caches", source)
        invalidate = inspect.getsource(
            FutonHubErpPrototype._invalidate_price_proposal_caches
        )
        self.assertIn("_selected_price_proposal = None", invalidate)
        self.assertIn("_price_rendered_model_keys = ()", invalidate)

    def test_publish_and_restore_invalidate_proposal_caches(self):
        publish_ui = inspect.getsource(
            FutonHubErpPrototype._render_price_publish_preview
        )
        restore_ui = inspect.getsource(
            FutonHubErpPrototype._render_price_restore_preview
        )
        self.assertIn("_invalidate_price_proposal_caches", publish_ui)
        self.assertIn("_invalidate_price_proposal_caches", restore_ui)

    def test_refresh_generation_still_discards_stale_response(self):
        source = inspect.getsource(
            FutonHubErpPrototype._finish_price_proposals_refresh
        )
        self.assertIn("generation != active_generation", source)
        self.assertIn("descartado_obsoleto", source)

    def test_action_buttons_use_requested_colors_and_outlines(self):
        source = inspect.getsource(
            FutonHubErpPrototype._render_saved_proposal_detail
        )
        self.assertIn("bg=GREEN", source)
        self.assertIn("bg=ROSE", source)
        self.assertGreaterEqual(source.count("relief=tk.SOLID"), 2)

    def test_action_button_logic_is_unchanged(self):
        source = inspect.getsource(
            FutonHubErpPrototype._render_saved_proposal_detail
        )
        self.assertIn("_open_price_publish_preview(proposal)", source)
        self.assertIn("_open_price_reject_modal(proposal)", source)
        self.assertIn("_open_delete_price_proposal_confirmation(proposal)", source)
        self.assertIn("_open_price_restore_preview(proposal)", source)
        self.assertIn("accept.configure(state=tk.DISABLED)", source)
        self.assertIn("reject.configure(state=tk.DISABLED)", source)

    def test_no_schema_or_dependency_change_required(self):
        service_source = inspect.getsource(price_proposals.create_real_price_proposal)
        self.assertNotIn("ALTER TABLE", service_source)
        self.assertNotIn("requests.", service_source)


if __name__ == "__main__":
    unittest.main()

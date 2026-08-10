from __future__ import annotations

import inspect
import sys
import tkinter as tk
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


class PriceComb001B81ModuleEntrySyncTests(unittest.TestCase):
    def _app(self) -> FutonHubErpPrototype:
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._cloud_session = object()
        app._price_catalog_loading = False
        app._price_catalog_loaded_once = False
        app._price_catalog_items = []
        app._price_catalog_error = ""
        app._price_live_sync_in_progress = False
        app._price_live_sync_completed = False
        app._price_live_sync_required = False
        app._price_loaded_once = True
        app._price_next_refresh_source = ""
        return app

    # 1. Entering Cambio de Precios starts the catalogue workflow before New proposal.
    def test_module_entry_starts_catalog_load_when_session_snapshot_is_absent(self):
        app = self._app()
        calls: list[str] = []
        app._load_price_catalog_for_live_sync = lambda: calls.append("catalog")

        app._maybe_start_price_woo_sync()

        self.assertEqual(calls, ["catalog"])
        self.assertTrue(app._price_live_sync_required)

    # 2. The entry loader uses the complete catalogue, not an active filter query.
    def test_entry_loader_reads_complete_catalogue(self):
        source = inspect.getsource(FutonHubErpPrototype._load_price_catalog_for_live_sync)
        self.assertIn("list_all_cloud_inventory_items", source)
        self.assertIn("reconcile_canonical_catalogue", source)
        self.assertIn("canonical_rows", source)
        self.assertNotIn("search_cloud_inventory_items", source)

    # 3. A completed session context is reused by New proposal without a second GET pass.
    def test_completed_context_is_reused_without_repeat_sync(self):
        app = self._app()
        app._price_catalog_loaded_once = True
        app._price_catalog_items = [object()]
        app._price_live_sync_completed = True
        calls: list[object] = []
        app._price_start_initial_live_sync = lambda items, **kwargs: calls.append((items, kwargs))

        app._maybe_start_price_woo_sync()

        self.assertEqual(calls, [])

    # 4. Returning to the saved list cannot repeat the completed session sync.
    def test_return_to_saved_list_does_not_repeat_get(self):
        source = inspect.getsource(FutonHubErpPrototype._maybe_start_price_woo_sync)
        self.assertIn("_price_live_sync_completed", source)
        self.assertIn("return", source)

    # A global catalogue failure waits for explicit manual refresh instead of looping on redraw.
    def test_catalogue_failure_does_not_restart_automatically(self):
        app = self._app()
        app._price_catalog_error = "Supabase unavailable"
        calls: list[str] = []
        app._load_price_catalog_for_live_sync = lambda: calls.append("catalog")

        app._maybe_start_price_woo_sync()

        self.assertEqual(calls, [])

    # An active worker is the single owner of the session synchronization.
    def test_active_sync_blocks_a_second_concurrent_start(self):
        app = self._app()
        app._price_live_sync_in_progress = True
        calls: list[str] = []
        app._load_price_catalog_for_live_sync = lambda: calls.append("catalog")

        app._maybe_start_price_woo_sync()

        self.assertEqual(calls, [])

    # 5. Returning to the editor reuses the catalogue instead of remote searching.
    def test_editor_filters_reuse_catalogue_snapshot(self):
        source = inspect.getsource(FutonHubErpPrototype._refresh_price_edit_items)
        self.assertIn("_price_catalog_loaded_once", source)
        self.assertIn("_price_catalog_items", source)
        self.assertNotIn("list_all_cloud_inventory_items", source)

    # 6. Manual refresh starts one new complete direct Woo pass.
    def test_manual_refresh_requests_force_full_sync(self):
        app = self._app()
        app._price_catalog_loaded_once = True
        app._price_catalog_items = ["all-items"]
        calls: list[tuple[object, dict]] = []
        app._price_start_initial_live_sync = lambda items, **kwargs: calls.append((items, kwargs))

        app._refresh_price_module(object(), source="manual")

        self.assertEqual(calls, [(["all-items"], {"force_full": True})])
        self.assertFalse(app._price_loaded_once)
        self.assertEqual(app._price_next_refresh_source, "manual")

    # 7. Retry keeps the request limited to recorded error identities.
    def test_retry_passes_retry_only_to_initial_sync(self):
        app = self._app()
        app._price_catalog_items = ["catalogue"]
        calls: list[tuple[object, dict]] = []
        app._price_start_initial_live_sync = lambda items, **kwargs: calls.append((items, kwargs))

        app._price_retry_initial_live_sync()

        self.assertEqual(calls, [(["catalogue"], {"retry_only": True})])

    # 8. A callback after the root is gone is dropped instead of raising TclError.
    def test_navigation_or_shutdown_callback_is_tcl_safe(self):
        app = self._app()

        def destroyed_after(*_args, **_kwargs):
            raise tk.TclError("application has been destroyed")

        app.after = destroyed_after
        app._price_schedule_live_sync_callback(lambda: self.fail("callback should be dropped"))

    # 9. The entry orchestration remains read-only; writes stay outside this path.
    def test_entry_orchestration_contains_no_persistence_write_calls(self):
        source = "\n".join(
            inspect.getsource(method)
            for method in (
                FutonHubErpPrototype._maybe_start_price_woo_sync,
                FutonHubErpPrototype._load_price_catalog_for_live_sync,
                FutonHubErpPrototype._price_start_initial_live_sync,
            )
        )
        for forbidden in (".insert(", ".update(", ".upsert(", ".delete("):
            self.assertNotIn(forbidden, source)

    # 10. Counts remain internal while the popup shows only real progress.
    def test_progress_keeps_real_destination_total_without_technical_labels(self):
        finish = inspect.getsource(FutonHubErpPrototype._finish_initial_live_sync)
        popup = inspect.getsource(FutonHubErpPrototype._price_update_live_sync_overlay)
        self.assertIn('final_counts.get("total", 0)', finish)
        self.assertIn("_price_sync_progress.configure", popup)
        self.assertNotIn("Catalogo fisico", popup)
        self.assertNotIn("destinos Woo", popup)


if __name__ == "__main__":
    unittest.main()

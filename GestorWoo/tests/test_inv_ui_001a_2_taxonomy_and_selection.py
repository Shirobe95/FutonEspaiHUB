from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT / "auditoria"))

from futonhub.cloud.services.inventory import (  # noqa: E402
    INVENTORY_SELECT_COLUMNS,
    list_all_cloud_inventory_items,
)
from futonhub.ui.erp.catalog_filters import VisibleItemSelection  # noqa: E402
from futonhub.ui.erp.inventory_list import ErpInventoryListMixin  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402
from inv_ui_001a_2_taxonomy import classify_cover, classify_futon  # noqa: E402


class _Response:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.data = rows


class _ReadOnlyQuery:
    def __init__(self, rows: list[dict[str, object]], calls: list[tuple[str, object]]) -> None:
        self._rows = rows
        self._calls = calls
        self._range: tuple[int, int] | None = None

    def select(self, columns: str):
        self._calls.append(("select", columns))
        return self

    def order(self, column: str, *, desc: bool = False):
        self._calls.append(("order", (column, desc)))
        return self

    def range(self, start: int, end: int):
        self._range = (start, end)
        self._calls.append(("range", self._range))
        return self

    def execute(self) -> _Response:
        assert self._range is not None
        start, end = self._range
        return _Response([dict(row) for row in self._rows[start : end + 1]])


class _ReadOnlyClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, object]] = []

    def table(self, table_name: str) -> _ReadOnlyQuery:
        self.calls.append(("table", table_name))
        return _ReadOnlyQuery(self.rows, self.calls)


class _Session:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.client = _ReadOnlyClient(rows)


class TaxonomyClassificationTests(unittest.TestCase):
    def test_cover_groups_require_exact_evidence(self) -> None:
        futon = classify_cover({"name": "Funda Futón 90 x 200", "size": "90x200"})
        pillow = classify_cover({"name": "Funda sin texto", "size": "70x40"})
        sofa = classify_cover({"name": "Funda Sofá Cama", "size": "140x200"})

        self.assertEqual("Funda Futón", futon[0])
        self.assertEqual("Funda Almohada", pillow[0])
        self.assertEqual("Funda Sofá", sofa[0])
        self.assertNotEqual("Funda Sofá", futon[0])

    def test_futon_groups_keep_latex_thicknesses_separate(self) -> None:
        cotton = classify_futon({"filter_group": "Algodon", "name": "Futón de algodón"})
        one_latex = classify_futon(
            {
                "filter_group": "Algodón",
                "name": "Futón núcleo látex 4 cm",
                "catalog_range": "1Látex-4-13",
            }
        )
        two_latex = classify_futon(
            {
                "filter_group": "Algodón",
                "name": "Futón Algodón 2 Látex + 2 Cojines",
                "catalog_description": "Dos capas de 4 cm de látex.",
                "catalog_range": "2Látex-8-13",
            }
        )
        ten_latex = classify_futon(
            {
                "filter_group": "Algodón 1 Látex",
                "name": "Futón núcleo látex 10 cm",
                "catalog_range": "10Látex-16",
            }
        )
        fifteen_latex = classify_futon(
            {
                "filter_group": "Algodón 1 Látex",
                "name": "Futón núcleo látex 15 cm",
                "catalog_range": "15Látex-19",
            }
        )

        self.assertEqual("Algodón", cotton[0])
        self.assertEqual("Algodón 1 Látex", one_latex[0])
        self.assertEqual("Algodón 2 Látex", two_latex[0])
        self.assertEqual("Algodón Látex 10 cm", ten_latex[0])
        self.assertEqual("Algodón Látex 15 cm", fifteen_latex[0])


class PaginatedInventoryReadTests(unittest.TestCase):
    def test_loads_beyond_old_limit_with_stable_deduplication_and_no_writes(self) -> None:
        rows = [{"item_id": str(number), "name": f"Item {number}"} for number in range(1, 252)]
        rows.insert(201, {"item_id": "200", "name": "Duplicate 200"})
        session = _Session(rows)

        loaded = list_all_cloud_inventory_items(session, page_size=100)

        self.assertEqual(251, len(loaded))
        self.assertEqual([str(number) for number in range(1, 252)], [row["item_id"] for row in loaded])
        self.assertGreater(len([call for call in session.client.calls if call[0] == "range"]), 2)
        self.assertTrue(all(value == INVENTORY_SELECT_COLUMNS for name, value in session.client.calls if name == "select"))
        self.assertNotIn(("select", "*"), session.client.calls)
        self.assertTrue(all(name in {"table", "select", "order", "range"} for name, _value in session.client.calls))


class VisibleItemSelectionTests(unittest.TestCase):
    def test_selection_is_limited_to_visible_items_after_every_transition(self) -> None:
        selection = VisibleItemSelection()
        self.assertEqual(frozenset(), selection.selected_item_ids)

        selection = selection.with_item("101", True, ["101", "102"])
        self.assertEqual(frozenset({"101"}), selection.selected_item_ids)
        selection = selection.toggle_all_visible(["101", "102"])
        self.assertEqual(frozenset({"101", "102"}), selection.selected_item_ids)

        for visible_ids in (["102"], ["102"], ["201"], ["201"], ["201", "202"]):
            selection = selection.reconcile(visible_ids)
            self.assertTrue(selection.selected_item_ids.issubset(set(visible_ids)))

        self.assertEqual(frozenset(), selection.selected_item_ids)

    def test_sort_keeps_visible_selection_but_page_change_discards_it(self) -> None:
        selection = VisibleItemSelection().toggle_all_visible(["301", "302"])
        self.assertEqual(frozenset({"301", "302"}), selection.reconcile(["302", "301"]).selected_item_ids)
        self.assertEqual(frozenset(), selection.reconcile(["303", "304"]).selected_item_ids)


class PrototypeCandidateSelectionTests(unittest.TestCase):
    def _app(self) -> FutonHubErpPrototype:
        app = FutonHubErpPrototype.__new__(FutonHubErpPrototype)
        app._price_candidate_page_size = 2
        app._price_candidate_page = 0
        app._price_selected_candidate_ids = set()
        app._price_visible_candidate_ids = set()
        app._current_key = ""
        return app

    @staticmethod
    def _results() -> list[dict[str, object]]:
        return [{"key": f"item:{number}", "code": str(number), "name": f"Item {number}"} for number in range(1, 26)]

    def test_page_transition_drops_previous_page_selection_and_payload_is_visible_only(self) -> None:
        app = self._app()
        results = self._results()
        first_page, page, total_pages = app._price_candidate_page_results(results)
        self.assertEqual((0, 3), (page, total_pages))
        app._price_set_candidate_selected(first_page[0], True, first_page)
        self.assertEqual(["item:1"], [app._price_candidate_id(row) for row in app._price_selected_visible_results(first_page)])

        app._price_candidate_page = 1
        second_page, _page, _pages = app._price_candidate_page_results(results)
        self.assertEqual([], app._price_selected_visible_results(second_page))
        self.assertEqual(set(), app._price_selected_candidate_ids)

    def test_header_selection_only_selects_current_page(self) -> None:
        app = self._app()
        results = self._results()
        visible, _page, _pages = app._price_candidate_page_results(results)
        app._price_toggle_all_visible_candidates(visible)
        self.assertEqual({f"item:{number}" for number in range(1, 11)}, app._price_selected_candidate_ids)
        app._price_toggle_all_visible_candidates(visible)
        self.assertEqual(set(), app._price_selected_candidate_ids)

    def test_page_size_change_reconciles_selection_to_new_visible_page(self) -> None:
        app = self._app()
        results = self._results()
        app._price_candidate_page = 1
        second_page, _page, _pages = app._price_candidate_page_results(results)
        app._price_set_candidate_selected(second_page[0], True, second_page)
        app._price_set_candidate_page_size(10)
        visible_after_resize, _page, _pages = app._price_candidate_page_results(results)
        self.assertEqual([], app._price_selected_visible_results(visible_after_resize))
        self.assertEqual(set(), app._price_selected_candidate_ids)


class UiWiringTests(unittest.TestCase):
    def test_inventory_treeview_has_both_synced_scrollbars_and_page_keys(self) -> None:
        source = inspect.getsource(ErpInventoryListMixin._build_inventory)
        self.assertIn("yscrollcommand=vertical_scroll.set", source)
        self.assertIn("xscrollcommand=horizontal_scroll.set", source)
        self.assertIn('tree.bind("<Prior>"', source)
        self.assertIn('tree.bind("<Next>"', source)

    def test_price_picker_uses_checkboxes_and_selected_visible_payload(self) -> None:
        source = inspect.getsource(FutonHubErpPrototype._price_items_pick_list)
        self.assertIn("tk.Checkbutton", source)
        self.assertIn("_price_selected_visible_results", source)
        self.assertIn("Previsualizar seleccionados", source)
        self.assertIn("Anadir seleccionados", source)
        self.assertIn("add_single_result(result)", source)
        self.assertIn("_price_set_candidate_selected(result, True, results)", source)


if __name__ == "__main__":
    unittest.main()

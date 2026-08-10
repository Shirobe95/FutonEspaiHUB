from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_catalog_reconciliation import (  # noqa: E402
    filter_coverage_audit_rows,
    reconcile_canonical_catalogue,
)
from futonhub.services.price_woo_catalog_index import (  # noqa: E402
    build_woo_read_only_index,
    reconcile_woo_contexts,
)
from futonhub.services.price_combination_live_reconciliation import (  # noqa: E402
    _reconciliation_status,
)
from futonhub.ui.erp.catalog_filters import (  # noqa: E402
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    filter_catalog_rows,
)
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


def canonical(item_id: str, sku: str, *, name: str = "Articulo", family: str = "Futones", group: str = "Basic", size: str = "140x200", gama: str = "Natural") -> dict[str, str]:
    return {
        "item_id": item_id,
        "heca_reference": sku,
        "hub_item_code": sku,
        "base_item_code": sku,
        "name": name,
        "item_record_type": "simple",
        "is_pack": "false",
        "filter_family": family,
        "filter_group": group,
        "filter_size": size,
        "filter_gama": gama,
    }


class Snapshot:
    def __init__(self, rows: list[dict[str, str]]):
        self.rows_by_item_id = {row["item_id"]: dict(row) for row in rows}


def product(woo_id: int, sku: str, *, kind: str = "simple", price: str = "99.00") -> dict[str, object]:
    return {
        "id": woo_id,
        "sku": sku,
        "name": f"Woo {sku}",
        "type": kind,
        "status": "publish",
        "regular_price": price,
        "sale_price": "",
        "price": price,
        "date_modified_gmt": "2026-08-06T00:00:00",
    }


class ReadOnlyWoo:
    def __init__(self, products: list[dict[str, object]], variations: dict[int, list[dict[str, object]]] | None = None):
        self.products = products
        self.variations = variations or {}
        self.calls: list[str] = []

    def iter_products(self):
        self.calls.append("products")
        yield from self.products

    def iter_product_variations(self, parent_id: int):
        self.calls.append(f"variations/{parent_id}")
        yield from self.variations.get(parent_id, [])


def sync_row(item_id: str, sku: str, *, local_id: str = "", local_kind: str = "", parent_id: str = "") -> dict[str, object]:
    return {
        "item_id": item_id,
        "physical_item_id": item_id,
        "physical_sku": sku,
        "catalog_live_status": "LIVE",
        "price_operable": True,
        "source": {
            "physical_item_id": item_id,
            "physical_sku": sku,
            "woo_id": local_id,
            "woo_item_kind": local_kind,
            "woo_parent_id": parent_id,
            "item_snapshot": {"item_id": item_id, "item_record_type": "simple", "is_pack": False},
        },
    }


class PriceComb001B83CatalogueReconciliationTests(unittest.TestCase):
    def test_snapshot_has_254_canonical_rows(self):
        self.assertEqual(PhysicalCatalogSnapshot.load().expected_count, 254)
        self.assertEqual(len(PhysicalCatalogSnapshot.load().rows_by_item_id), 254)

    def test_three_missing_live_rows_remain_visible(self):
        snapshot = PhysicalCatalogSnapshot.load()
        canonical_rows = list(snapshot.rows_by_item_id.values())
        live_rows = [dict(row) for row in canonical_rows[:251]]
        result = reconcile_canonical_catalogue(snapshot, live_rows)
        self.assertEqual(result["counts"]["canonical_expected"], 254)
        self.assertEqual(result["counts"]["canonical_missing_live"], 3)
        self.assertEqual(result["counts"]["price_catalogue_visible"], 254)
        self.assertEqual(len(result["missing_live_ids"]), 3)

    def test_woo_not_found_does_not_remove_canonical_filter_row(self):
        snapshot = Snapshot([canonical("101", "00101"), canonical("102", "00102")])
        reconciliation = reconcile_canonical_catalogue(snapshot, [canonical("101", "00101")])
        metadata = {row["item_id"]: row for row in reconciliation["canonical_rows"]}
        contexts = {"101": {"sync_status": "WOO_NOT_FOUND"}, "102": {"sync_status": "CANONICAL_NOT_LIVE"}}
        coverage = filter_coverage_audit_rows(
            reconciliation,
            filter_metadata_by_item_id=metadata,
            visible_item_ids=metadata,
            woo_context_by_item_id=contexts,
        )
        self.assertEqual(len(coverage), 2)
        self.assertEqual(coverage[0]["visible_in_family"], "YES")
        self.assertIn("WOO_NOT_FOUND", coverage[0]["reason"])

    def test_macao_rows_keep_approved_paths_and_search_identity(self):
        snapshot = PhysicalCatalogSnapshot.load()
        rows = [
            snapshot.rows_by_item_id["402014"],
            snapshot.rows_by_item_id["302009"],
        ]
        self.assertEqual(
            [(row["filter_family"], row["filter_group"], row["filter_size"], row["filter_gama"]) for row in rows],
            [("Camas", "Macao", "180x200", "Natural"), ("Bases para Tatamis", "Macao", "180x200", "Natural")],
        )
        self.assertEqual(filter_catalog_rows(rows, CatalogFilterSelection(query="0402014"))[0]["item_id"], "402014")
        self.assertEqual(filter_catalog_rows(rows, CatalogFilterSelection(query="Base Tatami Macao"))[0]["item_id"], "302009")

    def test_valid_local_link_is_verified(self):
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001")]))
        result = reconcile_woo_contexts([sync_row("1", "0201001", local_id="10", local_kind="product")], woo_index=index)
        self.assertEqual(result["live_price_context_by_physical_item"]["1"]["sync_status"], "LOCAL_LINK_VERIFIED")

    def test_broken_local_link_recovers_only_exact_product_sku(self):
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001")]))
        result = reconcile_woo_contexts([sync_row("1", "0201001", local_id="999", local_kind="product")], woo_index=index)
        context = result["live_price_context_by_physical_item"]["1"]
        self.assertEqual(context["sync_status"], "RECOVERED_BY_EXACT_PRODUCT_SKU")
        self.assertEqual(context["session_only"], "YES")

    def test_unique_variation_sku_is_recovered(self):
        variation = product(11, "0402014", price="120.00")
        index = build_woo_read_only_index(ReadOnlyWoo([product(20, "PARENT", kind="variable")], {20: [variation]}))
        result = reconcile_woo_contexts([sync_row("1", "0402014")], woo_index=index)
        context = result["live_price_context_by_physical_item"]["1"]
        self.assertEqual(context["sync_status"], "RECOVERED_BY_EXACT_VARIATION_SKU")
        self.assertEqual(context["woo_parent_id"], "20")

    def test_ambiguous_exact_sku_is_blocked(self):
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001"), product(11, "0201001")]))
        result = reconcile_woo_contexts([sync_row("1", "0201001")], woo_index=index)
        self.assertEqual(result["live_price_context_by_physical_item"]["1"]["sync_status"], "AMBIGUOUS_WOO_LINK")

    def test_private_combination_destination_is_not_published(self):
        status, reason = _reconciliation_status(
            {
                "combination_woo_id": "13092",
                "combination_parent_woo_id": "3658",
                "combination_sku": "0206001",
                "modified_components": [{"quantity": "1"}],
            },
            {
                "id": 13092,
                "parent_id": 3658,
                "sku": "0206001",
                "status": "private",
                "regular_price": "99.00",
                "price": "99.00",
            },
            "",
            duplicate=False,
        )
        self.assertEqual(status, "NOT_PUBLISHED")
        self.assertIn("private", reason)

    def test_suffixes_and_leading_zeroes_are_not_normalized_or_fuzzy_matched(self):
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001-A"), product(11, "201001")]))
        result = reconcile_woo_contexts([sync_row("1", "0201001"), sync_row("2", "0201001-A"), sync_row("3", "0201001")], woo_index=index)
        contexts = result["live_price_context_by_physical_item"]
        self.assertEqual(contexts["1"]["sync_status"], "WOO_NOT_FOUND")
        self.assertEqual(contexts["2"]["sync_status"], "RECOVERED_BY_EXACT_PRODUCT_SKU")
        self.assertEqual(contexts["3"]["physical_sku"], "0201001")

    def test_index_and_reconciliation_contain_no_write_path(self):
        source = "\n".join((
            inspect.getsource(build_woo_read_only_index),
            inspect.getsource(reconcile_woo_contexts),
        ))
        for forbidden in (".put(", ".post(", ".update(", ".insert(", ".delete("):
            self.assertNotIn(forbidden, source)

    def test_popup_is_resizable_and_shows_only_real_progress(self):
        source = inspect.getsource(FutonHubErpPrototype._price_start_live_sync_overlay)
        self.assertIn("resizable(True, True)", source)
        self.assertIn("maxsize", source)
        self.assertIn("Progressbar", source)
        self.assertIn("Cargando precios...", source)
        self.assertNotIn("counter_canvas", source)
        self.assertNotIn("catalog_physical", source)

    def test_preview_is_one_parent_child_tree_not_a_flat_direct_list(self):
        source = inspect.getsource(FutonHubErpPrototype._open_price_item_impact_popup)
        self.assertNotIn("direct_tree", source)
        self.assertIn('show="tree headings"', source)
        self.assertIn('text=f"DIRECTO:', source)
        self.assertIn("add_impact(parent_item", source)

    def test_unlinked_physical_rows_cannot_collapse_to_one_result(self):
        source = inspect.getsource(FutonHubErpPrototype._price_result_key)
        self.assertIn('return f"physical:', source)


if __name__ == "__main__":
    unittest.main()

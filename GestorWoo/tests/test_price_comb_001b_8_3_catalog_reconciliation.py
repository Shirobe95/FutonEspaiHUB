from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_catalog_reconciliation import (  # noqa: E402
    classify_price_proposal_catalogue_row,
    filter_coverage_audit_rows,
    price_proposal_selectable_catalogue_rows,
    reconcile_canonical_catalogue,
)
from futonhub.services.price_woo_only_sources import (  # noqa: E402
    build_approved_woo_only_price_source_rows,
    is_approved_woo_only_price_source_row,
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


def sync_row(
    item_id: str,
    sku: str,
    *,
    local_id: str = "",
    local_kind: str = "",
    parent_id: str = "",
    local_woo_sku: str = "",
) -> dict[str, object]:
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
            "woo_sku": local_woo_sku,
            "item_snapshot": {"item_id": item_id, "item_record_type": "simple", "is_pack": False},
        },
    }


def woo_only_mirror(
    sku: str,
    item_id: str,
    woo_id: str,
    *,
    parent_id: str = "3631",
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "item_record_type": "woo_item",
        "woo_id": woo_id,
        "woo_parent_id": parent_id,
        "parent_woo_id": parent_id,
        "woo_item_kind": "variation",
        "woo_sku": sku,
        "sku": sku,
        "status": "publish",
        "commercial_status": "Activo",
        "price": "71.00",
        "regular_price": "71.00",
        "sale_price": "",
    }


def live_variation(woo_id: int, parent_id: int, sku: str, *, price: str = "71.00") -> dict[str, object]:
    row = product(woo_id, sku, kind="variation", price=price)
    row.update({
        "parent_id": parent_id,
        "purchasable": True,
        "stock_status": "instock",
        "manage_stock": False,
    })
    return row


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

    def test_approved_tatami_portable_combination_links_are_verified(self):
        variations = {
            3657: [
                product(4558, "0201011|0808001", price="232.00"),
                product(4561, "0201011|0816001", price="232.00"),
            ]
        }
        index = build_woo_read_only_index(ReadOnlyWoo([product(3657, "", kind="variable")], variations))
        result = reconcile_woo_contexts(
            [
                sync_row(
                    "208001",
                    "0208001",
                    local_id="4558",
                    local_kind="variation",
                    parent_id="3657",
                    local_woo_sku="0201011|0808001",
                ),
                sync_row(
                    "216001",
                    "0216001",
                    local_id="4561",
                    local_kind="variation",
                    parent_id="3657",
                    local_woo_sku="0201011|0816001",
                ),
            ],
            woo_index=index,
        )
        contexts = result["live_price_context_by_physical_item"]
        self.assertEqual(contexts["208001"]["sync_status"], "LOCAL_LINK_VERIFIED")
        self.assertEqual(contexts["208001"]["resolution_source"], "APPROVED_LOCAL_COMBINATION_LINK")
        self.assertEqual(contexts["208001"]["woo_sku"], "0201011|0808001")
        self.assertEqual(contexts["216001"]["sync_status"], "LOCAL_LINK_VERIFIED")
        self.assertEqual(contexts["216001"]["resolution_source"], "APPROVED_LOCAL_COMBINATION_LINK")
        self.assertEqual(contexts["216001"]["woo_sku"], "0201011|0816001")

    def test_unapproved_combination_sku_local_link_still_requires_recovery(self):
        variations = {3657: [product(4558, "0201011|0808001", price="232.00")]}
        index = build_woo_read_only_index(ReadOnlyWoo([product(3657, "", kind="variable")], variations))
        result = reconcile_woo_contexts(
            [
                sync_row(
                    "999001",
                    "0999001",
                    local_id="4558",
                    local_kind="variation",
                    parent_id="3657",
                    local_woo_sku="0201011|0808001",
                )
            ],
            woo_index=index,
        )
        self.assertEqual(result["live_price_context_by_physical_item"]["999001"]["sync_status"], "LINK_RECOVERY_REQUIRED")

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

    def test_private_combination_destination_with_effective_price_is_price_ready(self):
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
        self.assertEqual(status, "VALID")
        self.assertIn("Validacion live exacta completada", reason)

    def test_suffixes_and_leading_zeroes_are_not_normalized_or_fuzzy_matched(self):
        index = build_woo_read_only_index(ReadOnlyWoo([product(10, "0201001-A"), product(11, "201001")]))
        result = reconcile_woo_contexts([sync_row("1", "0201001"), sync_row("2", "0201001-A"), sync_row("3", "0201001")], woo_index=index)
        contexts = result["live_price_context_by_physical_item"]
        self.assertEqual(contexts["1"]["sync_status"], "WOO_NOT_FOUND")
        self.assertEqual(contexts["2"]["sync_status"], "RECOVERED_BY_EXACT_PRODUCT_SKU")
        self.assertEqual(contexts["3"]["physical_sku"], "0201001")

    def test_approved_woo_only_fundas_are_promoted_only_to_price_selector(self):
        rows = build_approved_woo_only_price_source_rows([
            woo_only_mirror("0619005", "930000009907", "9907"),
            woo_only_mirror("0619006", "930000009908", "9908"),
            woo_only_mirror("0619007", "930000009999", "9999"),
        ])

        self.assertEqual([row["hub_item_code"] for row in rows], ["0619005", "0619006"])
        by_sku = {row["hub_item_code"]: row for row in rows}
        self.assertEqual(by_sku["0619005"]["filter_family"], "Fundas")
        self.assertEqual(by_sku["0619005"]["filter_group"], "Funda Futón")
        self.assertEqual(by_sku["0619005"]["filter_size"], "140x200x8")
        self.assertEqual(by_sku["0619005"]["filter_gama"], "Crudo")
        self.assertEqual(by_sku["0619005"]["inventory_visible"], "NO")
        self.assertEqual(by_sku["0619006"]["filter_gama"], "Negro")
        self.assertEqual(len(price_proposal_selectable_catalogue_rows(rows)), 2)
        self.assertTrue(is_approved_woo_only_price_source_row(by_sku["0619005"]))
        self.assertNotIn("930000009907", PhysicalCatalogSnapshot.load().rows_by_item_id)

    def test_unapproved_woo_mirror_is_not_a_price_source(self):
        row = woo_only_mirror("0616007", "616007", "3804")

        classification, reason = classify_price_proposal_catalogue_row(row)

        self.assertFalse(price_proposal_selectable_catalogue_rows([row]))
        self.assertEqual(classification, "WOO_MIRROR_NOT_PRICE_SOURCE")
        self.assertIn("Mirror Woo", reason)

    def test_approved_woo_only_fundas_require_exact_live_variation(self):
        rows = build_approved_woo_only_price_source_rows([
            woo_only_mirror("0619005", "930000009907", "9907"),
            woo_only_mirror("0619006", "930000009908", "9908"),
        ])
        index = build_woo_read_only_index(ReadOnlyWoo(
            [product(3631, "", kind="variable")],
            {
                3631: [
                    live_variation(9907, 3631, "0619005"),
                    live_variation(9908, 3631, "0619006"),
                ]
            },
        ))

        result = reconcile_woo_contexts(rows, woo_index=index)
        contexts = result["live_price_context_by_physical_item"]

        self.assertEqual(contexts["930000009907"]["sync_status"], "PRICE_SOURCE_WOO_ONLY_VERIFIED")
        self.assertEqual(contexts["930000009907"]["resolution_source"], "PRICE_SOURCE_WOO_ONLY")
        self.assertEqual(contexts["930000009907"]["effective_price"], "71.00")
        self.assertEqual(contexts["930000009907"]["publish_target_field"], "sale_price")
        self.assertEqual(contexts["930000009908"]["sync_status"], "PRICE_SOURCE_WOO_ONLY_VERIFIED")

    def test_approved_woo_only_fundas_block_duplicate_live_sku(self):
        rows = build_approved_woo_only_price_source_rows([
            woo_only_mirror("0619005", "930000009907", "9907"),
        ])
        index = build_woo_read_only_index(ReadOnlyWoo(
            [product(3631, "", kind="variable"), product(9999, "0619005", price="71.00")],
            {3631: [live_variation(9907, 3631, "0619005")]},
        ))

        result = reconcile_woo_contexts(rows, woo_index=index)

        self.assertEqual(result["live_price_context_by_physical_item"]["930000009907"]["sync_status"], "AMBIGUOUS_WOO_LINK")

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

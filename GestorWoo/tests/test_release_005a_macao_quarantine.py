from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_initial_live_sync import sync_initial_live_prices  # noqa: E402
from futonhub.ui.erp.catalog_filters import CatalogFilterSelection, filter_catalog_rows  # noqa: E402


class _ReadOnlyWoo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def get(self, endpoint: str, params: object = None) -> None:
        self.calls.append((endpoint, params))
        raise AssertionError("0402014 must not trigger a Woo read without an exact link.")


def _macao_row() -> dict[str, object]:
    return {
        "code": "0402014",
        "name": "Cama Macao, 180 x 200 cm, Natural",
        "cached_price": "",
        "source": {
            "physical_item_id": "402014",
            "physical_sku": "0402014",
            "price_operable": True,
            "item_snapshot": {
                "item_id": "402014",
                "hub_item_code": "0402014",
                "item_record_type": "simple",
                "is_pack": False,
            },
        },
    }


class Release005AMacaoQuarantineTests(unittest.TestCase):
    def test_macao_is_visible_but_has_no_automatic_woo_price_target(self) -> None:
        macao = _macao_row()
        base = {
            "physical_sku": "0302009",
            "hub_item_code": "0302009",
            "name": "Base para Tatami Macao, 180 x 200 cm, Natural",
        }
        visible = filter_catalog_rows(
            [
                {"physical_sku": "0402014", "hub_item_code": "0402014", "name": macao["name"]},
                base,
            ],
            CatalogFilterSelection(query="0402014"),
        )
        self.assertEqual([row["physical_sku"] for row in visible], ["0402014"])

        woo = _ReadOnlyWoo()
        result = sync_initial_live_prices([macao], woo_client=woo, session=None)
        context = result["live_price_context_by_physical_item"]["402014"]

        self.assertEqual(macao["source"]["item_snapshot"]["item_record_type"], "simple")
        self.assertFalse(macao["source"]["item_snapshot"]["is_pack"])
        self.assertEqual(context["physical_sku"], "0402014")
        self.assertEqual(context["sync_status"], "NO_WOO_LINK")
        self.assertEqual(context["price_change_eligible"], "NO")
        self.assertEqual(context["woo_id"], "")
        self.assertNotEqual(context["woo_id"], "3661")
        self.assertEqual(woo.calls, [])
        self.assertEqual(result["writes"], {"woo": 0, "supabase": 0, "sql": 0})


if __name__ == "__main__":
    unittest.main()

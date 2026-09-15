from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.cloud.services.woocommerce_publish import (  # noqa: E402
    _effective_woo_price,
    _pricing_payload_for_effective_price,
    _pricing_payload_for_proposal_effective_price,
)


class WooEffectivePriceTests(unittest.TestCase):
    def test_sale_price_is_effective_when_active(self) -> None:
        price = _effective_woo_price(
            {
                "regular_price": "150.00",
                "sale_price": "128.00",
                "price": "128.00",
            }
        )

        self.assertEqual(price, 128.0)

    def test_regular_price_is_effective_without_active_sale_price(self) -> None:
        for sale_price in ("", "0", None):
            with self.subTest(sale_price=sale_price):
                price = _effective_woo_price(
                    {
                        "regular_price": "150.00",
                        "sale_price": sale_price,
                        "price": "140.00",
                    }
                )

                self.assertEqual(price, 150.0)

    def test_price_field_is_fallback_when_regular_and_sale_are_empty(self) -> None:
        price = _effective_woo_price(
            {
                "regular_price": "",
                "sale_price": "",
                "price": "99.95",
            }
        )

        self.assertEqual(price, 99.95)


class WooPricingPayloadTests(unittest.TestCase):
    def test_active_sale_below_regular_updates_sale_price_only(self) -> None:
        payload, target = _pricing_payload_for_effective_price(
            {"regular_price": "150.00", "sale_price": "128.00"},
            138.0,
        )

        self.assertEqual(payload, {"sale_price": "138.00"})
        self.assertEqual(target, "sale_price")

    def test_active_sale_at_or_above_regular_becomes_regular_price_and_clears_sale(self) -> None:
        payload, target = _pricing_payload_for_effective_price(
            {"regular_price": "150.00", "sale_price": "128.00"},
            155.0,
        )

        self.assertEqual(payload, {"regular_price": "155.00", "sale_price": ""})
        self.assertEqual(target, "regular_price")

    def test_without_active_sale_updates_regular_price_and_clears_sale(self) -> None:
        for sale_price in ("", "0", None):
            with self.subTest(sale_price=sale_price):
                payload, target = _pricing_payload_for_effective_price(
                    {"regular_price": "150.00", "sale_price": sale_price},
                    138.0,
                )

                self.assertEqual(payload, {"regular_price": "138.00", "sale_price": ""})
                self.assertEqual(target, "regular_price")

    def test_woo_only_price_source_writes_sale_price_when_below_regular_price(self) -> None:
        proposal = {
            "source_row": {
                "price_source_woo_only": "YES",
                "price_source_mode": "PRICE_SOURCE_WOO_ONLY",
                "publish_target_field": "sale_price",
                "physical_item_id": "930000009907",
                "physical_sku": "0619005",
                "item_snapshot": {
                    "item_id": "930000009907",
                    "item_record_type": "woo_item",
                    "hub_item_code": "0619005",
                    "woo_id": "9907",
                    "woo_parent_id": "3631",
                    "woo_item_kind": "variation",
                    "woo_sku": "0619005",
                },
            }
        }

        payload, target = _pricing_payload_for_proposal_effective_price(
            proposal,
            {"regular_price": "90.00", "sale_price": "", "price": "90.00"},
            83.78,
        )

        self.assertEqual(payload, {"sale_price": "83.78"})
        self.assertEqual(target, "sale_price")

    def test_woo_only_price_source_uses_regular_price_when_sale_would_not_be_effective(self) -> None:
        proposal = {
            "source_row": {
                "price_source_woo_only": "YES",
                "price_source_mode": "PRICE_SOURCE_WOO_ONLY",
                "publish_target_field": "sale_price",
                "physical_item_id": "930000009907",
                "physical_sku": "0619005",
                "item_snapshot": {
                    "item_id": "930000009907",
                    "item_record_type": "woo_item",
                    "hub_item_code": "0619005",
                    "woo_id": "9907",
                    "woo_parent_id": "3631",
                    "woo_item_kind": "variation",
                    "woo_sku": "0619005",
                },
            }
        }

        payload, target = _pricing_payload_for_proposal_effective_price(
            proposal,
            {"regular_price": "71.00", "sale_price": "", "price": "71.00"},
            83.78,
        )

        self.assertEqual(payload, {"regular_price": "83.78", "sale_price": ""})
        self.assertEqual(target, "regular_price")


if __name__ == "__main__":
    unittest.main()


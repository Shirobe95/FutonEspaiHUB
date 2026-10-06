"""W3: el umbral de bajada del preview de grupo se compara con el precio vivo de Woo,
no con el espejo (cloud_item) de Supabase."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "src"))

import test_characterization_price_proposal_publication_group as base  # noqa: E402
from futonhub.cloud.services import woocommerce_publish  # noqa: E402


def target(cloud_price):
    return {
        "remote_key": "product:10", "endpoint": "products/10", "woo_id": 10, "remote_kind": "product",
        "canonical_key": "product:10", "cloud_item": {"price": cloud_price, "regular_price": cloud_price},
    }


class GroupDropThresholdTests(unittest.TestCase):
    def preview(self, *, mirror_price, woo_price, new_price):
        row = base.proposal("p", "product", 10, old_price=woo_price, new_price=new_price)
        woo = base.Woo({"products/10": [{"id": 10, "price": str(woo_price), "regular_price": str(woo_price), "sale_price": ""}]})
        with patch.object(woocommerce_publish, "_remote_target_for_proposal", return_value=target(mirror_price)):
            return woocommerce_publish.preview_price_proposal_group_publish(
                base.Session([row]), proposal_ids=["p"], settings=base.settings(), client=woo
            )["rows"][0]

    def test_stale_low_mirror_does_not_hide_a_big_drop_in_woo(self) -> None:
        row = self.preview(mirror_price=15, woo_price=100, new_price=20)  # -80 % frente a Woo
        self.assertEqual(row["status"], "NO PUBLICABLE")
        self.assertIn("80.00%", row["reason"])

    def test_stale_high_mirror_does_not_block_a_small_drop_in_woo(self) -> None:
        row = self.preview(mirror_price=300, woo_price=100, new_price=90)  # -10 % frente a Woo
        self.assertEqual(row["status"], "VALIDO")

    def test_warning_threshold_uses_woo_price(self) -> None:
        row = self.preview(mirror_price=100, woo_price=100, new_price=60)  # -40 %: aviso (30 %) pero no bloqueo (60 %)
        self.assertEqual(row["status"], "WARNING")


if __name__ == "__main__":
    unittest.main()

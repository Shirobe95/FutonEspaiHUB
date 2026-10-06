"""U5: con el catálogo vacío el editor de precios no puede reprogramarse en bucle."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp.prototype import FutonHubErpPrototype as P  # noqa: E402


class Shell:
    pass


class RenderLoopTests(unittest.TestCase):
    def test_reuse_is_claimed_once_per_catalog_generation(self) -> None:
        shell = Shell()
        shell._price_catalog_generation = 3
        self.assertTrue(P._price_edit_claim_catalog_reuse(shell))
        for _ in range(5):  # los siguientes renders de la misma generación no reprograman
            self.assertFalse(P._price_edit_claim_catalog_reuse(shell))

    def test_new_catalog_generation_allows_one_more_reuse(self) -> None:
        shell = Shell()
        shell._price_catalog_generation = 1
        self.assertTrue(P._price_edit_claim_catalog_reuse(shell))
        shell._price_catalog_generation = 2
        self.assertTrue(P._price_edit_claim_catalog_reuse(shell))
        self.assertFalse(P._price_edit_claim_catalog_reuse(shell))


if __name__ == "__main__":
    unittest.main()

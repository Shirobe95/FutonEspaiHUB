"""U5: «Previsualizar seleccionados» no puede rechazar con ``float(None)`` los Simples físicos."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp.prototype import FutonHubErpPrototype as P  # noqa: E402


class Shell:
    """Ejecuta los métodos reales de la ventana sin construir Tk."""

    _price_proposal_model: dict = {}
    _price_live_sync_required = False
    _price_search_query = "x"
    _price_combination_impact_service_cache = None

    def __getattr__(self, name):
        if name.startswith("_price_") and not hasattr(P, name):
            raise AttributeError(name)
        return types.MethodType(getattr(P, name), self)

    def _price_model_entries(self):
        return []


def result(price):
    return {
        "key": "k1", "code": "A1", "name": "Funda", "type": "Simple", "item": None, "price": price,
        "source": {"physical_item_id": "7", "physical_sku": "A1", "price_sync_status": "OK"},
    }


class BulkPreviewTests(unittest.TestCase):
    def row(self, price, percent="", exact="10"):
        return Shell()._price_build_bulk_preview([result(price)], percent, exact)["rows"][0]

    def test_simple_physical_with_live_price_is_calculated(self) -> None:
        row = self.row("100.00", percent="10", exact="")
        self.assertEqual(row["status"], "VALIDO", row["reason"])
        self.assertAlmostEqual(row["old_price_value"], 100.0)
        self.assertAlmostEqual(row["new_price_value"], 110.0)

    def test_simple_physical_without_price_gets_a_clear_error_not_a_python_error(self) -> None:
        row = self.row("")
        self.assertEqual(row["status"], "ERROR")
        self.assertIn("Precio Woo pendiente", row["reason"])
        self.assertNotIn("NoneType", row["reason"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from futonhub.ui.erp.formula_library import (  # noqa: E402
    FORMULA_CATEGORIES,
    FORMULA_LIBRARY,
    FORMULA_PROVIDER_FILTERS,
    FormulaRecord,
    formula_records,
    formula_summary,
    normalize_formula_provider,
    render_formula_library_html,
)


class FormulaLibraryContractTests(unittest.TestCase):
    def test_required_scope_is_covered(self) -> None:
        categories = {record.category for record in FORMULA_LIBRARY}

        self.assertEqual(categories, {"Pedidos", "Inventario", "Woo Precios", "Otros"})
        self.assertEqual(FORMULA_CATEGORIES[0], "Todas")

    def test_records_are_immutable_and_keys_are_unique(self) -> None:
        self.assertEqual(len({record.key for record in FORMULA_LIBRARY}), len(FORMULA_LIBRARY))
        with self.assertRaises(FrozenInstanceError):
            FORMULA_LIBRARY[0].name = "Cambio no permitido"  # type: ignore[misc]

    def test_active_and_auxiliary_formulas_have_traceable_sources(self) -> None:
        for record in FORMULA_LIBRARY:
            if record.status == "PREVISTA":
                continue
            with self.subTest(formula=record.key):
                source = PROJECT_ROOT / record.source_path
                self.assertTrue(record.expression)
                self.assertTrue(source.is_file(), source)
                self.assertTrue(record.source_symbol)
                self.assertTrue(record.conditions)
                self.assertIn(record.source_symbol, source.read_text(encoding="utf-8"))

    def test_authoritative_sales_margin_formula_is_documented_literally(self) -> None:
        record = next(item for item in FORMULA_LIBRARY if item.key == "pvp_margen_venta")

        self.assertEqual(record.expression, "pvp_unitario = coste_base / (1 - margen_percent / 100)")
        self.assertEqual(record.source_symbol, "_supplier_order_pvp_decimal")

    def test_category_filter_and_summary_are_deterministic(self) -> None:
        summary = formula_summary()

        self.assertEqual(summary["total"], len(FORMULA_LIBRARY))
        self.assertEqual(summary["total"], summary["active"] + summary["auxiliary"] + summary["future"])
        self.assertTrue(all(record.category == "Inventario" for record in formula_records("Inventario")))

    def test_supplier_order_formulas_are_filterable_by_provider_without_duplication(self) -> None:
        self.assertEqual(FORMULA_PROVIDER_FILTERS, ("Todos", "Comunes", "Ekomat", "Pascal", "Hemei", "Cipta"))

        pedidos = formula_records("Pedidos")
        self.assertTrue(pedidos)
        self.assertTrue(all(record.providers for record in pedidos))
        self.assertEqual(len({record.key for record in pedidos}), len(pedidos))

        comunes = {record.key for record in formula_records("Pedidos", "Comunes")}
        ekomat = {record.key for record in formula_records("Pedidos", "Ekomat")}
        pascal = {record.key for record in formula_records("Pedidos", "Pascal")}
        hemei = {record.key for record in formula_records("Pedidos", "Hemei")}
        cipta = {record.key for record in formula_records("Pedidos", "Cipta")}
        heimei_alias = {record.key for record in formula_records("Pedidos", "Heimei")}

        self.assertIn("pvp_margen_venta", comunes)
        self.assertIn("coste_final_general", ekomat)
        self.assertIn("coste_final_general", pascal)
        self.assertIn("heimei_coste_final", hemei)
        self.assertIn("heimei_coste_final", cipta)
        self.assertNotIn("heimei_coste_final", ekomat)
        self.assertNotIn("coste_final_general", hemei)
        self.assertEqual(heimei_alias, hemei)
        self.assertEqual(normalize_formula_provider("Heimei"), "Hemei")

    def test_erp_view_contains_no_editable_text_controls_or_write_services(self) -> None:
        source = (ROOT / "src" / "futonhub" / "ui" / "erp" / "formula_library.py").read_text(encoding="utf-8")

        for forbidden in ("tk.Entry", "tk.Text", "ttk.Entry", "ttk.Combobox", "update_inventory_item_fields", "save_business_constants"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_html_is_mobile_ready_and_contains_no_formula_edit_fields(self) -> None:
        html = render_formula_library_html()

        self.assertIn('name="viewport"', html)
        self.assertIn("Biblioteca de Fórmulas", html)
        self.assertNotIn("<input", html)
        self.assertNotIn("<textarea", html)
        self.assertEqual(html.count('class="formula-card"'), len(FORMULA_LIBRARY))

    def test_formula_record_type_is_explicit(self) -> None:
        self.assertIsInstance(FORMULA_LIBRARY[0], FormulaRecord)


if __name__ == "__main__":
    unittest.main()

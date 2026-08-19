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
    PROTOTYPE_SOURCE,
    FormulaRecord,
    formula_provider_sections,
    formula_records,
    formula_sections,
    formula_summary,
    formula_usage_text,
    normalize_formula_provider,
    render_formula_library_html,
)


class FormulaLibraryContractTests(unittest.TestCase):
    def test_required_scope_is_covered(self) -> None:
        categories = {record.category for record in FORMULA_LIBRARY}

        self.assertEqual(
            categories,
            {"Pedidos", "Inventario", "Cambio de Precios", "Combinaciones Woo", "Recepción", "Otros"},
        )
        self.assertEqual(
            FORMULA_CATEGORIES,
            ("Todas", "Pedidos", "Inventario", "Cambio de Precios", "Combinaciones Woo", "Recepción", "Otros"),
        )

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
        self.assertTrue(all("Inventario" in record.usage_areas for record in formula_records("Inventario")))

    def test_supplier_order_formulas_are_filterable_by_provider_without_duplication(self) -> None:
        self.assertEqual(FORMULA_PROVIDER_FILTERS, ("Todos", "Ekomat", "Pascal", "Hemei", "Cipta", "Comunes"))

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
        self.assertIn("inventario_coste_ponderado", comunes)

    def test_supplier_order_provider_sections_project_common_formulas(self) -> None:
        for provider in ("Ekomat", "Pascal", "Hemei", "Cipta"):
            with self.subTest(provider=provider):
                sections = formula_provider_sections(provider)
                section_titles = [title for title, _records in sections]
                projected_records = [record for _title, records in sections for record in records]

                self.assertTrue(any(provider in title for title in section_titles))
                self.assertTrue(any(title.startswith("Comunes utilizadas") for title in section_titles))
                self.assertEqual(len(projected_records), len({record.key for record in projected_records}))
                self.assertIn("pvp_margen_venta", {record.key for record in projected_records})

    def test_usage_area_sections_are_separated_by_real_workflow(self) -> None:
        all_sections = dict(formula_sections("Todas"))

        for expected in ("Pedidos", "Inventario", "Cambio de Precios", "Combinaciones Woo", "Recepción", "Otros"):
            with self.subTest(section=expected):
                self.assertIn(expected, all_sections)

        direct_price = {record.key for record in formula_records("Cambio de Precios")}
        woo_combinations = {record.key for record in formula_records("Combinaciones Woo")}
        reception = {record.key for record in formula_records("Recepción")}

        self.assertIn("woo_delta_precio", direct_price)
        self.assertNotIn("woo_combination_simulated_price", direct_price)
        self.assertIn("woo_combination_simulated_price", woo_combinations)
        self.assertIn("inventario_stock_recepcion", reception)

    def test_download_formula_is_dynamic_and_separate_from_iva_re(self) -> None:
        descarga = next(record for record in FORMULA_LIBRARY if record.key == "descarga_coste_producto")
        iva_re = next(record for record in FORMULA_LIBRARY if record.key == "iva_recargo_equivalencia")

        self.assertEqual(descarga.expression, "descarga_unidad = round(coste_descarga_iva / unidades_que_reparten_descarga, 2)")
        self.assertIn("Se recalcula para cada pedido", descarga.notes)
        self.assertNotIn("COSTE_DESCARGA_FUTONES_UNIDAD", descarga.expression + descarga.notes)
        self.assertEqual(iva_re.expression, "iva_re = round(precio_proveedor * factor_iva_re, 2)")
        self.assertIn("factor fiscal independiente", iva_re.notes)

    def test_erp_view_contains_no_editable_text_controls_or_write_services(self) -> None:
        source = (ROOT / "src" / "futonhub" / "ui" / "erp" / "formula_library.py").read_text(encoding="utf-8")

        for forbidden in ("tk.Entry", "tk.Text", "ttk.Entry", "ttk.Combobox", "update_inventory_item_fields", "save_business_constants"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_html_is_mobile_ready_and_contains_no_formula_edit_fields(self) -> None:
        html = render_formula_library_html()

        self.assertIn('name="viewport"', html)
        self.assertIn("Biblioteca de Fórmulas", html)
        self.assertIn("provider-guide", html)
        self.assertIn("USADO EN", html)
        self.assertIn("Cambio de Precios", html)
        self.assertIn("Combinaciones Woo", html)
        self.assertIn("@media (max-width: 900px)", html)
        self.assertIn("overflow-x: auto", html)
        self.assertIn("overflow-wrap: anywhere", html)
        self.assertNotIn("<input", html)
        self.assertNotIn("<textarea", html)
        self.assertEqual(html.count('class="formula-card"'), len(FORMULA_LIBRARY))
        self.assertEqual(html.count("data-record-key="), len(FORMULA_LIBRARY))

    def test_formula_usage_chips_are_documented_without_changing_sources(self) -> None:
        record = next(item for item in FORMULA_LIBRARY if item.key == "heimei_coste_final")

        self.assertEqual(record.calculation_family, "import_usd_eur")
        self.assertIn("Pedidos / Hemei, Cipta", formula_usage_text(record))
        self.assertEqual(record.source_path, PROTOTYPE_SOURCE)
        self.assertEqual(record.source_symbol, "_calculate_supplier_order_in_memory")

    def test_formula_record_type_is_explicit(self) -> None:
        self.assertIsInstance(FORMULA_LIBRARY[0], FormulaRecord)


if __name__ == "__main__":
    unittest.main()

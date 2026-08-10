from __future__ import annotations

from dataclasses import dataclass
from html import escape
import tkinter as tk
from typing import Iterable

from futonhub.ui.erp.shared_ui import (
    AMBER,
    AMBER_SOFT,
    BG,
    BLUE,
    BLUE_SOFT,
    CARD,
    GREEN,
    GREEN_SOFT,
    INDIGO,
    INDIGO_SOFT,
    LINE,
    MUTED,
    SOFT,
    TEXT,
)


@dataclass(frozen=True)
class FormulaRecord:
    key: str
    category: str
    name: str
    status: str
    purpose: str
    expression: str
    variables: tuple[str, ...]
    units: str
    module: str
    source_path: str
    source_symbol: str
    conditions: str = "Validaciones y casos límite definidos por el método fuente."
    notes: str = ""


def _formula(
    key: str,
    category: str,
    name: str,
    expression: str,
    variables: tuple[str, ...],
    units: str,
    module: str,
    source_path: str,
    source_symbol: str,
    *,
    purpose: str,
    status: str = "ACTIVA",
    conditions: str = "Validaciones y casos límite definidos por el método fuente.",
    notes: str = "",
) -> FormulaRecord:
    return FormulaRecord(
        key=key,
        category=category,
        name=name,
        status=status,
        purpose=purpose,
        expression=expression,
        variables=variables,
        units=units,
        module=module,
        source_path=source_path,
        source_symbol=source_symbol,
        conditions=conditions,
        notes=notes,
    )


PROTOTYPE_SOURCE = "GestorWoo/src/futonhub/ui/erp/prototype.py"
LEGACY_ORDER_SOURCE = "CalculoCoste/coste_pedido.py"
ORDERS_SOURCE = "GestorWoo/src/futonhub/cloud/services/orders.py"
PRICE_PROPOSALS_SOURCE = "GestorWoo/src/futonhub/cloud/services/price_proposals.py"
COMBINATION_PRICE_SOURCE = "GestorWoo/src/futonhub/services/combination_price_impact.py"


FORMULA_LIBRARY: tuple[FormulaRecord, ...] = (
    _formula(
        "pedido_m3_linea",
        "Pedidos",
        "M3 total de linea",
        "m3_total_linea = round(m3_unidad * cantidad, 6)",
        ("m3_unidad", "cantidad"),
        "m3",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Obtiene el volumen total de una linea cuando el pedido aporta M3 por unidad.",
    ),
    _formula(
        "pedido_coste_total_linea",
        "Pedidos",
        "Coste total de linea",
        "coste_linea = round(coste_final_unitario * cantidad, 2)",
        ("coste_final_unitario", "cantidad"),
        "EUR",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Calcula el coste total de una linea ya validada.",
    ),
    _formula(
        "transporte_coste_m3",
        "Pedidos",
        "Coste de transporte por M3",
        "coste_transporte_m3 = round(coste_transporte_iva / m3_total_pedido, 2)",
        ("coste_transporte_iva", "m3_total_pedido"),
        "EUR/m3",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Reparte el transporte total del pedido sobre el volumen total.",
        notes="El calculo se bloquea cuando el M3 total no es positivo.",
    ),
    _formula(
        "transporte_coste_producto",
        "Pedidos",
        "Transporte unitario por producto",
        "transporte_producto = round(coste_transporte_m3 * m3_unidad, 2)",
        ("coste_transporte_m3", "m3_unidad"),
        "EUR/unidad",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Asigna a cada unidad el transporte correspondiente a su volumen.",
    ),
    _formula(
        "descarga_coste_producto",
        "Pedidos",
        "Descarga unitaria",
        "descarga_unidad = round(coste_descarga_iva / unidades_que_reparten_descarga, 2)",
        ("coste_descarga_iva", "unidades_que_reparten_descarga"),
        "EUR/unidad",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Reparte la descarga solo entre lineas marcadas para participar en ese reparto.",
        notes="Las lineas excluidas reciben descarga_unidad = 0.",
    ),
    _formula(
        "heimei_tasa_cambio",
        "Pedidos",
        "Tasa de cambio Heimei",
        "tasa_cambio = round(precio_dolares / precio_euros_pagados, 6)",
        ("precio_dolares", "precio_euros_pagados"),
        "USD/EUR",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Deriva la tasa aplicada a los precios de articulo del pedido Heimei.",
    ),
    _formula(
        "heimei_importe_transporte",
        "Pedidos",
        "Importe de transporte y aranceles",
        "importe_transporte = factura_transporte + derechos_aranceles",
        ("factura_transporte", "derechos_aranceles"),
        "EUR",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Agrupa los dos importes que alimentan el porcentaje de transporte.",
    ),
    _formula(
        "heimei_pc_transporte",
        "Pedidos",
        "Porcentaje de transporte Heimei",
        "pc_transporte = round((importe_transporte / precio_euros_pagados) * 100, 2)",
        ("importe_transporte", "precio_euros_pagados"),
        "%",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Expresa transporte y aranceles como porcentaje de la factura pagada.",
    ),
    _formula(
        "heimei_pc_descarga",
        "Pedidos",
        "Porcentaje de descarga Heimei",
        "pc_descarga = round((importe_descarga * 100) / precio_euros_pagados, 2)",
        ("importe_descarga", "precio_euros_pagados"),
        "%",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Convierte el importe fijo de descarga en porcentaje de la factura.",
    ),
    _formula(
        "iva_recargo_equivalencia",
        "Pedidos",
        "IVA y recargo de equivalencia",
        "iva_re = round(precio_proveedor * factor_iva_re, 2)",
        ("precio_proveedor", "factor_iva_re"),
        "EUR",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Calcula el importe fiscal agregado al precio de proveedor.",
        notes="La configuracion 26,2 se normaliza a factor 0,262 antes de usarla.",
    ),
    _formula(
        "precio_compra_iva_re",
        "Pedidos",
        "Precio de compra con IVA y recargo",
        "precio_con_iva = round(precio_proveedor + iva_re, 2)",
        ("precio_proveedor", "iva_re"),
        "EUR/unidad",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Suma al precio de proveedor el importe fiscal calculado.",
    ),
    _formula(
        "coste_almacenaje_iva",
        "Pedidos",
        "Coste de almacenaje con IVA",
        "almacenaje_iva = round(coste_diario_m3 * m3_unidad * rotacion_c * 1.21, 4)",
        ("coste_diario_m3", "m3_unidad", "rotacion_c"),
        "EUR/unidad",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Valora el almacenaje previsto e incorpora el multiplicador IVA 1,21.",
    ),
    _formula(
        "coste_picking_iva",
        "Pedidos",
        "Coste de picking con IVA",
        "picking_iva = round(((bultos * 0.3) + 4.12) * 1.21, 3)",
        ("bultos",),
        "EUR/unidad",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Calcula el picking segun bultos e incorpora el multiplicador IVA 1,21.",
    ),
    _formula(
        "coste_descarga_general",
        "Pedidos",
        "Coste tras transporte y descarga",
        "coste_descarga = round(transporte_producto + descarga_unidad + precio_con_iva, 2)",
        ("transporte_producto", "descarga_unidad", "precio_con_iva"),
        "EUR/unidad",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Agrupa compra fiscalizada, transporte y descarga antes de costes operativos.",
    ),
    _formula(
        "coste_final_general",
        "Pedidos",
        "Coste final unitario general",
        "coste_final = round(coste_descarga + almacenaje_iva + picking_iva, 2)",
        ("coste_descarga", "almacenaje_iva", "picking_iva"),
        "EUR/unidad",
        "Pedidos generales",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Obtiene el coste final unitario de Ekomat, Pascal y Cipta.",
        notes=f"Formula espejo verificada en {LEGACY_ORDER_SOURCE}: calcular_coste_unitario_pedido.",
    ),
    _formula(
        "heimei_pc_varios",
        "Pedidos",
        "Porcentaje de varios Heimei",
        "pc_varios = round((importe_varios / precio_euros_pagados) * 100, 2)",
        ("importe_varios", "precio_euros_pagados"),
        "%",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Convierte el importe fijo de varios en porcentaje de la factura.",
    ),
    _formula(
        "heimei_pc_suma",
        "Pedidos",
        "Porcentaje total de gastos Heimei",
        "pc_suma = round(pc_transporte + pc_descarga + pc_financiacion + pc_manipulacion + pc_varios, 2)",
        ("pc_transporte", "pc_descarga", "pc_financiacion", "pc_manipulacion", "pc_varios"),
        "%",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Consolida los porcentajes aplicables al precio del articulo.",
    ),
    _formula(
        "heimei_precio_articulo_eur",
        "Pedidos",
        "Precio de articulo en euros",
        "precio_articulo_eur = round(precio_articulo_usd / tasa_cambio, 2)",
        ("precio_articulo_usd", "tasa_cambio"),
        "EUR/unidad",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Convierte el precio de proveedor del articulo a euros.",
    ),
    _formula(
        "heimei_gastos_aplicables",
        "Pedidos",
        "Gastos aplicables Heimei",
        "gastos = round(precio_articulo_eur * pc_suma / 100, 2)",
        ("precio_articulo_eur", "pc_suma"),
        "EUR/unidad",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Aplica el porcentaje consolidado de gastos al articulo.",
    ),
    _formula(
        "heimei_coste_sin_almacenaje",
        "Pedidos",
        "Coste Heimei antes de almacenaje",
        "coste_sin_almacenaje = round(precio_articulo_eur + gastos, 2)",
        ("precio_articulo_eur", "gastos"),
        "EUR/unidad",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Suma precio convertido y gastos antes de almacenaje y picking.",
    ),
    _formula(
        "heimei_coste_final",
        "Pedidos",
        "Coste final unitario Heimei",
        "coste_final = round(coste_sin_almacenaje + almacenaje_iva + picking_iva, 2)",
        ("coste_sin_almacenaje", "almacenaje_iva", "picking_iva"),
        "EUR/unidad",
        "Pedidos Heimei / Tatamis",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Obtiene el coste final unitario de la formula Heimei/Tatamis.",
        notes=f"Formula espejo verificada en {LEGACY_ORDER_SOURCE}: calcular_coste_unitario_tatamis_pedido.",
    ),
    _formula(
        "pvp_margen_venta",
        "Pedidos",
        "P.V.P. desde margen de venta",
        "pvp_unitario = coste_base / (1 - margen_percent / 100)",
        ("coste_base", "margen_percent"),
        "EUR/unidad",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_supplier_order_pvp_decimal",
        purpose="Calcula el P.V.P. con margen sobre precio de venta, redondeado a 0,01 EUR con ROUND_HALF_UP.",
        conditions="coste_base > 0 y margen_percent < 100.",
        notes="El margen debe ser menor que 100; el coste base no positivo devuelve 0,00.",
    ),
    _formula(
        "margen_desde_pvp",
        "Pedidos",
        "Margen de venta desde P.V.P.",
        "margen_percent = (1 - coste_base / pvp_unitario) * 100",
        ("coste_base", "pvp_unitario"),
        "%",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_supplier_order_margin_from_pvp",
        purpose="Recupera el margen cuando el usuario aporta un P.V.P. unitario.",
        conditions="coste_base >= 0 y pvp_unitario > 0.",
        notes="Redondeo a 0,01 con ROUND_HALF_UP; P.V.P. debe ser positivo.",
    ),
    _formula(
        "pvp_total_linea",
        "Pedidos",
        "P.V.P. total de linea",
        "pvp_linea = round(pvp_unitario * cantidad, 2)",
        ("pvp_unitario", "cantidad"),
        "EUR",
        "Pedidos de proveedor",
        PROTOTYPE_SOURCE,
        "_calculate_supplier_order_in_memory",
        purpose="Extiende el P.V.P. unitario a la cantidad de la linea.",
    ),
    _formula(
        "inventario_coste_ponderado",
        "Inventario",
        "Coste medio ponderado tras pedido",
        "ponderado = round(((stock * coste_medio) + (cantidad * coste_final)) / (stock + cantidad), 2)",
        ("stock", "coste_medio", "cantidad", "coste_final"),
        "EUR/unidad",
        "Inventario y pedidos",
        PROTOTYPE_SOURCE,
        "_supplier_order_weighted_unit_cost",
        purpose="Calcula el coste comercial ponderado del lote con el stock existente.",
        notes="Si stock o coste medio no son positivos, devuelve el coste final del nuevo lote.",
    ),
    _formula(
        "inventario_stock_recepcion",
        "Inventario",
        "Stock tras recepcion",
        "stock_destino_despues = stock_destino_antes + cantidad_recibida",
        ("stock_destino_antes", "cantidad_recibida"),
        "unidades",
        "Recepcion de pedidos",
        ORDERS_SOURCE,
        "preview_receive_supplier_order",
        purpose="Previsualiza el stock de tienda o almacen despues de una recepcion.",
        notes="Solo se incrementa el destino seleccionado; la biblioteca no ejecuta la recepcion.",
    ),
    _formula(
        "woo_delta_precio",
        "Woo Precios",
        "Diferencia de precio propuesta",
        "delta = precio_propuesto - precio_actual",
        ("precio_propuesto", "precio_actual"),
        "EUR",
        "Propuestas y publicacion WooCommerce",
        PRICE_PROPOSALS_SOURCE,
        "_legacy_price_safety_preview",
        purpose="Calcula la diferencia absoluta que se revisa antes de publicar precios.",
        status="AUXILIAR",
    ),
    _formula(
        "woo_delta_precio_percent",
        "Woo Precios",
        "Variacion porcentual de precio",
        "delta_percent = ((precio_propuesto - precio_actual) / precio_actual) * 100",
        ("precio_propuesto", "precio_actual"),
        "%",
        "Propuestas y publicacion WooCommerce",
        PRICE_PROPOSALS_SOURCE,
        "_legacy_price_safety_preview",
        purpose="Mide la variacion y permite aplicar umbrales de aviso o bloqueo antes de WooCommerce.",
        status="AUXILIAR",
        notes="Solo se calcula cuando el precio actual es positivo.",
    ),
    _formula(
        "woo_combination_weighted_delta",
        "Woo Precios",
        "Delta ponderado por componente Woo",
        "delta_ponderado = delta_unitario * cantidad_componente",
        ("delta_unitario", "cantidad_componente"),
        "EUR",
        "Impacto de combinaciones Woo",
        COMBINATION_PRICE_SOURCE,
        "impact_for_changes",
        purpose="Acumula el efecto de un cambio de componente según la cantidad exacta usada por una combinación Woo.",
        conditions="cantidad_componente > 0 y la arista de composición debe ser exacta y operativa.",
        notes="Las aristas en cuarentena no se incluyen en el impacto operativo.",
    ),
    _formula(
        "woo_combination_simulated_price",
        "Woo Precios",
        "Precio simulado de combinación Woo",
        "precio_simulado = precio_efectivo_actual + suma(delta_ponderado)",
        ("precio_efectivo_actual", "delta_ponderado"),
        "EUR",
        "Impacto de combinaciones Woo",
        COMBINATION_PRICE_SOURCE,
        "impact_for_changes",
        purpose="Calcula el impacto acumulado de los componentes exactos sobre el precio efectivo de una combinación.",
        conditions="El precio efectivo actual debe ser numérico y las relaciones deben pertenecer al grafo operativo aprobado.",
        notes="Es una simulación read-only; no publica cambios en WooCommerce.",
    ),
    _formula(
        "futuras_pendientes",
        "Otros",
        "Formulas futuras",
        "Pendiente de evidencia en codigo",
        (),
        "No aplica",
        "Reserva documental",
        "",
        "",
        purpose="Reserva una seccion para formulas que se incorporen y puedan demostrarse en codigo.",
        status="PREVISTA",
        notes="No representa una formula activa ni autoriza completar huecos por conocimiento general.",
    ),
)


FORMULA_CATEGORIES = (
    "Todas",
    "Pedidos",
    "Inventario",
    "Woo Precios",
    "Otros",
)


def formula_records(category: str = "Todas") -> tuple[FormulaRecord, ...]:
    if category == "Todas":
        return FORMULA_LIBRARY
    return tuple(record for record in FORMULA_LIBRARY if record.category == category)


def formula_summary(records: Iterable[FormulaRecord] = FORMULA_LIBRARY) -> dict[str, int]:
    values = tuple(records)
    return {
        "total": len(values),
        "active": sum(record.status == "ACTIVA" for record in values),
        "auxiliary": sum(record.status == "AUXILIAR" for record in values),
        "future": sum(record.status == "PREVISTA" for record in values),
        "categories": len({record.category for record in values if record.category != "Otros"}),
    }


def render_formula_library_html(records: Iterable[FormulaRecord] = FORMULA_LIBRARY) -> str:
    values = tuple(records)
    category_buttons = "".join(
        f'<button type="button" data-category="{escape(category)}">{escape(category)}</button>'
        for category in FORMULA_CATEGORIES
    )
    cards = []
    for record in values:
        source = f"{record.source_path} :: {record.source_symbol}" if record.source_path else "Pendiente de evidencia"
        variables = ", ".join(record.variables) or "No aplica"
        cards.append(
            f"""
            <article class="formula-card" data-category="{escape(record.category)}">
              <div class="card-head">
                <div><span class="category">{escape(record.category)}</span><h2>{escape(record.name)}</h2></div>
                <span class="status {escape(record.status.lower())}">{escape(record.status)}</span>
              </div>
              <p>{escape(record.purpose)}</p>
              <code>{escape(record.expression)}</code>
              <dl>
                <div><dt>Variables</dt><dd>{escape(variables)}</dd></div>
                <div><dt>Unidades</dt><dd>{escape(record.units)}</dd></div>
                <div><dt>Modulo</dt><dd>{escape(record.module)}</dd></div>
                <div><dt>Fuente</dt><dd>{escape(source)}</dd></div>
                <div><dt>Condiciones</dt><dd>{escape(record.conditions)}</dd></div>
              </dl>
              {f'<p class="note">{escape(record.notes)}</p>' if record.notes else ''}
            </article>
            """
        )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FutonHUB - Biblioteca de Fórmulas</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, "Segoe UI", sans-serif; background: #f8fafc; color: #0f172a; }}
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; max-width: 100%; overflow-x: hidden; }}
    body {{ margin: 0; }}
    header {{ background: #fff; border-bottom: 1px solid #e2e8f0; padding: 28px clamp(18px, 4vw, 64px) 22px; }}
    .eyebrow {{ color: #4f46e5; font-size: 12px; font-weight: 800; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 6px; font-size: clamp(28px, 4vw, 42px); letter-spacing: 0; }}
    header p {{ margin: 0; color: #64748b; max-width: 760px; }}
    main {{ width: 100%; max-width: 1320px; min-width: 0; margin: 0 auto; padding: 20px clamp(14px, 3vw, 32px) 52px; }}
    .notice {{ background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; padding: 14px 16px; margin-bottom: 16px; }}
    nav {{ display: flex; width: 100%; max-width: 100%; gap: 8px; overflow-x: auto; padding: 4px 0 14px; }}
    button {{ border: 1px solid #cbd5e1; background: #fff; color: #334155; padding: 9px 13px; cursor: pointer; white-space: nowrap; }}
    button.active {{ background: #4f46e5; border-color: #4f46e5; color: #fff; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .formula-card {{ background: #fff; border: 1px solid #e2e8f0; padding: 18px; min-width: 0; }}
    .card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
    .category {{ color: #4f46e5; font-size: 11px; font-weight: 800; text-transform: uppercase; }}
    h2 {{ font-size: 17px; margin: 4px 0 0; letter-spacing: 0; }}
    p {{ color: #475569; line-height: 1.45; }}
    code {{ display: block; max-width: 100%; white-space: normal; overflow-wrap: anywhere; background: #f1f5f9; border-left: 3px solid #4f46e5; padding: 12px; color: #0f172a; }}
    dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin: 14px 0 0; }}
    dl div {{ min-width: 0; }}
    dt {{ color: #64748b; font-size: 11px; font-weight: 800; text-transform: uppercase; }}
    dd {{ margin: 3px 0 0; overflow-wrap: anywhere; }}
    .status {{ font-size: 10px; font-weight: 800; padding: 5px 8px; background: #ecfdf5; color: #047857; }}
    .status.auxiliar {{ background: #eff6ff; color: #1d4ed8; }}
    .status.prevista {{ background: #fffbeb; color: #b45309; }}
    .note {{ border-top: 1px solid #e2e8f0; padding-top: 10px; font-size: 13px; }}
    .hidden {{ display: none; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} dl {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header><span class="eyebrow">Sistema / Solo lectura</span><h1>Biblioteca de Fórmulas</h1><p>Inventario trazable construido desde el código real. Esta vista no modifica fórmulas, constantes, datos ni resultados.</p></header>
  <main>
    <div class="notice">Consulta documental. Cualquier cambio de formula requiere un corte funcional independiente.</div>
    <nav aria-label="Categorias">{category_buttons}</nav>
    <section class="grid">{''.join(cards)}</section>
  </main>
  <script>
    const buttons = [...document.querySelectorAll('button[data-category]')];
    const cards = [...document.querySelectorAll('.formula-card')];
    function selectCategory(category) {{
      buttons.forEach(button => button.classList.toggle('active', button.dataset.category === category));
      cards.forEach(card => card.classList.toggle('hidden', category !== 'Todas' && card.dataset.category !== category));
    }}
    buttons.forEach(button => button.addEventListener('click', () => selectCategory(button.dataset.category)));
    selectCategory('Todas');
  </script>
</body>
</html>
"""


class ErpFormulaLibraryMixin:
    _formula_library_category = "Todas"

    def _build_formula_library(self, parent: tk.Frame) -> None:
        self._page_header(
            parent,
            "SISTEMA / SOLO LECTURA",
            "Biblioteca de Fórmulas",
            "Fórmulas verificadas en código, variables, unidades y origen de cada cálculo.",
        )

        notice = tk.Frame(parent, bg=INDIGO_SOFT, highlightbackground="#C7D2FE", highlightthickness=1)
        notice.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            notice,
            text="Consulta documental. Esta pantalla no modifica fórmulas, constantes, datos ni resultados.",
            bg=INDIGO_SOFT,
            fg="#3730A3",
            font=("Segoe UI", 10, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, padx=14, pady=11)

        categories = tk.Frame(parent, bg=BG)
        categories.pack(fill=tk.X, pady=(0, 10))

        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        body = tk.Frame(canvas, bg=BG)
        body.columnconfigure(0, weight=1)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def render(category: str) -> None:
            self._formula_library_category = category
            for child in body.winfo_children():
                child.destroy()
            for record in formula_records(category):
                self._formula_library_card(body, record).pack(fill=tk.X, pady=(0, 10))
            for button in categories.winfo_children():
                selected = str(button.cget("text")) == category
                button.configure(
                    bg=INDIGO if selected else CARD,
                    fg="white" if selected else "#334155",
                    activebackground="#4338CA" if selected else SOFT,
                    activeforeground="white" if selected else TEXT,
                )
            canvas.yview_moveto(0)

        for category in FORMULA_CATEGORIES:
            self._button(categories, category, command=lambda value=category: render(value)).pack(side=tk.LEFT, padx=(0, 7))

        def sync_scroll(_event: object | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())

        body.bind("<Configure>", sync_scroll)
        canvas.bind("<Configure>", sync_scroll)
        canvas.bind_all(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            if getattr(self, "_current_key", "") == "formulas"
            else None,
        )
        render(self._formula_library_category if self._formula_library_category in FORMULA_CATEGORIES else "Todas")

    def _formula_library_card(self, parent: tk.Misc, record: FormulaRecord) -> tk.Frame:
        status_styles = {
            "ACTIVA": (GREEN, GREEN_SOFT),
            "AUXILIAR": (BLUE, BLUE_SOFT),
            "PREVISTA": (AMBER, AMBER_SOFT),
        }
        fg, soft_bg = status_styles.get(record.status, (BLUE, BLUE_SOFT))
        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        head = tk.Frame(card, bg=CARD)
        head.pack(fill=tk.X, padx=16, pady=(14, 7))
        title = tk.Frame(head, bg=CARD)
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(title, text=record.category.upper(), bg=CARD, fg=INDIGO, font=("Segoe UI", 8, "bold")).pack(anchor=tk.W)
        tk.Label(title, text=record.name, bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold"), anchor=tk.W).pack(fill=tk.X)
        tk.Label(head, text=record.status, bg=soft_bg, fg=fg, font=("Segoe UI", 8, "bold"), padx=9, pady=4).pack(side=tk.RIGHT)

        tk.Label(card, text=record.purpose, bg=CARD, fg=MUTED, font=("Segoe UI", 9), anchor=tk.W, justify=tk.LEFT, wraplength=920).pack(fill=tk.X, padx=16)
        expression = tk.Frame(card, bg=SOFT, highlightbackground=LINE, highlightthickness=1)
        expression.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(
            expression,
            text=record.expression,
            bg=SOFT,
            fg=TEXT,
            font=("Consolas", 10, "bold"),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=920,
        ).pack(fill=tk.X, padx=12, pady=10)

        details = tk.Frame(card, bg=CARD)
        details.pack(fill=tk.X, padx=16, pady=(0, 12))
        details.columnconfigure(0, weight=1)
        details.columnconfigure(1, weight=1)
        variables = ", ".join(record.variables) or "No aplica"
        source = f"{record.source_path} :: {record.source_symbol}" if record.source_path else "Pendiente de evidencia"
        self._formula_library_detail(details, 0, 0, "Variables", variables)
        self._formula_library_detail(details, 0, 1, "Unidades", record.units)
        self._formula_library_detail(details, 1, 0, "Modulo", record.module)
        self._formula_library_detail(details, 1, 1, "Fuente", source)
        self._formula_library_detail(details, 2, 0, "Condiciones", record.conditions)
        if record.notes:
            tk.Label(card, text=record.notes, bg=INDIGO_SOFT, fg="#3730A3", font=("Segoe UI", 9), anchor=tk.W, justify=tk.LEFT, wraplength=920).pack(fill=tk.X, padx=16, pady=(0, 14), ipady=7)
        return card

    def _formula_library_detail(self, parent: tk.Misc, row: int, column: int, label: str, value: str) -> None:
        frame = tk.Frame(parent, bg=CARD)
        frame.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 8, 8 if column == 0 else 0), pady=4)
        tk.Label(frame, text=label.upper(), bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold"), anchor=tk.W).pack(fill=tk.X)
        tk.Label(frame, text=value, bg=CARD, fg=TEXT, font=("Segoe UI", 9), anchor=tk.W, justify=tk.LEFT, wraplength=440).pack(fill=tk.X)

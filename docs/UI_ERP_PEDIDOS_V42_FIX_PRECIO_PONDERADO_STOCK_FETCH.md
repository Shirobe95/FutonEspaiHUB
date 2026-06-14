# UI ERP Pedidos v42 - Fix precio ponderado lote

## Problema

La columna `Precio ponderado lote` aparecía, pero parecía calcular como si no hubiera stock.

## Causa

La fórmula ya estaba implementada, pero el puente `get_supplier_price()` no estaba trayendo desde Supabase estos campos:

```text
store_stock
warehouse_stock
weighted_average_cost
```

Entonces el cálculo recibía stock/coste medio como 0 y aplicaba fallback:

```text
precio_ponderado_lote = Coste Final Artículo
```

## Solución

`get_supplier_price()` ahora selecciona también:

```text
store_stock
warehouse_stock
weighted_average_cost
order_calculated_price
```

Con eso `_fill_supplier_prices_for_order_items()` puede meter en la línea:

```text
inventory_store_stock
inventory_warehouse_stock
inventory_stock_total
inventory_weighted_average_cost
```

y el cálculo aplica:

```text
precio_ponderado_lote =
(stock_total_actual × coste_medio_actual + cantidad_pedida × coste_final_artículo)
/
(stock_total_actual + cantidad_pedida)
```

## Nota

Si `weighted_average_cost` está vacío o 0 en Supabase, el ERP seguirá usando como referencia el `Coste Final Artículo`.

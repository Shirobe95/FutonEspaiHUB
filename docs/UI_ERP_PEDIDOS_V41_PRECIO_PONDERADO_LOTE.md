# UI ERP Pedidos v41 - Precio ponderado por lote

## Objetivo

Añadir en la tabla de cálculo de pedido una columna de referencia para el precio ponderado.

## Columna nueva

Se añade después de:

```text
Coste Final Artículo
```

y antes de:

```text
Coste Total Cantidad
```

Nueva columna:

```text
Precio ponderado lote
```

## Fórmula

Se calcula tomando todo el lote pedido:

```text
precio_ponderado_lote =
(stock_total_actual × coste_medio_actual + cantidad_pedida × coste_final_artículo)
/
(stock_total_actual + cantidad_pedida)
```

## Criterio

- Si hay stock actual y coste medio actual, se calcula ponderado real.
- Si no hay coste medio o no hay stock actual, se usa como referencia el Coste Final Artículo.
- No modifica el Coste Final Artículo.
- No actualiza stock.
- No escribe el nuevo ponderado en Supabase todavía.
- Se muestra también en la exportación premium del pedido.

## Datos usados

Desde `inventory_items`:

```text
store_stock
warehouse_stock
weighted_average_cost
```

Desde cálculo de pedido:

```text
quantity
precio_coste_final
```

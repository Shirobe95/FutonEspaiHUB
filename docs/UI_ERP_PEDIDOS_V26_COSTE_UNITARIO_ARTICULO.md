# UI ERP Pedidos v26 - Coste final unitario del artículo

## Cambio quirúrgico

La tabla de cálculo de pedido ahora diferencia dos conceptos:

```text
Coste Final Artículo  = coste unitario real del producto
Coste Total Cantidad  = coste unitario × cantidad pedida
```

## Motivo

En el trabajo diario interesa principalmente saber cuánto cuesta **una unidad** del producto.

Ejemplo:

```text
Coste Final Artículo: 46.73 €
Cantidad pedida: 30
Coste Total Cantidad: 1401.90 €
```

El total de cantidad se mantiene porque puede ser útil para resumen del pedido, pero deja de ocupar el lugar principal.

## Columnas modificadas

Antes:

```text
% Financiación
Coste Final del Producto
```

Ahora:

```text
% Financiación / Rentabilidad
Coste Final Artículo
Coste Total Cantidad
```

## Datos internos

El cálculo ya guardaba ambos:

```text
source_row.unit_cost / precio_coste_final -> coste unitario
source_row.line_cost / final_cost         -> coste total cantidad
```

Este parche solo los muestra correctamente en tabla.

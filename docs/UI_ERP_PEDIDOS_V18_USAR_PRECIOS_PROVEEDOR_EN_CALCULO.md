# UI ERP Pedidos v18 - Usar precios proveedor en cálculo

## Objetivo

Una vez migrados los precios proveedor a Supabase, Pedidos debe usarlos al calcular.

Modelo Supabase:

```text
inventory_items.primary_supplier_price
inventory_items.pascal_price
```

Regla:

```text
Proveedor Pascal -> pascal_price
Ekomat / Heimei / Cipta -> primary_supplier_price
```

## Cambio

Antes de calcular, el ERP revisa cada línea del pedido:

- si la línea ya trae `precio_proveedor`, lo respeta.
- si falta precio proveedor, busca en Supabase por `item_id + proveedor`.
- si encuentra precio, lo rellena en memoria.
- si no encuentra precio, la fila queda marcada como error/roja.

## Seguridad

- No toca WooCommerce.
- No toca inventario.
- No modifica precios.
- Solo usa precios existentes para calcular el pedido.

## Archivo tocado

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

# UI ERP Pedidos v20 - Resolver precios proveedor

## Diagnóstico

Los precios proveedor sí están en Supabase:

```text
inventory_items.primary_supplier_price
inventory_items.pascal_price
```

El problema probable es que el código que llega desde Excel/PDF no siempre coincide exactamente con `inventory_items.item_id`.

## Cambio

El resolver de precios proveedor ahora intenta buscar por:

1. `inventory_items.item_id`
2. `inventory_items.heca_reference`
3. `inventory_items.woo_sku`
4. versión numérica sin ceros a la izquierda

## Regla de precio

```text
Pascal -> pascal_price
Otros proveedores -> primary_supplier_price
```

## Metadata añadida a la línea

Cuando encuentra precio, guarda en `source_row`:

```text
supplier_price_source
supplier_price_column
supplier_price_provider
supplier_price_matched_by
supplier_price_item_id
ui_supplier_price_filled
```

Esto permite ver luego por dónde encontró el precio.

## Seguridad

No toca WooCommerce.  
No modifica inventario.  
Solo lee precios y los usa en memoria para calcular el pedido.

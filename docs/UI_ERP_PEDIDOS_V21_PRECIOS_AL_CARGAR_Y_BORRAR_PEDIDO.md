# UI ERP Pedidos v21 - Precios al cargar y borrar pedido

## Precios proveedor al cargar

Antes, el precio proveedor se rellenaba al pulsar **Calcular pedido**.  
Eso hacía que, al cargar el Excel/PDF, las filas aparecieran rojas aunque luego sí pudieran calcularse.

Ahora:

```text
Cargar Excel/PDF
→ resolver precio proveedor desde Supabase
→ pintar tabla ya con precio si existe
```

También se hace al abrir/modificar un borrador ya guardado.

Regla:

```text
Pascal -> inventory_items.pascal_price
Ekomat / Heimei / Cipta -> inventory_items.primary_supplier_price
```

## Borrar pedido

El botón **Borrar pedido** queda funcional como cancelación lógica:

```text
status = cancelled
source_row.ui_cancelled = true
```

No borra histórico ni líneas.  
No toca inventario.  
No toca WooCommerce.

Al cancelar:

- genera snapshot
- genera audit log
- quita el pedido de la lista visual
- al actualizar/reabrir no vuelve a salir porque la consulta excluye `cancelled`

## Archivos tocados

- `GestorWoo/src/futonhub/ui/erp/prototype.py`
- `GestorWoo/src/futonhub/cloud/services/orders.py`

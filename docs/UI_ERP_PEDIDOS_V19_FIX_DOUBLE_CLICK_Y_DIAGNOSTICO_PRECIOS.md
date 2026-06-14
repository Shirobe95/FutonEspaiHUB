# UI ERP Pedidos v19 - Fix doble click y diagnóstico precios proveedor

## Fix crítico

El doble click en la tabla de cálculo de Pedidos fallaba con:

```text
TypeError: cannot unpack non-iterable OrderItem object
```

Causa:

- Inventario necesita `item_by_iid[iid] = item`.
- Pedidos necesita `item_by_iid[iid] = (index, item)`.
- Un parche anterior dejó Pedidos guardando solo `item`.

Corrección:

```text
_build_inventory      -> item_by_iid[iid] = item
_calculation_tree     -> item_by_iid[iid] = (index, item)
```

## Diagnóstico de precios proveedor

Nuevo comando:

```powershell
python gestorwoo.py cloud-supplier-prices-diagnostic
```

No escribe nada.

Muestra:

- filas locales de supplier_prices
- distribución por proveedor
- items locales a mapear
- items encontrados en inventory_items Supabase
- items locales no encontrados
- conflictos de doble proveedor
- muestra de precios actuales en Supabase

## Objetivo

Antes de seguir con cálculo automático, verificar si:

```text
inventory_items.primary_supplier_price
inventory_items.pascal_price
```

ya están cargados y con qué valores.

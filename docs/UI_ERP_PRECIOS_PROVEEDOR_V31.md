# UI ERP v31 - Precio Proveedores

## Objetivo

Nueva sección en **Gestión** para consultar y editar precios proveedor desde Supabase.

## Menú

```text
Gestión → Precio Proveedores
```

## Fuente de datos

Tabla Supabase:

```text
inventory_items
```

Columnas principales:

```text
item_id
name
family
subgroup
materials
size
primary_supplier_price
pascal_price
heca_reference
woo_sku
updated_at
```

## Funcionalidad

- Carga items reales desde Supabase.
- Búsqueda por nombre, HECA, Woo SKU e ID exacto.
- Tabla con:
  - ID
  - Nombre
  - Precio principal
  - Precio Pascal
  - Familia
  - Subgrupo
  - Estado
- Panel lateral de detalle.
- Edición de:
  - primary_supplier_price
  - pascal_price
- Campo de motivo/nota.
- Guardado con:
  - update en Supabase
  - snapshot
  - audit log

## Seguridad

No toca WooCommerce.  
No toca stock.  
No toca pedidos.  
Solo actualiza precios proveedor en `inventory_items`.

## Servicios añadidos

```text
list_supplier_price_inventory_items()
update_supplier_price_inventory_item()
```

# UI ERP Pedidos v17 - Fix migración precios proveedor

## Problema

La v16 usaba `upsert` sobre `inventory_items`.

Si un `item_id` de la SQLite local no existía en Supabase, Supabase intentaba insertar una fila nueva en `inventory_items` solo con precios. Eso fallaba porque `name` es NOT NULL:

```text
null value in column "name" of relation "inventory_items" violates not-null constraint
```

## Solución

La migración ahora no inserta items nuevos.

Flujo:

```text
leer supplier_prices local
→ construir updates para inventory_items
→ comprobar si item_id existe en Supabase
→ si existe: UPDATE de primary_supplier_price / pascal_price
→ si no existe: saltar y reportar
```

## Resultado esperado

El comando debe mostrar:

- filas locales
- items a actualizar
- items no encontrados en Supabase
- migrados
- saltados

## SQL diagnóstico

Se añade:

```text
docs/SQL_DIAGNOSTICO_SUPABASE_INVENTORY_SUPPLIER_PRICES.sql
```

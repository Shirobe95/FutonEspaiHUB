# UI ERP v23 - Fix guardado de constantes

## Problema

Al guardar constantes desde Configuración / Cálculos, Supabase devolvía:

```text
Could not find the 'source_row' column of 'business_constants' in the schema cache
```

## Causa

El servicio intentaba guardar metadata en `business_constants.source_row`, pero la tabla real de Supabase no tiene esa columna.

## Solución

`save_business_constants()` ahora es tolerante al esquema real:

1. Intenta guardar payload completo.
2. Si Supabase dice que falta `source_row`, lo elimina y reintenta.
3. Si faltan otras columnas opcionales como `updated_at`, `unit` o `description`, también las elimina y reintenta.
4. Si el `upsert` falla por constraint/schema cache, usa fallback update/insert por `key`.

## Seguridad

- Sigue creando snapshot si puede.
- Sigue creando audit log si puede.
- No toca WooCommerce.
- No toca pedidos.
- Solo modifica `business_constants`.

## Archivo tocado

```text
GestorWoo/src/futonhub/cloud/services/business_constants.py
```

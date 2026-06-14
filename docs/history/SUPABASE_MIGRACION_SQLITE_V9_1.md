# FutonHUB v9.1 - Fix migración SQLite → Supabase

Esta versión corrige el error de migración:

```txt
there is no unique or exclusion constraint matching the ON CONFLICT specification
```

El fallo aparecía al migrar `price_change_proposals`, después de haber subido correctamente:

- `products`
- `product_variations`
- `inventory_items`
- `supplier_prices`
- `heca_stock`

## Qué pasó

El script v9 creaba un índice único parcial para `local_sqlite_id`. PostgreSQL lo acepta, pero PostgREST/Supabase no lo puede usar como destino de `on_conflict`.

## Qué hacer

1. Ejecutar en Supabase SQL Editor:

```txt
docs/supabase/15_fix_on_conflict_migracion_v9_1.sql
```

2. Repetir la migración:

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR
```

Es seguro repetirla: las tablas ya migradas usan `upsert`, así que se actualizan sin duplicarse.

También puedes reanudar solo la tabla que falló:

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR --tables price_change_proposals
```

Luego revisa:

```powershell
python gestorwoo.py cloud-operational-status
```

WooCommerce no se toca en esta fase.

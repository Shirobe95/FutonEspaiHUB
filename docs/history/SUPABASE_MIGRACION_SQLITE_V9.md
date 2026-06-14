# FutonHUB v9 - Migración controlada SQLite → Supabase

Objetivo: subir la base local estable a Supabase como verdad operativa interna, sin tocar WooCommerce.

## 1. Ejecutar SQL

En Supabase > SQL Editor ejecuta:

```txt
docs/supabase/14_migracion_sqlite_supabase_v9.sql
```

## 2. Preview con login admin

Desde `GestorWoo`:

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-preview
```

Esto compara conteos locales y cloud. No sube datos.

## 3. Ejecutar migración real

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR
```

También puedes migrar una tabla concreta durante pruebas:

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR --tables products
```

## Tablas incluidas

- products
- product_variations
- inventory_items
- supplier_prices
- heca_stock
- price_change_proposals
- supplier_orders
- supplier_order_items

## Seguridad

- Solo admin puede ejecutar.
- Crea audit_logs de inicio y fin.
- No publica ni sincroniza con WooCommerce.
- Usa upsert para evitar duplicados al repetir migración.

## Después de migrar

Ejecuta:

```powershell
python gestorwoo.py cloud-operational-status
```

Los conteos cloud deberían acercarse a:

```txt
products: 115
product_variations: 614
inventory_items: 235
supplier_prices: 397
heca_stock: 2930
price_change_proposals: 7
```

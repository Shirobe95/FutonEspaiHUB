# UI ERP Pedidos v15 - Migrar precios de proveedor

## Objetivo

Migrar la tabla local `supplier_prices` desde SQLite a Supabase para que Pedidos pueda calcular usando precios de proveedor reales.

## Fuente local

```text
GestorWoo/data/gestorwoo.sqlite3
tabla: supplier_prices
```

Columnas:

```text
item_id
supplier
price
currency
source
updated_at
```

En la base local actual hay 435 registros.

## Servicio nuevo

```text
GestorWoo/src/futonhub/cloud/services/supplier_prices.py
```

Funciones principales:

```python
read_local_supplier_prices()
preview_supplier_prices_migration(session)
migrate_supplier_prices_to_supabase(session, execute=True)
get_supplier_price(session, item_id, supplier)
list_supplier_prices_for_item(session, item_id)
```

## Comandos nuevos

Preview, no escribe:

```powershell
python gestorwoo.py cloud-migrate-supplier-prices-preview
```

Ejecutar migración:

```powershell
python gestorwoo.py cloud-migrate-supplier-prices-execute --confirm MIGRAR_PRECIOS_PROVEEDOR
```

## Seguridad

- No toca WooCommerce.
- No toca inventario.
- Crea audit log.
- Intenta crear snapshot resumen de migración.
- Usa upsert por `item_id,supplier`.

## Nota importante Supabase

Para que el upsert funcione bien, Supabase debe tener una restricción única sobre:

```sql
(item_id, supplier)
```

Si no existe, el comando de ejecución puede devolver error de constraint/on_conflict.

SQL recomendado si falta:

```sql
create unique index if not exists supplier_prices_item_supplier_uidx
on public.supplier_prices (item_id, supplier);
```

## Próximo paso

Una vez migrado:

- Pedidos puede consultar `supplier_prices` por `item_id + proveedor`.
- Si una línea de Excel no trae precio proveedor, se intenta llenar desde Supabase.
- Si no existe precio, la fila queda roja y se edita con doble click.

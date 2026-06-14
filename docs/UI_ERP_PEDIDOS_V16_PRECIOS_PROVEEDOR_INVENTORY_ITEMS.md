# UI ERP Pedidos v16 - Precios proveedor en inventory_items

## Corrección de rumbo

Supabase no debe usar `supplier_prices` como fuente principal para Pedidos.

Modelo real confirmado:

```text
inventory_items.primary_supplier_price
inventory_items.pascal_price
```

Interpretación:

- `primary_supplier_price`: precio del proveedor principal del item.
- `pascal_price`: precio Pascal cuando el item tiene precio alternativo Pascal.

## Migración corregida

La migración desde SQLite local `supplier_prices` ahora actualiza `inventory_items`:

- proveedor Pascal → `pascal_price`
- cualquier otro proveedor → `primary_supplier_price`

También guarda metadata en `source_row.supplier_price_migration`.

## Comandos

Preview:

```powershell
python gestorwoo.py cloud-migrate-supplier-prices-preview
```

Ejecutar:

```powershell
python gestorwoo.py cloud-migrate-supplier-prices-execute --confirm MIGRAR_PRECIOS_PROVEEDOR
```

## Datos locales encontrados

SQLite local:

```text
GestorWoo/data/gestorwoo.sqlite3
supplier_prices: 435 filas
```

Distribución:

```text
Cipta: 27
Ekomat: 203
Hemei: 22
Pascal: 183
```

Ejemplos de doble proveedor:

```text
606001 → Ekomat precio 1 + Pascal precio 2
606002 → Ekomat precio 1 + Pascal precio 2
```

## Uso posterior en Pedidos

```text
Si proveedor = Pascal → usar inventory_items.pascal_price
Si proveedor != Pascal → usar inventory_items.primary_supplier_price
```

## Seguridad

- No toca WooCommerce.
- No toca stock.
- No crea pedidos.
- Solo actualiza columnas de precio proveedor en inventory_items.
- Genera audit log y snapshot resumen.

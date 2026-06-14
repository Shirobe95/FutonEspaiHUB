# UI ERP v35 - Precio manual en pedidos + import de items faltantes

## Problema 1: precio manual pisado al recalcular

Al completar un precio proveedor manualmente en una línea de pedido, al pulsar **Calcular pedido** no debe volver a resolver precio desde Supabase y pisar ese valor.

### Solución

El editor de línea ahora marca:

```text
ui_manual_supplier_price = true
supplier_price_source = manual_order_editor
supplier_price_matched_by = manual
```

Y `_fill_supplier_prices_for_order_items()` preserva ese precio manual.

También se añadieron campos al editor de línea:

```text
Rotación C
Bultos
```

porque la fórmula real los necesita.

## Problema 2: items nuevos no existen en Supabase

Se generó CSV desde los archivos subidos:

```text
docs/imports/E-2026-03_inventory_items_from_upload.csv
```

Fuente:

```text
PLANTILLA PEDIDO E-2026-03.xlsx
data.xlsx
```

El CSV contiene 78 líneas del pedido con cantidad > 0. Los items que ya existan en Supabase se saltan; los faltantes se insertan.

## Comandos nuevos

Preview:

```powershell
python gestorwoo.py cloud-import-inventory-items-csv-preview --csv docs/imports/E-2026-03_inventory_items_from_upload.csv
```

Ejecutar:

```powershell
python gestorwoo.py cloud-import-inventory-items-csv-execute --csv docs/imports/E-2026-03_inventory_items_from_upload.csv --confirm IMPORTAR_ITEMS
```

## Seguridad

- No toca WooCommerce.
- No toca stock.
- Inserta solo items faltantes en `inventory_items`.
- Genera snapshot y audit log.
- No sobrescribe items existentes.

# UI ERP v36 - Import 12 items faltantes con rotación completa

## Objetivo

Completar los 12 items que faltaban en Supabase para poder calcular pedidos E-2026-03 sin introducir precio/rotación manual.

## Archivos actualizados

```text
docs/imports/E-2026-03_inventory_items_from_upload.csv
docs/imports/E-2026-03_12_items_faltantes_completos.csv
docs/imports/SQL_IMPORT_12_ITEMS_FALTANTES_E_2026_03.sql
```

## Rotaciones añadidas

```text
758087 -> 0.02
759005 -> 0.01
759006 -> 0.02
759008 -> 0.02
759007 -> 0.02
759009 -> 0.01
759010 -> 0.01
770002 -> 0.02
770008 -> 0.02
780008 -> 0.02
780010 -> 0.03
780014 -> 0.01
```

## Comandos recomendados

Preview solo de los 12:

```powershell
python gestorwoo.py cloud-upsert-inventory-items-csv-preview --csv docs/imports/E-2026-03_12_items_faltantes_completos.csv
```

Ejecutar:

```powershell
python gestorwoo.py cloud-upsert-inventory-items-csv-execute --csv docs/imports/E-2026-03_12_items_faltantes_completos.csv --confirm IMPORTAR_ITEMS
```

## Alternativa SQL

Ejecutar en Supabase SQL Editor:

```text
docs/imports/SQL_IMPORT_12_ITEMS_FALTANTES_E_2026_03.sql
```

## Seguridad

No toca WooCommerce.  
No toca stock.  
Solo inserta/actualiza ficha base de inventory_items para cálculo de pedidos.

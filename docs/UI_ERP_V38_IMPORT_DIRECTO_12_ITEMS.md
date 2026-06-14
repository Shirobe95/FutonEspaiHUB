# UI ERP v38 - Import directo 12 items

## Problema

El BAT llamaba a `gestorwoo.py cloud-upsert-inventory-items-csv-execute`, pero en algunas ejecuciones Windows/argparse terminaba mostrando la ayuda general del CLI en vez de ejecutar el subcomando.

## Solución

Se añade un script directo:

```text
GestorWoo/importar_12_items_e_2026_03.py
```

Este script no pasa por el CLI general. Hace directamente:

```text
login Supabase
→ upsert_inventory_items_csv()
→ preview o execute
```

## BATs actualizados

```text
PREVIEW_IMPORTAR_12_ITEMS_E_2026_03.bat
IMPORTAR_12_ITEMS_E_2026_03.bat
```

Ahora llaman:

```text
python GestorWoo/importar_12_items_e_2026_03.py
```

con ruta absoluta al CSV.

## Alternativa SQL

También se copia en raíz:

```text
SQL_IMPORT_12_ITEMS_FALTANTES_E_2026_03.sql
```

Si el script falla por permisos/RLS, se puede ejecutar ese SQL directamente en Supabase SQL Editor.

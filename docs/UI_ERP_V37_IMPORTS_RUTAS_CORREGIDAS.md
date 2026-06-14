# UI ERP v37 - Imports con rutas corregidas

## Problema

Al ejecutar desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-import-inventory-items-csv-preview --csv docs/imports/E-2026-03_inventory_items_from_upload.csv
```

fallaba porque buscaba el CSV en:

```text
GestorWoo/docs/imports/...
```

pero el archivo estaba en:

```text
docs/imports/...
```

en la raíz del proyecto.

## Solución

1. Se duplican los CSV de importación en:

```text
docs/imports/
GestorWoo/docs/imports/
```

2. El servicio `inventory_item_import.py` ahora resuelve rutas robustamente:

- desde raíz
- desde `GestorWoo`
- rutas relativas
- rutas absolutas

3. Se añaden BATs opcionales:

```text
PREVIEW_IMPORTAR_12_ITEMS_E_2026_03.bat
IMPORTAR_12_ITEMS_E_2026_03.bat
```

## Comando recomendado desde GestorWoo

```powershell
python gestorwoo.py cloud-upsert-inventory-items-csv-preview --csv docs/imports/E-2026-03_12_items_faltantes_completos.csv
```

Ejecutar:

```powershell
python gestorwoo.py cloud-upsert-inventory-items-csv-execute --csv docs/imports/E-2026-03_12_items_faltantes_completos.csv --confirm IMPORTAR_ITEMS
```

## Alternativa desde raíz

```powershell
cd work_pedidos_v9
.venv_erp\Scripts\python.exe GestorWoo\gestorwoo.py cloud-upsert-inventory-items-csv-preview --csv docs/imports/E-2026-03_12_items_faltantes_completos.csv
```

# UI-ERP Inventario - cambios aplicados

## Archivo modificado

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

## Cambios

- El precio mostrado en Inventario ahora usa `woo_price` como precio de referencia.
- Se corrigió el mapeo de materiales:
  - `materials` -> Materiales.
  - `subgroup` -> Subgrupo.
- Se separaron campos reales:
  - Medidas desde `size`.
  - M3 desde `cubic_meters`.
  - Stock tienda desde `store_stock`.
  - Stock almacén desde `warehouse_stock`.
  - Stock total como suma de tienda + almacén.
- Se ampliaron los datos internos de `InventoryItem` para conservar los campos reales del inventario.
- El panel de detalle rápido ahora tiene scroll interno.
- El detalle completo ahora tiene scroll interno en la zona de detalles del item.
- Se quitaron textos de ruido y acciones extra del detalle rápido.
- La exportación de inventario exporta los items visibles en ese momento.
- Los historiales de precio y stock ya no muestran valores inventados: quedan como zonas preparadas para historiales reales futuros.

## Verificación

- `python -m compileall -q GestorWoo/src`
- `PYTHONPATH=src python -m pytest -q`
- Resultado: 11 tests OK.

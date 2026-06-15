# FutonHUB - Corte 004C1 inventory field editing

Fecha: 2026-06-15

Commit real:

```text
5a1e2ee1b645eb21784cec41e12bbf578b44cf1a
fix: restrict inventory field editing scope
```

Hash padre:

```text
87c053f0e0dd2ccab898cb514214d4ce5b361bac
```

Estado de push:

```text
Pushed a origin/refactor/modularizacion-v1
```

Commit funcional inicial del corte:

```text
f0ebc14c506e94464f45c1cd01e939f062ceccb3
refactor: extract inventory field editing
```

## Alcance

Extraccion controlada de helpers de edicion de campos de Inventario a:

```text
GestorWoo/src/futonhub/ui/erp/inventory_edit.py
```

Se mantiene `FutonHubErpPrototype` como adaptador principal. La ventana de detalle completo sigue invocando los mismos metodos y textos.

## Archivos tocados

- `GestorWoo/src/futonhub/ui/erp/inventory_edit.py`
- `GestorWoo/src/futonhub/ui/erp/prototype.py`
- `GestorWoo/tests/test_characterization_inventory_edit.py`
- `auditoria/CODEX_CORTE_004C1_INVENTORY_FIELD_EDITING.md`

Archivo de tests:

```text
GestorWoo/tests/test_characterization_inventory_edit.py
```

## Simbolos movidos

- `ErpInventoryEditMixin._inventory_editable_initial_values`
- `ErpInventoryEditMixin._collect_inventory_detail_changes`
- `ErpInventoryEditMixin._editable_detail_row`
- `ErpInventoryEditMixin._open_inventory_changes_review`
- `ErpInventoryEditMixin._apply_inventory_detail_changes`
- `ErpInventoryEditMixin._after_inventory_item_updated`

## Dependencias preservadas

- Servicio existente: `update_inventory_item_fields`.
- Preview/log/snapshot: preservados dentro del servicio existente; no se modificaron servicios.
- Confirmacion de servicio: `update_inventory_item_fields` sigue generando `OperationSnapshot` con `write_snapshot(...)` antes del update y `AuditEvent` con `write_audit_event(...)` despues del update.
- Advertencia UI: se conserva el texto "Los cambios son internos del HUB. WooCommerce no se toca desde esta ventana."
- Refresco posterior: se conserva `_refresh_inventory(..., allow_empty=True)` tras aplicar cambios.
- WooCommerce: no se toca desde este flujo.

## Campos editables

Filas editables presentadas por la ventana de detalle completo:

- `name` / Nombre
- `family` / Familia
- `subgroup` / Subgrupo
- `size` / Medidas
- `materials` / Materiales
- `cubic_meters` / M3 unidad
- `rotation_c` / Rotacion C
- `packages` / Bultos
- `primary_supplier_price` / Precio proveedor
- `pascal_price` / Precio Pascal
- `notes` / Notas internas

Campos visibles como solo lectura en 004C1:

- `commercial_status` / Estado comercial: el servicio existente lo rechaza.
- `heca_reference` / HECA reference: el servicio existente lo rechaza.
- `woo_sku` / Woo SKU: el servicio existente lo rechaza.
- `store_stock` / Stock tienda: reservado al Corte 004C2 de movimientos de stock.
- `warehouse_stock` / Stock almacen: reservado al Corte 004C2 de movimientos de stock.

Whitelist real del servicio existente que queda usada por 004C1:

- `name`
- `family`
- `subgroup`
- `materials`
- `size`
- `cubic_meters`
- `rotation_c`
- `packages`
- `primary_supplier_price`
- `pascal_price`
- `notes`

Correccion previa al smoke: la UI ya no ofrece como editables `commercial_status`, `heca_reference`, `woo_sku`, `store_stock` ni `warehouse_stock`. No se amplio la whitelist del servicio.

## Valores vacios

Representacion en UI/mixin:

- valores `None` o cadena vacia en numericos se muestran como `""`;
- valores texto vacios se muestran como `""`;
- en el preview de cambios, un valor vacio se muestra como `Sin definir`;
- al aplicar, la comparacion usa `strip()` y envia el valor nuevo como texto al servicio;
- el servicio normaliza texto vacio a `None`;
- el servicio normaliza numericos mediante `_coerce_optional_float`, por lo que numericos vacios quedan como `None`.

## Exclusiones

No se movieron ni modificaron:

- movimientos de stock;
- creacion de items;
- exportacion;
- packs/componentes;
- propuestas de precio;
- escritura Woo;
- esquemas o migraciones.

## Tests

Suite previa:

```text
Ran 64 tests in 0.088s
OK
```

Tests anadidos:

- `test_initial_editable_values_preserve_item_fields`
- `test_collect_changes_detects_real_changes`
- `test_collect_changes_treats_blank_field_as_change_when_previous_value_exists`
- `test_noop_review_reports_no_pending_changes`
- `test_apply_changes_calls_internal_inventory_service_and_does_not_touch_woo`
- `test_apply_changes_reports_service_failure_without_destroying_review`
- `test_after_inventory_item_updated_refreshes_current_inventory_view`
- `test_unsupported_fields_are_reserved_readonly_rows`
- `test_stock_fields_are_not_part_of_004c1_editable_rows`
- `test_unsupported_and_stock_fields_are_not_collected_for_service_payload`
- `test_empty_optional_numeric_becomes_none_in_existing_service_preview`

Suite final:

```text
Ran 75 tests in 0.111s
OK
```

## Checklist manual

- Abrir ERP mediante `Abrir ERP.bat`.
- Login.
- Inventario: seleccionar item.
- Abrir detalle completo.
- Confirmar aviso de que WooCommerce no se toca.
- Editar un campo interno y revisar preview de cambios.
- Cancelar sin aplicar.
- Repetir cambio y guardar.
- Confirmar mensaje con `operation_id`.
- Confirmar refresco del item en Inventario.
- Confirmar que WooCommerce no cambia.

Resultado manual aprobado:

- Edicion de campos internos correcta.
- Preview correcto.
- Cancelacion sin cambios.
- Guardado y refresco correctos.
- Persistencia confirmada.
- `commercial_status`, `heca_reference`, `woo_sku`, `store_stock` y `warehouse_stock` visibles como solo lectura.
- WooCommerce no se modifica.
- Cierre sin traceback.

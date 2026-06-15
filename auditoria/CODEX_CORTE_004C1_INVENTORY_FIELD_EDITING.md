# FutonHUB - Corte 004C1 inventory field editing

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract inventory field editing
```

## Alcance

Extraccion controlada de helpers de edicion de campos de Inventario a:

```text
GestorWoo/src/futonhub/ui/erp/inventory_edit.py
```

Se mantiene `FutonHubErpPrototype` como adaptador principal. La ventana de detalle completo sigue invocando los mismos metodos y textos.

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
- Advertencia UI: se conserva el texto "Los cambios son internos del HUB. WooCommerce no se toca desde esta ventana."
- Refresco posterior: se conserva `_refresh_inventory(..., allow_empty=True)` tras aplicar cambios.
- WooCommerce: no se toca desde este flujo.

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

Suite final:

```text
Ran 71 tests in 0.095s
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

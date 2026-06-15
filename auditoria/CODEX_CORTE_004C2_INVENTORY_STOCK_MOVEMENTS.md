# FutonHUB - Corte 004C2 inventory stock movements

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract inventory stock movements
```

## Alcance

Extraccion del flujo de movimientos de stock interno a:

```text
GestorWoo/src/futonhub/ui/erp/inventory_stock.py
```

`FutonHubErpPrototype` permanece como adaptador principal. El detalle lateral y el detalle completo abren el mismo popup de movimiento de stock.

## Simbolos movidos/anadidos

- `ErpInventoryStockMixin._open_inventory_stock_preview_modal`
- `ErpInventoryStockMixin._inventory_stock_form_values`
- `ErpInventoryStockMixin._inventory_stock_preview_text`
- `ErpInventoryStockMixin._apply_inventory_stock_change`

## Flujo preservado

- Stock tienda y stock almacen se tratan como valores separados.
- El popup usa "Nuevo stock tienda" y "Nuevo stock almacen", igual que el servicio actual de ajuste absoluto.
- Motivo obligatorio en UI antes de previsualizar o aplicar.
- Preview mediante `preview_internal_inventory_update`.
- Aplicacion mediante `update_internal_inventory_item`.
- El servicio existente conserva bloqueo de negativos.
- El servicio existente conserva `operation_id`, snapshot y audit log.
- WooCommerce no se toca.
- Tras aplicar se refresca Inventario mediante `_after_inventory_item_updated`.

## Exclusiones

No se modificaron:

- edicion generica de campos;
- creacion de items;
- exportacion;
- packs/componentes;
- propuestas de precio;
- WooCommerce;
- esquemas o migraciones;
- reglas comerciales del servicio.

## Tests

Suite previa:

```text
Ran 75 tests in 0.111s
OK
```

Tests anadidos:

- `test_stock_movement_requires_reason`
- `test_preview_keeps_store_and_warehouse_separate`
- `test_existing_service_blocks_negative_store_stock`
- `test_apply_uses_existing_service_and_preserves_operation_id`
- `test_apply_does_not_touch_woocommerce`

Suite final:

```text
Ran 80 tests in 0.114s
OK
```

## Checklist manual pendiente

- Abrir ERP mediante `Abrir ERP.bat`.
- Login.
- Inventario: seleccionar item real.
- Abrir `Movimiento stock` desde detalle lateral.
- Probar preview con tienda o almacen.
- Confirmar que motivo vacio bloquea.
- Confirmar que stock negativo queda bloqueado.
- Aplicar movimiento controlado.
- Confirmar `operation_id`.
- Confirmar refresco posterior.
- Confirmar Historial de stock.
- Confirmar audit log y snapshot.
- Confirmar WooCommerce intacto.
- Restaurar valor original con otro movimiento controlado.
- Cerrar sin traceback.

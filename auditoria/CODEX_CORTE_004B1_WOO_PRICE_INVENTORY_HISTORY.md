# FutonHUB - Corte 004B.1 Woo price events in inventory history

Fecha: 2026-06-15

Commit previsto:

```text
fix: persist Woo price events in complete inventory history
```

## Alcance

El historial de Inventario pasa a recibir eventos de precio Woo verificados en `inventory_change_history`.
No se sustituyen `audit_logs` ni `operation_snapshots`.

Correccion posterior al smoke test manual: la afirmacion inicial de que no habia cambios de esquema ya no es valida para Supabase real. `inventory_change_history` existe en SQLite legacy y el codigo cloud la consume, pero no aparece creada por las migraciones Supabase del repositorio. El smoke test devolvio `PGRST205: Could not find the table 'public.inventory_change_history' in the schema cache`. Queda documentado en `auditoria/CODEX_DIAGNOSTICO_SCHEMA_INVENTORY_HISTORY_004B1.md`; no se ha ejecutado migracion.

## Simbolos tocados

- `futonhub.cloud.services.inventory.resolve_inventory_item_id_for_woo_price_event`
- `futonhub.cloud.services.inventory.record_woo_price_inventory_history`
- `futonhub.cloud.services.inventory.sync_woocommerce_price_inventory_state`
- `futonhub.cloud.services.woocommerce_publish.publish_woocommerce_price`
- `futonhub.cloud.services.security_logs.restore_snapshot_to_previous_state`
- `futonhub.ui.erp.inventory_detail._load_inventory_history`
- `futonhub.ui.erp.inventory_detail._render_inventory_history`
- `futonhub.ui.erp.inventory_detail._render_inventory_history_error`

## Flujo de persistencia

Publicacion Woo:

1. Woo se escribe y se relee.
2. El precio efectivo verificado se compara con la propuesta.
3. Se resuelve `inventory_items.item_id` por identidad interna, `woo_id` o, como fallback, referencia/SKU.
4. Se actualiza `inventory_items.woo_price`, columna usada por Inventario para mostrar `Precio Woo`.
5. Se inserta una fila idempotente en `inventory_change_history` con `woo_price`, precio anterior, precio nuevo, `operation_id` y metadatos.
6. `audit_logs` y `operation_snapshots` siguen siendo la caja negra tecnica.

Rollback Woo:

1. Woo se restaura desde snapshot y se relee.
2. Se actualiza `inventory_items.woo_price` con el precio restaurado.
3. Se registra un segundo evento `woo_price` con el precio antes del rollback y el precio restaurado.
4. No se elimina ni sobrescribe el evento de publicacion.

Si no se puede resolver `item_id`, no se inventa asociacion y el resultado conserva diagnostico en `inventory_history_resolution`.

Si Woo queda escrito/verificado pero falla `inventory_items` o `inventory_change_history`, la operacion no se declara completamente exitosa. Se registra una operacion parcial critica con el mismo `operation_id` y se debe reintentar solo la sincronizacion interna sin volver a publicar Woo.

## Diagnostico de causa raiz

- `Precio Woo` en Inventario se construye desde `inventory_items.woo_price`.
- El primer intento de 004B.1 actualizaba Woo y el espejo `products`/`product_variations`; no cerraba `inventory_items.woo_price`.
- El helper de historial podia devolver fallo sin lanzar excepcion, por lo que la UI podia mostrar exito aunque Inventario/historial hubieran fallado.
- La escritura de historial ahora tolera nombres reales observados en el codigo legacy: `field_name`, `change_source`, `item_name`, ademas de los nombres cloud usados por el servicio.
- Diagnostico posterior: la sincronizacion de `inventory_items.woo_price` ya se confirma correcta en publicacion y rollback reales; el bloqueo restante es exclusivamente de esquema/exposicion de `public.inventory_change_history` en Supabase.

## Tests

Comando previo:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado previo: 55 tests OK.

Tests anadidos:

- `test_publish_128_to_138_generates_woo_price_history_for_item`
- `test_rollback_138_to_128_appends_second_history_event_without_deleting_publish_event`
- `test_same_operation_id_does_not_duplicate_inventory_history`
- `test_unresolved_item_id_leaves_diagnostic_without_inventing_history`
- `test_inventory_mirror_failure_does_not_declare_publish_success`
- `test_inventory_history_failure_does_not_declare_publish_success`
- `test_internal_retry_sync_does_not_write_woo_again`
- `test_ambiguous_sku_resolution_does_not_associate_wrong_item`
- `test_variable_product_uses_internal_identity_before_sku`

Resultado final:

```text
Ran 64 tests in 0.104s
OK
```

## Checklist manual SKU 0201014

- Abrir ERP con `Abrir ERP.bat`.
- Buscar SKU/item `0201014` en Inventario.
- Abrir detalle y comprobar bloque `Historial completo`.
- Publicar propuesta Woo 128 -> 138 una sola vez y confirmar relectura Woo.
- Volver a Inventario y refrescar detalle del item.
- Confirmar que `Precio Woo` muestra 138.00.
- Confirmar evento `woo_price` 128.00 -> 138.00 en historial.
- Ejecutar rollback real desde Seguridad/snapshot de publicacion.
- Volver a Inventario y refrescar detalle del item.
- Confirmar que `Precio Woo` muestra 128.00.
- Confirmar segundo evento `woo_price` 138.00 -> 128.00.
- Confirmar que el evento de publicacion sigue visible.
- Confirmar que `audit_logs` y `operation_snapshots` siguen visibles desde Seguridad.

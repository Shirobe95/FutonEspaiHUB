# FutonHUB v8.5 - Pedido simulado Worker

Objetivo: probar una acción operativa más cercana al trabajo real sin tocar inventario ni WooCommerce.

## Qué hace

- Worker crea o actualiza un pedido simulado en `supplier_orders`.
- Crea una línea simulada en `supplier_order_items`.
- Genera `audit_log` mediante RPC Caja Negra.
- Genera `operation_snapshot` si el pedido ya existía.
- Admin puede revisar logs/snapshots y limpiar la prueba.

Datos de prueba usados:

- `order_file`: `TEST_WORKER_ORDER`
- `provider`: `TEST_WORKER`
- `item_code`: `TEST-SKU-001`

## SQL recomendado

Ejecutar en Supabase:

`docs/supabase/10_rpc_clean_worker_order_v8_5.sql`

Este SQL permite limpiar el pedido simulado desde admin sin dar permisos generales de borrado a workers.

## Comandos

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-worker-order-test
python gestorwoo.py cloud-clean-worker-order-test
```

## Prueba visual

1. Abrir HUB.
2. Login como worker.
3. Pulsar `Pedido simulado`.
4. Confirmar que el worker no ve logs/snapshots.
5. Reiniciar o login como admin.
6. Revisar `Logs cloud` y `Snapshots cloud`.
7. Pulsar `Limpiar pedido test`.

## Seguridad

No toca:

- WooCommerce
- Inventario real
- Pedidos reales
- Productos reales

La limpieza solo borra `TEST_WORKER_ORDER` si está marcado como test en `source_row`.

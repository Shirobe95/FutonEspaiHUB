# FutonEspai HUB v8.6 - Inventario simulado Worker

Objetivo: probar un flujo operativo más cercano al trabajo real de tienda sin tocar inventario real ni WooCommerce.

## Qué prueba

- Login real como worker.
- Creación/actualización de un item de inventario simulado en `inventory_items`.
- Escritura de `audit_logs` mediante caja negra RPC.
- Escritura de `operation_snapshots` cuando ya existe estado previo.
- Lectura posterior desde admin.
- Limpieza admin mediante RPC segura.

## Dato de prueba

La prueba usa siempre:

- `item_id = -900001`
- `name = TEST_WORKER_INVENTORY_ITEM`
- `family = TEST`
- `subgroup = WORKER_SIMULATION`
- `woo_link_status = TEST_NO_WOO`

No se debe usar como inventario real.

## SQL necesario

Ejecutar en Supabase > SQL Editor:

```txt
docs/supabase/11_rpc_clean_worker_inventory_v8_6.sql
```

## Prueba visual

1. Abrir el HUB.
2. Login como worker.
3. Pulsar `Inventario simulado`.
4. Repetir una segunda vez para forzar snapshot del estado anterior.
5. Login como admin.
6. Abrir `Logs cloud` y `Snapshots cloud`.
7. Pulsar `Limpiar inventario test`.

## Prueba por consola

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-worker-inventory-test
python gestorwoo.py cloud-worker-inventory-test
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
python gestorwoo.py cloud-clean-worker-inventory-test
```

## Seguridad

- El worker puede crear/actualizar el dato de prueba.
- El worker no ve logs/snapshots.
- Solo admin puede limpiar el dato por RPC.
- WooCommerce no participa.

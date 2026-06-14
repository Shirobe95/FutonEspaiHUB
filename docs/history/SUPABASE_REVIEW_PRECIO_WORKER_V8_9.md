# FutonHUB v8.9 · Revisión admin de propuesta worker simulada

Objetivo: validar el ciclo completo de tienda sin tocar WooCommerce:

1. Worker crea/actualiza `TEST_WORKER_PRICE_PROPOSAL`.
2. Admin aprueba o rechaza la propuesta.
3. Supabase actualiza `price_change_proposals.status`.
4. Caja negra genera `audit_logs` y `operation_snapshots`.
5. No se publica nada en WooCommerce.

## SQL requerido

Ejecutar en Supabase SQL Editor:

```txt
docs/supabase/13_rpc_review_worker_price_v8_9.sql
```

## Prueba visual

1. Login como worker.
2. Menú `Pruebas` → `Precio simulado`.
3. Login como admin.
4. Menú `Caja negra` → `Aprobar precio test` o `Rechazar precio test`.
5. Revisar `Logs cloud` y `Snapshots cloud`.

## Prueba por consola

```powershell
python gestorwoo.py cloud-worker-price-test
python gestorwoo.py cloud-review-worker-price-test approved
python gestorwoo.py cloud-review-worker-price-test rejected
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
```

La limpieza sigue siendo:

```powershell
python gestorwoo.py cloud-clean-worker-price-test
```

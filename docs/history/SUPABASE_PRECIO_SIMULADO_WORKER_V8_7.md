# FutonEspaiHUB v8.7 · Propuesta de precio simulada Worker

Objetivo: validar el flujo operativo de cambio de precio sin tocar WooCommerce ni precios reales.

## SQL necesario

Ejecutar en Supabase SQL Editor:

```txt
docs/supabase/12_rpc_clean_worker_price_v8_7.sql
```

## Prueba por HUB

1. Abrir HUB.
2. Login como worker.
3. Pulsar `Precio simulado` dos veces.
4. Login como admin.
5. Revisar `Logs cloud` y `Snapshots cloud`.
6. Pulsar `Limpiar precio test`.

## Prueba por PowerShell

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-worker-price-test
python gestorwoo.py cloud-worker-price-test
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
python gestorwoo.py cloud-clean-worker-price-test
```

## Datos usados

- Tabla: `price_change_proposals`
- Nombre: `TEST_WORKER_PRICE_PROPOSAL`
- `item_woo_id`: `-990001`
- Estado: `pending`

No publica nada en WooCommerce.

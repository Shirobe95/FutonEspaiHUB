# FutonHUB v7 · Modelo operativo online

Esta versión prepara el HUB para trabajo simultáneo online en Supabase sin tocar WooCommerce todavía.

## Decisión de trabajo

- **Workers**: pueden hacer trabajo operativo de tienda.
  - Inventario.
  - Pedidos.
  - Cálculo de coste.
  - Propuestas de precio.
  - Constantes operativas.
  - Consulta de productos y variaciones.

- **Admin**: puede hacer todo lo anterior y además acceder a la sala de máquinas.
  - Logs.
  - Snapshots.
  - Backups/restauración.
  - Usuarios/permisos.
  - Diagnóstico avanzado.
  - Locks.
  - Migraciones.
  - Publicación crítica hacia WooCommerce.

WooCommerce queda para el final. La prioridad ahora es validar la base operativa online con acciones seguras y reversibles.

## SQL nuevo

Ejecutar en Supabase SQL Editor:

```txt
docs/supabase/05_modelo_operativo_online_v7.sql
```

Este script:

1. Actualiza permisos `worker` y `admin`.
2. Crea tablas operativas online:
   - products
   - product_variations
   - inventory_items
   - supplier_prices
   - heca_stock
   - price_change_proposals
   - supplier_orders
   - supplier_order_items
   - business_constants
3. Activa RLS.
4. Permite que workers escriban en operaciones de tienda, pero no vean logs/backups/restauración/sala de máquinas.
5. Crea semilla de constantes del negocio.

## Comandos nuevos

Desde `FutonEspaiHUB/GestorWoo`:

```powershell
python gestorwoo.py cloud-operational-status
```

Comprueba tablas operativas Supabase con login real.

```powershell
python gestorwoo.py cloud-test-constant
```

Crea o actualiza la constante segura `TEST_FACTOR_SEGURIDAD`.

Esta prueba:
- escribe en `business_constants`;
- genera `audit_log`;
- si la constante ya existía, genera `operation_snapshot` previo;
- no afecta a cálculos reales.

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-dry-run
```

Lee la SQLite local y muestra qué tablas/filas serán candidatas para migración futura.
No sube datos.

## Botones nuevos en HUB

- `Test constante cloud`: disponible en modo Supabase. Sirve para validar escritura operativa.
- `Estado operativo cloud`: disponible para admin. Muestra tablas y permisos operativos.

## Prueba recomendada

1. Ejecuta el SQL `05_modelo_operativo_online_v7.sql`.
2. Abre el HUB.
3. Haz login Supabase.
4. Pulsa `Test constante cloud`.
5. Pulsa `Logs cloud` y confirma que aparece la operación.
6. Pulsa `Snapshots cloud`.
   - La primera vez puede no crear snapshot si no existía valor anterior.
   - La segunda vez debería crear snapshot porque ya hay valor previo.
7. Ejecuta:

```powershell
python gestorwoo.py cloud-operational-status
python gestorwoo.py migrate-sqlite-to-supabase-dry-run
```

## Estado de migración

Esta v7 NO migra productos/inventario todavía.

La ruta siguiente es:

- v8: migrador SQLite → Supabase con `--dry-run` y luego `--execute`.
- v9: módulos leyendo desde Supabase por fases.
- WooCommerce: dejar para el final, protegido con locks, snapshot, preview y log.

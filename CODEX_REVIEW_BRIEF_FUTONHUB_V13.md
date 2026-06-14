# FutonEspai HUB · Checkpoint estable v13

Fecha del checkpoint: 2026-05-27  
Estado: lógica online validada, lista para revisión externa y salto progresivo a UI ERP.

## 1. Objetivo del proyecto

FutonEspai HUB es una herramienta interna de gestión para FutonEspai. Su objetivo es centralizar operaciones que antes estaban dispersas entre WooCommerce, Excel, SQLite y procesos manuales:

- Gestión de productos y variaciones.
- Propuestas de cambios de precio.
- Publicación protegida de precios en WooCommerce.
- Inventario interno de tienda y almacén.
- Cálculo de costes individuales y de pedidos.
- Auditoría, snapshots y rollback.
- Roles de trabajo: admin y workers.

La versión v13 es un checkpoint de lógica estable. La UI actual todavía es una interfaz de laboratorio/validación, no la UI ERP final.

## 2. Decisión arquitectónica principal

Se descartó la opción de base SQLite compartida por red de Windows porque la gestión de usuarios/contraseñas y permisos compartidos resultó frágil. Se decidió usar Supabase/PostgreSQL como base central online.

Arquitectura actual:

```text
PC Admin / Workers
        |
        v
FutonHUB Python + Tkinter
        |
        v
Supabase Auth + Postgres + RLS + RPC
        |
        v
WooCommerce API, solo cuando una operación admin explícita lo requiere
```

Regla central:

- Supabase es la verdad operativa interna.
- WooCommerce es el canal público/catálogo y solo se modifica mediante publicación protegida.
- SQLite local queda como base histórica, respaldo, desarrollo o emergencia.

## 3. Roles y permisos

### Admin

Puede usar todo:

- Operaciones de tienda.
- Propuestas de precio.
- Inventario interno.
- Publicación en WooCommerce.
- Logs.
- Snapshots.
- Rollback.
- Backups/restauración.
- Diagnóstico avanzado.
- Seguridad.
- Usuarios/permisos.

### Worker

Puede hacer trabajo operativo de tienda:

- Buscar productos.
- Crear propuestas de precio.
- Aprobar/rechazar propuestas internas.
- Gestionar inventario interno.
- Trabajar pedidos/cálculos cuando se migren esos flujos.

No puede acceder al motor:

- Logs técnicos.
- Snapshots.
- Rollback.
- Backups/restauración.
- Seguridad.
- Gestión de usuarios.
- Diagnóstico avanzado.
- Publicación en WooCommerce.

Aunque el worker no vea logs ni snapshots, sus acciones generan caja negra automáticamente.

## 4. Supabase y seguridad

Se utilizan:

- Supabase Auth para login.
- Tabla `profiles` para rol y estado activo.
- RLS para ocultar datos sensibles a workers.
- RPC `security definer` para operaciones de caja negra que deben ser invisibles para workers, pero generadas por ellos.

Tablas de seguridad y operación:

- `profiles`
- `devices`
- `role_permissions`
- `audit_logs`
- `operation_snapshots`
- `notifications`
- `system_locks`
- `entity_locks`

Tablas operativas migradas/creadas:

- `products`
- `product_variations`
- `inventory_items`
- `supplier_prices`
- `heca_stock`
- `price_change_proposals`
- `supplier_orders`
- `supplier_order_items`
- `business_constants`

## 5. Caja negra: audit_logs y operation_snapshots

Cada operación relevante genera:

- `operation_id`
- usuario
- email
- rol
- máquina
- módulo
- acción
- entidad afectada
- estado
- datos antes/después cuando aplica

Diferencia conceptual:

- `audit_logs`: qué pasó, quién lo hizo, cuándo, desde dónde y con qué resultado.
- `operation_snapshots`: estado previo que permite rollback lógico.

La escritura de logs/snapshots se hace por RPC para evitar conflictos de RLS y para que los workers puedan generar caja negra sin poder verla.

## 6. Migración SQLite -> Supabase

Se migró la base local a Supabase con migración controlada.

Conteos migrados:

- `products`: 115
- `product_variations`: 614
- `inventory_items`: 235
- `supplier_prices`: 397
- `heca_stock`: 2930
- `price_change_proposals`: 7
- `supplier_orders`: 0
- `supplier_order_items`: 0

Tras pruebas, Supabase puede tener filas adicionales de test, por ejemplo item de inventario simulado o propuesta de precio test.

Comandos relacionados:

```powershell
python gestorwoo.py migrate-sqlite-to-supabase-preview
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR
```

## 7. Flujo de propuestas de precio validado

Flujo completo validado:

```text
Buscar producto/variación en Supabase
-> crear propuesta interna
-> preview obligatorio antes de guardar
-> aprobar/rechazar propuesta
-> preview WooCommerce, solo admin
-> publicación WooCommerce, solo admin con confirmación escrita
-> log + snapshot
```

La aprobación/rechazo de propuestas es operación de tienda. Admin y worker pueden hacerlo.

La publicación en WooCommerce es herramienta maestra. Solo admin.

## 8. Validaciones de precio

Se añadieron barreras contra errores peligrosos:

- Precio propuesto <= 0: ERROR bloqueante.
- Bajada mayor o igual al umbral warning: WARNING, requiere confirmación explícita.
- Bajada mayor o igual al umbral crítico: ERROR bloqueante.
- Producto padre variable sin precio propio: aviso esperado, no bloqueo.
- Variación con precio actual nulo/0: WARNING para preview/publicación, no bloqueo por sí solo.
- Producto/variación inexistente en WooCommerce: bloquea publicación.

Configuración en `.env`:

```env
GESTORWOO_PRICE_DROP_WARNING_PERCENT=30
GESTORWOO_PRICE_DROP_BLOCK_PERCENT=60
```

Pruebas de estrés realizadas:

- Precio propuesto 0: ERROR correcto.
- Bajada amarilla 40%: WARNING correcto.
- Bajada roja 65%: ERROR correcto.

## 9. WooCommerce

WooCommerce se trata con máxima precaución.

Operaciones validadas:

- Importar producto concreto de WooCommerce a Supabase.
- Importar sus variaciones.
- Crear propuesta sobre variación importada.
- Aprobar propuesta.
- Preview WooCommerce.
- Publicar una propuesta aprobada en WooCommerce.
- Marcar propuesta como `published` en Supabase.
- Actualizar espejo de precio en Supabase.
- Generar log y snapshot.

La publicación real requiere:

```powershell
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id <ID> --confirm PUBLICAR
```

Si hay warnings:

```powershell
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id <ID> --confirm PUBLICAR --ack-woo-warning
```

No existe publicación masiva en este checkpoint.

## 10. Inventario interno

Se validó inventario interno en Supabase:

- Buscar item real.
- Preview antes de aplicar.
- Cambiar `store_stock`.
- Cambiar `warehouse_stock`.
- Generar snapshot previo.
- Generar audit_log.
- WooCommerce no se toca.

Comandos:

```powershell
python gestorwoo.py cloud-search-inventory --query "tatami" --limit 20
python gestorwoo.py cloud-inventory-update-internal --item-id 201001 --store-stock 15 --notes "Prueba" --execute
```

El cambio pide confirmación escrita `APLICAR`.

## 11. Rollback desde snapshot

Se validó rollback interno desde snapshot:

- Listar candidatos.
- Distinguir soportados/no soportados.
- Preview obligatorio.
- Confirmación escrita `REVERTIR`.
- Revertir datos internos en Supabase.
- Generar nuevo audit_log.
- Generar nuevo operation_snapshot.
- No tocar WooCommerce.

Comandos:

```powershell
python gestorwoo.py cloud-rollback-candidates --limit 30
python gestorwoo.py cloud-rollback-snapshot --operation-id <OPERATION_ID>
python gestorwoo.py cloud-rollback-snapshot --operation-id <OPERATION_ID> --execute --confirm REVERTIR
```

Soporte actual de rollback:

- `inventory_items`
- `price_change_proposals`
- `business_constants`

Pendiente recomendado: ajustar rollback para que no restaure siempre `updated_at` y `updated_by` originales, sino que deje esos campos como la fecha/admin del rollback y preserve el estado anterior dentro de snapshot/log.

## 12. Comandos principales

Diagnóstico:

```powershell
python gestorwoo.py diagnostic
python gestorwoo.py cloud-diagnostic
python gestorwoo.py cloud-login-diagnostic
python gestorwoo.py cloud-operational-status
```

Productos y propuestas:

```powershell
python gestorwoo.py cloud-search-products --query "futon" --limit 15
python gestorwoo.py cloud-import-woocommerce-product --query "Test Product + Var"
python gestorwoo.py cloud-real-price-proposal --item-kind variation --woo-id 12557 --new-price 219 --notes "Prueba"
python gestorwoo.py cloud-list-real-price-proposals --status pending --limit 50
python gestorwoo.py cloud-review-real-price-proposal approved
python gestorwoo.py cloud-review-real-price-proposal rejected
```

WooCommerce:

```powershell
python gestorwoo.py cloud-woocommerce-publish-preview --proposal-id <ID>
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id <ID> --confirm PUBLICAR
```

Inventario:

```powershell
python gestorwoo.py cloud-search-inventory --query "tatami" --limit 20
python gestorwoo.py cloud-inventory-update-internal --item-id <ID> --store-stock 5 --warehouse-stock 3 --execute
```

Caja negra:

```powershell
python gestorwoo.py cloud-logs --limit 30
python gestorwoo.py cloud-snapshots --limit 30
python gestorwoo.py cloud-rollback-candidates --limit 30
```

## 13. Estado de UI

La UI actual en Tkinter ha sido usada como laboratorio funcional. Tiene lógica conectada, pero no es todavía la UI final.

Próximo objetivo visual:

- Crear UI ERP limpia.
- Separar navegación por módulos.
- Evitar botones acumulados.
- Mantener mismas funciones, pero con flujo de trabajo normal.

Estructura ERP sugerida:

```text
Dashboard
Gestion
  - Productos
  - Inventario
  - WooCommerce
  - Proveedores
Precios
  - Buscar producto
  - Crear propuesta
  - Bandeja propuestas
  - Publicacion WooCommerce
Pedidos
  - Cargar pedido
  - Pedidos en curso
  - Calculo de pedido
Calculos
  - Coste individual
  - Constantes
Seguridad/Admin
  - Logs
  - Snapshots
  - Rollback
  - Backups
  - Usuarios
  - Diagnostico
```

Para workers, ocultar Seguridad/Admin y publicación WooCommerce.

## 14. Limpieza realizada en checkpoint v13

Se reorganizó el proyecto para revisión:

- SQL Supabase en `docs/supabase/`.
- Documentación histórica en `docs/history/`.
- Scripts de administración en `scripts/admin/`.
- Scripts de migración en `scripts/migration/`.
- Scripts de prueba en `scripts/testing/`.
- Se eliminó la SQLite duplicada aislada que ya no cumple función operativa.
- Se eliminaron `__pycache__` y archivos compilados.
- Se mantuvo `.env` funcional en modo Supabase guardado, sin imprimir secretos en documentación.

## 15. Pendientes antes de producción real

- Revisar seguridad de `.env` y no subir secretos a repositorios.
- Crear `.env.example` saneado para Git/Codex.
- Consolidar tests automatizados mínimos.
- Añadir locks online en publicación WooCommerce y operaciones críticas.
- Mejorar rollback para metadatos `updated_at/updated_by`.
- Añadir limpieza/archivado de datos TEST.
- Migrar UI a patrón ERP.
- Probar pedidos reales.
- Probar constantes reales.
- Definir estrategia de backup Supabase y exportación local.

## 16. Revisión solicitada a Codex

Pedir a Codex revisar especialmente:

1. Seguridad de RLS y RPC.
2. Uso correcto de Supabase Auth/session en cliente Python.
3. Riesgos de publicar precios en WooCommerce.
4. Consistencia de snapshots/rollback.
5. Duplicación de lógica entre CLI y UI.
6. Errores de importación/migración por columnas o esquemas.
7. Posible refactor hacia capas:
   - cloud/auth
   - cloud/repository
   - services/precios
   - services/inventario
   - services/rollback
   - ui/erp
8. Pruebas automatizadas recomendadas.

## 17. Advertencias de seguridad

Este proyecto puede contener `.env` con credenciales reales. No subir el ZIP completo a GitHub público ni compartir fuera del entorno controlado.

WooCommerce solo debe modificarse desde comandos o pantallas que exijan confirmación explícita.


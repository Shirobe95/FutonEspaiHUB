# FutonHUB - Smoke tests manuales de modularizacion

Fecha de consolidacion: 2026-06-15

Regla de entrada validada en todos los cortes:

```text
Abrir ERP.bat -> GestorWoo/gestorwoo.py erp-prototype -> gestorwoo.cli -> futonhub.ui.erp.prototype
```

## Tabla acumulada

| Corte | Prueba | Resultado | Fecha | Commit | Evidencia | Incidencias |
|---|---|---|---|---|---|---|
| 001 shared UI | Apertura mediante `Abrir ERP.bat`, login, sidebar, navegacion, overlay, dashboard | Aprobado | 2026-06-15 | `e00855ca4bc1fd69151b3ebe2a6b9a0867f85a8b` | Usuario confirma smoke test manual superado tras Corte 001 | Sin incidencias funcionales reportadas |
| 002 shell/navigation | Login correcto, sidebar completo, cambio entre todas las vistas, resaltado, topbar, estado de sesion, cierre | Aprobado | 2026-06-15 | `f1a7134ac4d9fb8dce36dbd2bd58d5b8a4b22d29` | Usuario confirma ausencia de widgets superpuestos y cierre sin traceback | Sin incidencias funcionales reportadas |
| 003 dashboard | Dashboard, KPIs, tarjetas, actividad reciente, bloques de atencion, pedidos recientes, sistemas, acciones contextuales, navegacion ida/vuelta | Aprobado | 2026-06-15 | `c35b2bf661b1a5b8e4f152a6e882210d46a85b51` | Usuario confirma Dashboard correcto y sin duplicados visuales | Sin incidencias funcionales reportadas |
| 004A inventory list | Listado, columnas, recarga inicial, busqueda por codigo/SKU, busqueda textual, busqueda con/sin acentos, sin resultados, seleccion, detalle lateral, navegacion | Aprobado | 2026-06-15 | `c953a3bd4736c2cccf73ce33f5f7b7604792b03f` | Usuario confirma cierre sin traceback y comportamiento esperado del listado | Sin incidencias funcionales reportadas |
| 004B inventory detail/history | Seleccion, detalle lateral existente, historial, navegacion y cierre | Aprobado | 2026-06-15 | `6a1aa15b3e5ef5f984b49547b03919dac2433877` | Smoke manual real aprobado mediante `Abrir ERP.bat` | Deuda Unicode documentada sin corregir |
| 004B.1 Woo price inventory history | Publicacion Woo, web actualizada, `inventory_items.woo_price`, historial completo, graficas, rollback, segundo evento historico y eventos previos conservados con SKU `0201014` | Aprobado | 2026-06-15 | `a2e3e87d831897e311f7cc86ed1b943b710aa974` / docs `a3d0b7426ad42967a81c240a34d404a196fd95a3` | Usuario confirma smoke test manual aprobado tras migracion minima y recarga de schema | Sin backfill historico; no iniciar 004C1 en este cierre |
| 004C1 inventory field editing | Edicion de `notes`/`family`, preview, cancelacion sin cambios, guardado, refresco, persistencia, campos reservados solo lectura, Woo intacto y cierre | Aprobado | 2026-06-15 | `5a1e2ee1b645eb21784cec41e12bbf578b44cf1a` | Usuario confirma smoke test manual aprobado mediante `Abrir ERP.bat` | Stock reservado para 004C2; sin cambios Woo |
| 004C2 inventory stock movements | Motivo obligatorio, negativos bloqueados, cambio correcto de stock, tienda y almacen independientes, persistencia, historial, audit log, snapshot, restauracion y cierre | Aprobado | 2026-06-15 | `aea7c1f52845fb93e8346ae65040b8386d87c1c8` | Usuario confirma smoke test manual aprobado mediante `Abrir ERP.bat` | WooCommerce intacto; sin cambios funcionales posteriores al smoke |
| 004D1 inventory item creation | Creacion de items, validaciones, persistencia de `rotation_c`, `packages`, `primary_supplier_price`, `pascal_price` y `commercial_status`, refresco, detalle completo, edicion posterior, sin falsos cambios y cierre | Aprobado | 2026-06-16 | `d2c005d056d6698511c1e1aea211a680449e475b` | Usuario confirma smoke test manual aprobado mediante `Abrir ERP.bat` tras correccion de proyeccion de lectura | WooCommerce intacto; sin cambios en escrituras, RLS ni esquema |
| FUNC-001 supplier order cost and P.V.P. | Pedidos separa coste real, rentabilidad y P.V.P.; UI y exportaciones reales de Ekomat/Heimei; coste total por cantidad basado en coste real; recepcion e inventario no usan `pvp_*` | Aprobado | 2026-06-16 | `3d0f08bd7a28115cca182a8da4578f59cab55258` | Usuario confirma smoke manual aprobado en UI y exportaciones reales | Sin cambios en esquema, RLS, RPCs ni pedidos historicos |
| FUNC-002 price proposal pack composition | Propuestas de precios muestran composicion legible de packs Woo en `Nombre`; articulos normales mantienen nombre; sin consultas por fila ni cambios Woo | Pendiente | 2026-06-17 | `785989cc234e7d1e95a24a1adb98f07d5c215026` | Pendiente de smoke manual mediante `Abrir ERP.bat` | Fallback tecnico indica incidencia de datos si falta composicion enriquecida |

## Suite automatizada asociada

Comando:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado actual:

```text
Ran 107 tests
OK
```

## Notas

- Los smoke tests son manuales porque requieren UI, login y apertura mediante `Abrir ERP.bat`.
- Los tests automaticos usan dobles/mocks y no escriben en WooCommerce ni Supabase.
- No se corrigio la deuda Unicode durante esta consolidacion.

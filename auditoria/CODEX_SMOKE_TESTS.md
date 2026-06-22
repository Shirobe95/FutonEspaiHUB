# FutonHUB - Smoke tests manuales de modularizacion

Fecha de consolidacion: 2026-06-22

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
| FUNC-002I price proposal pack composition | Busqueda global oculta solo en Cambio de Precios; Items usa lista scrollable con filas compactas para simples y multilinea para packs; viewport limitado; controles y Variaciones permanecen visibles | Pendiente | 2026-06-18 | FUNC-002H `824b5b9faf0475b94c2b145076dfe90c9bce23d8` / FUNC-002I `b510998b7032ac6de71ff9aff54073e94504e783` | Pendiente de smoke manual mediante `Abrir ERP.bat` | Confirmar alturas reales, scroll, controles inferiores, variaciones, seleccion, doble clic y Anadir |
| FUNC-003 / 003A / 003B / 003C / 003D supplier order profitability, base-item resolution and Pascal fallback | Formula de margen; rentabilidad global e individual; Coste Final derivado; equivalencia numerica; packs y filas Woo/alias/componentes/sinteticas excluidas; prioridad por articulo base; Pascal real o fallback principal; entrada manual si faltan ambos precios; calculo, guardado, recarga y recepcion | Aprobado | 2026-06-22 | FUNC-003 `2cb5939` / 003A `8499a6b` / 003B `72b9158` / 003C `008cac9` / 003D `e2dfe14` | Usuario confirma smoke manual completo mediante `Abrir ERP.bat` | Sin traceback ni incidencias funcionales reportadas |

## Suite automatizada asociada

Comando:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado actual tras FUNC-003D:

```text
Ran 161 tests
OK
```

## Notas

- Los smoke tests son manuales porque requieren UI, login y apertura mediante `Abrir ERP.bat`.
- Los tests automaticos usan dobles/mocks y no escriben en WooCommerce ni Supabase.
- No se corrigio la deuda Unicode durante esta consolidacion.

## Norma Git para ahorro de tokens

Codex no debe ejecutar Git, crear commits, hacer push, actualizar ramas ni
generar informes extensos de Git salvo peticion explicita del usuario. Durante
cada corte debe limitarse a analizar, implementar, probar y resumir. Los cambios
Git se agrupan al cerrar una fase.

En iteraciones pequenas:

- no ejecutar `git status` repetidamente;
- no crear commits por cada microcambio;
- no hacer push automaticamente;
- no listar hashes ni estado de rama salvo que se solicite;
- no actualizar documentacion en cada iteracion pequena;
- mantener respuestas breves;
- informar solo problema, solucion, archivos tocados, tests y pendiente de
  smoke.

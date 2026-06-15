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
| 004B inventory detail/history | Seleccion, detalle lateral existente, historial, navegacion y cierre | Pendiente de smoke test manual real | 2026-06-15 | `6a1aa15b3e5ef5f984b49547b03919dac2433877` | Revision tecnica global aprobada; falta prueba manual real mediante `Abrir ERP.bat` | Smoke manual real pendiente; deuda Unicode documentada sin corregir |

## Suite automatizada asociada

Comando:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado actual:

```text
Ran 53 tests in 0.095s
OK
```

## Notas

- Los smoke tests son manuales porque requieren UI, login y apertura mediante `Abrir ERP.bat`.
- Los tests automaticos usan dobles/mocks y no escriben en WooCommerce ni Supabase.
- No se corrigio la deuda Unicode durante esta consolidacion.

# FutonHUB - Consolidacion modularizacion hasta Inventario detalle

Fecha: 2026-06-15

Commit documental previsto:

```text
docs: consolidate modularization progress through inventory detail
```

## Estado Git

Rama:

```text
refactor/modularizacion-v1
```

HEAD antes de este commit documental:

```text
6a1aa15b3e5ef5f984b49547b03919dac2433877
```

Base de `main`:

```text
6946d4e9091208b61a3f43d28721fe7cb57c2a14
```

Estado remoto:

```text
## refactor/modularizacion-v1...origin/refactor/modularizacion-v1 [ahead 4]
```

Los cortes 003, 004A y 004B estan confirmados localmente y pendientes de push por limite del entorno.

## Commits estructurales y documental

| Corte | Commit | Padre | Push |
|---|---|---|---|
| 001 shared UI | `e00855ca4bc1fd69151b3ebe2a6b9a0867f85a8b` | `0adf26a1bfbc3899f8c499c5195da98c0ccbfb65` | Pushed |
| 002 shell/navigation | `f1a7134ac4d9fb8dce36dbd2bd58d5b8a4b22d29` | `e00855ca4bc1fd69151b3ebe2a6b9a0867f85a8b` | Pushed |
| 003 Dashboard | `c35b2bf661b1a5b8e4f152a6e882210d46a85b51` | `f1a7134ac4d9fb8dce36dbd2bd58d5b8a4b22d29` | Pendiente |
| 004A Inventario listado | `c953a3bd4736c2cccf73ce33f5f7b7604792b03f` | `c35b2bf661b1a5b8e4f152a6e882210d46a85b51` | Pendiente |
| 004B Inventario detalle/historial | `6a1aa15b3e5ef5f984b49547b03919dac2433877` | `c953a3bd4736c2cccf73ce33f5f7b7604792b03f` | Pendiente |
| Consolidacion documental | Este commit `docs: consolidate modularization progress through inventory detail` | `6a1aa15b3e5ef5f984b49547b03919dac2433877` | Pendiente |

## Suite automatizada

Comando ejecutado:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 53 tests in 0.079s
OK
```

Desglose:

| Bloque | Tests |
|---|---:|
| Inicial checkpoint | 11 |
| Caracterizacion inicial | 29 |
| Dashboard | 3 |
| Inventario listado | 6 |
| Inventario detalle/historial | 4 |
| Total | 53 |

## Lineas actuales

```text
GestorWoo/src/futonhub/ui/erp/prototype.py: 7495 lineas
```

## Archivos Python extraidos durante la modularizacion

```text
GestorWoo/src/futonhub/ui/erp/shared_ui.py
GestorWoo/src/futonhub/ui/erp/shell.py
GestorWoo/src/futonhub/ui/erp/dashboard.py
GestorWoo/src/futonhub/ui/erp/inventory_list.py
GestorWoo/src/futonhub/ui/erp/inventory_detail.py
```

## Responsabilidades actuales por archivo

| Archivo | Responsabilidad |
|---|---|
| `shared_ui.py` | constantes visuales, dataclasses UI temporales, helpers UI compartidos y overlay |
| `shell.py` | `NAV_ITEMS`, shell, sidebar, topbar, cabecera, cambio de vista, resaltado activo y alias `inventory -> inventario` |
| `dashboard.py` | construccion visual del Dashboard, KPIs, tarjetas, actividad y recoleccion de datos del Dashboard |
| `inventory_list.py` | vista principal de Inventario, busqueda, refresco, tabla, seleccion y carga del listado |
| `inventory_detail.py` | panel lateral de detalle, filas de detalle, carga y renderizado de historial precio/stock |
| `prototype.py` | adaptador principal, login, modulos no extraidos y acciones fuera de alcance de cortes actuales |

## `prototype.py` conserva

- `FutonHubErpPrototype` y `run_erp_prototype`.
- Login y sesion.
- Edicion, stock, creacion, exportacion, packs/componentes y conexion con Precios de Inventario.
- WooCommerce.
- Cambio de Precios.
- Pedidos.
- Precio Proveedores.
- Informes / Exportaciones.
- Configuracion.
- Seguridad / Logs / Snapshots / Rollback.

## `git diff --stat main...HEAD`

Estado final tras el commit documental de consolidacion:

```text
 GestorWoo/src/futonhub/ui/erp/dashboard.py         |  292 +++++
 GestorWoo/src/futonhub/ui/erp/inventory_detail.py  |  179 +++
 GestorWoo/src/futonhub/ui/erp/inventory_list.py    |  173 +++
 GestorWoo/src/futonhub/ui/erp/prototype.py         | 1158 +-------------------
 GestorWoo/src/futonhub/ui/erp/shared_ui.py         |  397 +++++++
 GestorWoo/src/futonhub/ui/erp/shell.py             |  163 +++
 .../test_characterization_blackbox_persistence.py  |  128 +++
 GestorWoo/tests/test_characterization_dashboard.py |  161 +++
 .../tests/test_characterization_entrypoint.py      |   89 ++
 .../test_characterization_inventory_detail.py      |  165 +++
 .../tests/test_characterization_inventory_list.py  |  184 ++++
 .../tests/test_characterization_pack_components.py |  197 ++++
 .../test_characterization_woocommerce_price.py     |   87 ++
 .../test_characterization_woocommerce_rollback.py  |  185 ++++
 .../test_characterization_woocommerce_sync.py      |  206 ++++
 auditoria/AUDITORIA_FUNCIONAL_V1.md                |   46 +
 auditoria/CODEX_BASE_GIT_CARACTERIZACION.md        |  168 +++
 auditoria/CODEX_BUGS_OBSERVADOS.md                 |   61 ++
 auditoria/CODEX_CARACTERIZACION_TESTS.md           |  303 +++++
 .../CODEX_CONSOLIDACION_MODULARIZACION_004B.md     |  173 +++
 auditoria/CODEX_CORTE_001_SHARED_UI.md             |  190 ++++
 auditoria/CODEX_CORTE_002_SHELL_NAVIGATION.md      |  216 ++++
 auditoria/CODEX_CORTE_003_DASHBOARD.md             |  226 ++++
 auditoria/CODEX_CORTE_004A_INVENTORY_LIST.md       |  279 +++++
 .../CODEX_CORTE_004B_INVENTORY_DETAIL_HISTORY.md   |  255 +++++
 auditoria/CODEX_SMOKE_TESTS.md                     |   40 +
 auditoria/MAPA_FUNCIONAL_CODIGO.md                 |   66 +-
 27 files changed, 4654 insertions(+), 1133 deletions(-)
```

## Smoke tests manuales

Registro consolidado:

```text
auditoria/CODEX_SMOKE_TESTS.md
```

Estado:

- Corte 001 aprobado manualmente.
- Corte 002 aprobado manualmente.
- Corte 003 aprobado manualmente.
- Corte 004A aprobado manualmente.
- Corte 004B aprobado tecnicamente en revision global previa a esta consolidacion; smoke test manual real pendiente.

## Restricciones respetadas

- No se modificaron servicios.
- No se modificaron esquemas Supabase, RLS, RPC, tablas ni columnas.
- No se modifico el entrypoint oficial.
- No se corrigio la deuda Unicode.
- No se movio codigo funcional durante esta consolidacion documental.

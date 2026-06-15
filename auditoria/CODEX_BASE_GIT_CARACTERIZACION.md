# FutonHUB - Base Git para fase de caracterizacion

Fecha: 2026-06-14

Estado del documento:

```text
Historico inicial de la fase de caracterizacion.
Actualizado el 2026-06-15 con el estado acumulado tras Corte 004B.
```

## Rama activa

```text
## refactor/modularizacion-v1...origin/refactor/modularizacion-v1
```

## Ramas locales

```text
main                       6946d4e [origin/main] Add FutonHUB checkpoint v62.1 baseline
refactor/modularizacion-v1 6946d4e [origin/refactor/modularizacion-v1] Add FutonHUB checkpoint v62.1 baseline
```

## Ramas remotas

```text
origin/main                       6946d4e Add FutonHUB checkpoint v62.1 baseline
origin/refactor/modularizacion-v1 6946d4e Add FutonHUB checkpoint v62.1 baseline
```

## Commit base

```text
6946d4e9091208b61a3f43d28721fe7cb57c2a14
```

`main` y `refactor/modularizacion-v1` apuntan al mismo commit base:

```text
6946d4e Add FutonHUB checkpoint v62.1 baseline
```

## Diferencia actual entre `main` y `refactor/modularizacion-v1`

Comandos:

```powershell
git diff --stat main..refactor/modularizacion-v1
git diff --name-only main..refactor/modularizacion-v1
```

Resultado:

```text
Sin diferencias.
```

## Copias anidadas

Comprobaciones ejecutadas dentro del repositorio clonado:

```powershell
Get-ChildItem -Recurse -Force -Directory -Filter .git
Get-ChildItem -Recurse -Force -File -Filter CHECKPOINT_V62_1_CODEX.md
```

Resultado:

```text
Unico .git:
FutonEspaiHUB\.git

Unico checkpoint:
FutonEspaiHUB\CHECKPOINT_V62_1_CODEX.md
```

Conclusion: no existe una copia anidada ni una segunda importacion completa del proyecto dentro del repositorio de trabajo `FutonEspaiHUB`.

## Alcance autorizado

Solo queda autorizada la fase de caracterizacion:

1. Test del entrypoint y contrato de navegacion.
2. Tests de precio efectivo y payload Woo.
3. Tests de clasificacion, productos test, padres variables y enlaces.
4. Tests de persistencia de log y snapshot.
5. Tests de rollback real de `regular_price` y `sale_price`.
6. Tests de componentes de packs.

Restricciones:

- Usar dobles/mocks.
- No escribir en WooCommerce real.
- No escribir en Supabase real.
- No iniciar extraccion de UI compartida, shell, navegacion o modulos.
- Documentar bugs encontrados aparte y no corregirlos salvo que formen parte de la caracterizacion.

## Actualizacion acumulada tras Corte 004B

HEAD funcional previo al commit documental:

```text
6a1aa15b3e5ef5f984b49547b03919dac2433877
```

Commit base de `main`:

```text
6946d4e9091208b61a3f43d28721fe7cb57c2a14
```

Estado de rama:

```text
## refactor/modularizacion-v1...origin/refactor/modularizacion-v1 [ahead 4]
```

Commits acumulados desde la caracterizacion:

```text
6a1aa15 refactor: extract inventory detail and history
c953a3b refactor: extract inventory list view
c35b2bf refactor: extract dashboard view
f1a7134 refactor: extract erp shell and navigation
e00855c refactor: extract erp shared ui primitives
0adf26a Document characterization verification and observed bugs
c7722c7 Characterize inventory pack components
a019111 Characterize Woo price rollback verification
e379674 Characterize blackbox persistence checks
0c6abae Characterize Woo sync classification links
e42d6a0 Characterize Woo effective price payload
0723543 Characterize ERP entrypoint and navigation
8c25ec8 Document characterization branch baseline
```

Resumen `git diff --stat main...HEAD` tras el commit documental de consolidacion:

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

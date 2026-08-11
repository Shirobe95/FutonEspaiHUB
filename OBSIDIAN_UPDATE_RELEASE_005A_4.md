# FUTONHUB - RELEASE-005A.4 HOTFIX v0.5.0-rc.3

Status: `PUBLISHED_TO_CLIENT_BRANCH`
Date: 2026-08-11

## Contexto

- `v0.5.0-rc.2` corrigio el checksum del snapshot fisico.
- Una instalacion real via FutonHub-Launcher siguio fallando en Inventario
  porque `CatalogOperationalBaseline()` intentaba leer artefactos locales de
  auditoria: `auditoria/out/woo_map_001a_3`.
- Esa carpeta no forma parte del runtime distribuido y no debe existir en el
  cliente.

## Decision

- `v0.5.0-rc.3` elimina la dependencia runtime legacy de
  `auditoria/out/woo_map_001a_3`.
- El baseline operativo aprobado se promueve a un contrato minimo y versionado
  bajo `futonhub/runtime_config`.
- El contrato contiene 254 filas: 188 operativas y 66 en cuarentena.
- El contrato no contiene precios, stock, credenciales, rutas locales ni trazas
  de auditoria innecesarias.

## Seguridad

- Sin WooCommerce.
- Sin Supabase writes.
- Sin SQL.
- Sin precios.
- Sin stock.
- Sin costes.
- Sin proveedores.
- Sin cambios comerciales de catalogo.
- Sin cambios UI.
- Sin cambios Launcher.

## Validacion

- `py_compile`: OK.
- `compileall`: OK.
- Runtime distribuido sin `auditoria/`: PASS.
- Secuencia completa de Inventario con fake Supabase: PASS.
- Snapshot fisico: 254 filas.
- Baseline operativo: 254 filas.
- Baseline operativo: 188 operativos / 66 cuarentena.
- Suite completa `GestorWoo/tests`: 813 OK.

## Publicacion

- Commit previsto: `fix: v0.5.0-rc.3 remove runtime audit dependency`.
- Tag previsto: `v0.5.0-rc.3`.
- `refactor/modularizacion-v1` sigue siendo desarrollo/preparacion.
- `main` sigue siendo distribucion de clientes.

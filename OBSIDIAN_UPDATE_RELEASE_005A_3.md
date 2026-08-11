# FUTONHUB - RELEASE-005A.3 HOTFIX v0.5.0-rc.2

Status: `READY_FOR_RELEASE_COMMIT`
Date: 2026-08-11

## Contexto

- `v0.5.0-rc.1` quedo distribuida en `main`, pero una instalacion real via
  FutonHub-Launcher fallo al abrir Inventario por divergencia SHA-256 del
  snapshot fisico.
- La causa raiz fue el checksum raw-byte calculado desde working tree Windows
  con CRLF, mientras Git/GitHub zipball distribuyen el CSV con LF.
- No hubo cambio comercial del snapshot y Macao `0402014` permanece en
  cuarentena.

## Decision

- `v0.5.0-rc.1` = RC con bug checksum de distribucion.
- `v0.5.0-rc.2` = hotfix checksum canonico.
- Nuevo contrato de checksum:
  `checksum_mode = utf8_text_lf_v1`.
- El loader sigue fallando cerrado ante manifest invalido, modo no soportado,
  CSV manipulado o SHA incorrecto.

## Seguridad

- Sin WooCommerce.
- Sin Supabase.
- Sin SQL.
- Sin precios.
- Sin stock.
- Sin cambios UI.
- Sin nuevas funcionalidades.

## Validacion

- `py_compile`: OK.
- `compileall`: OK.
- Tests especificos checksum/runtime: 7 OK.
- Suite completa `GestorWoo/tests`: 811 OK.
- `git diff --check`: OK.
- La prueba de distribucion confirma runtime sin `auditoria/` y 254 filas
  cargadas desde `PhysicalCatalogSnapshot`.

## Pendiente tras este artefacto

- Crear commit `fix: v0.5.0-rc.2 runtime catalog checksum`.
- Crear tag `v0.5.0-rc.2`.
- Publicar primero `refactor/modularizacion-v1`.
- Promover despues a `main` por fast-forward.

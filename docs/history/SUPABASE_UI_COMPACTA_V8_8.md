# FutonEspaiHUB - Supabase UI Compacta v8.8

## Objetivo

Compactar la interfaz del HUB para evitar una fila interminable de botones durante las pruebas Supabase.

## Cambios

- Las pruebas operativas quedan agrupadas en el menú **Pruebas**.
- Las herramientas admin de auditoría quedan agrupadas en el menú **Caja negra**.
- Las limpiezas de datos TEST quedan agrupadas en el menú **Limpieza test**.
- Se mantienen los roles seguros:
  - Sin login: HUB bloqueado.
  - Worker: herramientas operativas y menú Pruebas.
  - Admin: herramientas operativas + Caja negra + Limpieza test.
- No se toca WooCommerce.
- No se toca inventario real.
- No requiere SQL nuevo.

## Nota de seguridad

La configuración mantiene `GESTORWOO_MODE=supabase_guarded`. La clave `SUPABASE_SERVICE_ROLE_KEY` no es necesaria para el uso normal del HUB y queda vacía en esta entrega.

# UI ERP Cambio de Precios v7 - ZIP corregido

## Motivo

El ZIP anterior `FutonHUB_Codex_Migr_cambio_precios_saiyan3_v7.zip` quedó mal empaquetado y solo contenía tres elementos de documentación/checkpoint, no el proyecto expandido completo.

Este paquete corrige el empaquetado y contiene el proyecto completo con la versión v7 aplicada sobre la base funcional v6.

## Cambios incluidos

- Footer compacto en Items y Variaciones con botones alineados al borde derecho.
- Barra de búsqueda de propuestas funcional.
- Búsqueda de propuestas sin sensibilidad a acentos.
- Nueva propuesta abre el editor vacío.
- Si la propuesta no tiene nombre al guardar, se solicita nombre.
- Se mantiene el editor único para nueva propuesta y modificar propuesta.
- Se conserva la carga de items reales desde Supabase en edición de propuestas.
- Se conserva el flujo de variaciones reales y añadir todas las variaciones.
- Se mantiene la eliminación de items sin repoblar automáticamente el listado.

## Nota

La aplicación de cambios reales a WooCommerce sigue estando bajo el flujo protegido de aceptar propuesta/publicación, con validaciones y logs.

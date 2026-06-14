# FutonHUB v55.3 - Contenido de packs visible en Inventario Operaciones

## Objetivo

La mejora de v55.3 coloca el contenido de los packs directamente en la pantalla diaria de Inventario dentro de Operaciones, no en WooCommerce.

## Cambios

- En el detalle lateral del item se muestra `Contenido pack` cuando el item es un `woo_pack` o tiene SKU compuesto con `|`.
- En `Abrir detalle completo` se añade un bloque visible `Contenido del pack`.
- Se añade botón `Ver contenido pack` en el detalle lateral y en el detalle completo.
- El popup consulta directamente `inventory_item_components` usando `parent_item_code = hub_item_code`, por ejemplo `WOO-PACK-3720`.
- Si la consulta no devuelve componentes, se usa fallback desde `woo_sku`, agrupando tokens por cantidad.

## Prueba recomendada

1. Abrir Operaciones > Inventario.
2. Buscar `0201001`.
3. Seleccionar `WOO-PACK-3720` o cualquier `WOO-PACK`.
4. Verificar que aparece `Contenido pack` en el panel lateral.
5. Abrir `Abrir detalle completo` y comprobar el bloque `Contenido del pack`.
6. Pulsar `Ver contenido pack` para abrir el popup independiente.

## Seguridad

- No toca WooCommerce.
- No modifica stock ni precios.
- No cambia `item_id`.
- Solo lee `inventory_item_components` y usa fallback desde `woo_sku`.

# FutonHUB v55 - Contenido visible de packs en inventario

## Objetivo

Mejorar la lectura de los resultados del buscador de Inventario interno Supabase cuando aparecen items compuestos tipo `WOO-PACK-xxxx`.

En v54 el buscador ya encontraba correctamente packs buscando por cualquiera de sus componentes. En v55 se añade visibilidad del contenido completo del pack para saber rápidamente qué contiene.

## Cambios

- El servicio de inventario en Supabase enriquece los resultados de búsqueda con todos los componentes del pack desde `inventory_item_components`.
- Para cada `woo_pack` se genera:
  - `hub_pack_components_text`, resumen en una línea.
  - `hub_pack_components_multiline`, resumen detallado para panel de detalle.
- La tabla de Inventario interno añade columna `Contenido pack`.
- La ventana añade un panel inferior `Detalle del item / contenido del pack`.
- Al seleccionar un pack, el panel muestra todos sus componentes con cantidad y nombre.
- Los alias muestran su relación base cuando está disponible.

## Ejemplo esperado

Buscando `0201001`, un resultado `WOO-PACK-3720` puede mostrar:

```text
Contenido / relación:
- 0201001 x2 · Tatami, 80 x 200 x 5,5 cm.
- 0728003 x1 · Futón Coco Plus 150x200x14,5 cm
```

## Seguridad

- No modifica WooCommerce.
- No escribe datos al buscar.
- No cambia `item_id`, que sigue siendo `int8`.
- Solo consulta `inventory_items`, `v_inventory_hub_search_ranked` e `inventory_item_components`.

## Pruebas

```text
python -m compileall -q src
pytest -q
```

Resultado local:

```text
11 passed
```

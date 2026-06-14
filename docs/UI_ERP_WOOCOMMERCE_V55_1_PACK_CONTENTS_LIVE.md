# FutonHUB v55.1 - Contenido de packs visible bajo demanda

## Objetivo

Corregir la visualización del contenido de packs en Inventario interno Supabase.

En v55 la tabla podía encontrar correctamente packs por componente, pero el contenido completo del pack podía no aparecer en la columna ni en el detalle si el enriquecimiento bulk no devolvía filas visibles desde Supabase.

## Cambio aplicado

En la ventana **Inventario interno Supabase**:

- Al seleccionar un item tipo `woo_pack` o `manual_pack`, el panel de detalle consulta directamente `inventory_item_components` por `parent_item_code`.
- Si encuentra componentes, muestra el contenido completo:

```text
Contenido del pack / relación:
- 0201001 x2 · Tatami, 80 x 200 x 5,5 cm.
- 0728003 x1 · Futón ...
```

- La columna **Contenido pack** muestra `Selecciona para ver contenido` cuando el contenido todavía no está precargado.
- El panel de detalle aumenta de altura para que el contenido sea legible.

## Seguridad

- No toca WooCommerce.
- No escribe datos al seleccionar items.
- No cambia `item_id`.
- Solo lee `inventory_item_components` bajo demanda.

## Pruebas

```text
python -m compileall -q src
pytest -q
```

Resultado:

```text
11 passed
```

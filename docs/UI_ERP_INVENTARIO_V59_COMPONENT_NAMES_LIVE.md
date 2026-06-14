# FutonHUB v59 · Nombres vivos en componentes de packs

## Objetivo
Completar la vista profesional de packs en Operaciones > Inventario.

## Regla
`inventory_item_components` conserva código y cantidad. Cuando `component_name` está vacío, el HUB resuelve el nombre desde `inventory_items` buscando, en este orden:

1. `hub_item_code`
2. `heca_reference`
3. `woo_sku` simple

De este modo el nombre visible no queda duplicado ni obsoleto.

## Resultado visual
Cada componente se muestra como tarjeta:

- Cantidad: `2x`
- ID: `0201001`
- Nombre: `Tatami, 80 x 200 x 5,5 cm.`

## Seguridad
La consulta es solo lectura. No modifica WooCommerce ni Supabase.

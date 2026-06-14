# FutonHUB v54 - Búsqueda exacta por componentes, alias y packs Woo

## Objetivo

Integrar en el buscador de inventario interno Supabase la nueva estructura de relaciones:

- Items simples de `inventory_items`.
- Alias con letra, por ejemplo `0902005A -> 0902005`.
- Packs/compuestos Woo, por ejemplo `WOO-PACK-3720 -> 0201001 x2 + 0728003 x1`.

## Requisitos previos en Supabase

Antes de usar esta versión, deben estar ejecutados los SQL del lote de pociones:

1. `001_inventory_item_components.sql`
2. `002_insert_lote1_componentes_alias.sql`
3. `003_fix_component_search_exact_DROP_RECREATE.sql`
4. `004_insert_lote2_inventory_items_pack_alias_FIXED_VALUES.sql`
5. `005_create_hub_search_exact_view.sql`
6. `006_create_hub_search_ranked_view_FIXED_COLUMNS.sql`

## Cambios en código

### Servicio cloud de inventario

Archivo:

`GestorWoo/src/futonhub/cloud/services/inventory.py`

Cambios:

- `search_cloud_inventory_items()` intenta primero buscar en `public.v_inventory_hub_search_ranked`.
- Si la vista existe, permite búsquedas exactas por:
  - `item_id`
  - `hub_item_code`
  - `heca_reference`
  - `woo_sku`
  - componente de pack
  - alias/base
- Si la vista no existe o falla, vuelve al buscador clásico en `inventory_items`.
- Se añaden a la selección los campos:
  - `hub_item_code`
  - `item_record_type`
  - `base_item_code`
  - `heca_reference`

### UI de inventario interno Supabase

Archivo:

`GestorWoo/src/futonhub/ui/erp/cloud_inventory.py`

Cambios:

- El buscador arranca con ejemplo `0201001`.
- La tabla muestra columnas nuevas:
  - Código
  - Tipo
  - Relación
- Los packs relacionados aparecen como resultados normales, pero indicando su componente relacionado.

Ejemplo esperado al buscar `0201001`:

- `0201001` como item simple directo.
- `WOO-PACK-3720` como pack que contiene `0201001 x2`.

## Seguridad

- No se toca WooCommerce.
- No se cambia el tipo de `item_id`, sigue siendo `int8`.
- No se escriben datos desde el buscador.
- Las operaciones de stock mantienen preview, confirmación, audit_log y operation_snapshot.

## Prueba recomendada

En el HUB:

1. Abrir `Inventario interno Supabase`.
2. Buscar `0201001`.
3. Verificar que aparece el item simple y los packs `WOO-PACK-...`.
4. Buscar un alias con letra, por ejemplo uno de los insertados en lote 1.
5. Verificar que aparece el alias y su relación base.

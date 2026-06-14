# FutonHUB v59.5 - Corrección real de nombres de componentes

## Fallo localizado

`search_cloud_inventory_items(..., enrich_components=False)` ignoraba el parámetro y enriquecía siempre los resultados.

Al resolver el nombre de un componente se producía este circuito:

1. El detalle del pack pedía el nombre del componente.
2. La búsqueda de Inventario encontraba el item correcto.
3. Antes de devolverlo, intentaba enriquecer otra vez los packs.
4. El enriquecimiento volvía a pedir nombres de componentes.
5. La recursión terminaba capturada silenciosamente y el nombre quedaba vacío.

## Corrección

Las dos salidas de `search_cloud_inventory_items` respetan ahora `enrich_components=False`.

Cuando el detalle del pack busca `0201001`, recibe directamente el item simple y copia únicamente `name`, sin volver a cargar relaciones de packs.

## Verificación

- Compilación correcta.
- `pytest -q`: 11 passed.

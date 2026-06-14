# FutonHUB v59.3 - nombres usando la búsqueda real del inventario

La resolución de nombres de componentes usa primero `v_inventory_hub_search_ranked`, la misma vista que ya devuelve correctamente el item simple y sus packs en Operaciones > Inventario.

Prioridades:
1. Resultado cuyo `result_item_code` coincide exactamente con el componente.
2. Resultado con `best_token_type` directo.
3. Respaldo desde `inventory_items`.

No se toma el nombre de un pack encontrado por relación como nombre del componente.

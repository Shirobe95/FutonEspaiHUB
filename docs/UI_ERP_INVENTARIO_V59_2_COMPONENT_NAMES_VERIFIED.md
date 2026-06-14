# FutonHUB v59.2 - resolución verificable de nombres de componentes

- Carga una sola vez los items visibles de `inventory_items`.
- Genera un mapa por `item_id`, `hub_item_code`, `heca_reference` y `woo_sku` simple.
- Compara códigos con y sin ceros iniciales.
- Deja de silenciar fallos de consulta.
- Si no existe coincidencia real, la UI muestra `No encontrado en inventario`.

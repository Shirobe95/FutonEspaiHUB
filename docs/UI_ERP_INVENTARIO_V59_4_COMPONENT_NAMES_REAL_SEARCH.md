# FutonHUB v59.4 - nombres usando la búsqueda real de Inventario

- El detalle del pack reutiliza `search_cloud_inventory_items`.
- Se añade `enrich_components=False` para evitar recursión al resolver nombres.
- Solo se copia el campo `name` de la coincidencia exacta.
- Ya no existe una segunda ruta de búsqueda para los nombres.

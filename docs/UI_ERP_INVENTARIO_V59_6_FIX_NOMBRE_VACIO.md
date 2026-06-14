# FutonHUB v59.6 - corrección nombre vacío en componentes

Problema localizado:
- `search_cloud_inventory_items` usaba `dict.setdefault()` para copiar `result_name` desde `v_inventory_hub_search_ranked`.
- Si `inventory_items` ya contenía la clave `name` con `NULL` o cadena vacía, `setdefault()` no la reemplazaba.
- La tabla principal podía mostrar `woo_name`, pero el resolvedor del pack solo leía `name`, por lo que terminaba como `No encontrado en inventario`.

Corrección:
- Los campos vacíos se rellenan explícitamente desde la vista ranked.
- El resolvedor usa `name`, `woo_name` y `hub_search_result_name` como cadena de respaldo.
- Se conserva `hub_search_result_name` para diagnóstico.

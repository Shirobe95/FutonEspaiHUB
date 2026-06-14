# FutonHUB v59.1 - nombres de componentes corregidos

- Sustituye placeholders como `-`, `Sin nombre visible`, `Pendiente` y `Sin definir`.
- Busca el nombre vivo en `inventory_items` por `hub_item_code`, `heca_reference`, `woo_sku` simple e `item_id`.
- Prueba variantes con y sin ceros iniciales.
- Mantiene `inventory_item_components` como tabla de relaciones, sin duplicar nombres manualmente.

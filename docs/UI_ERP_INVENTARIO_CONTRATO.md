# UI-ERP Inventario - contrato funcional

## Objetivo

Inventario muestra productos reales del HUB con cada dato en su campo correcto. Es una vista de consulta, detalle, exportación y preparación de propuestas de precio.

## Reglas de datos

- `item_id` -> ID / Código.
- `name` -> Nombre.
- `woo_price` -> Precio visible. El precio de trabajo es siempre el precio de WooCommerce porque los items se venden en la web.
- `store_stock` -> Stock tienda.
- `warehouse_stock` -> Stock almacén.
- `store_stock + warehouse_stock` -> Stock total.
- `family` -> Familia.
- `subgroup` -> Subgrupo.
- `materials` -> Materiales.
- `size` -> Medidas.
- `cubic_meters` -> M3.
- `woo_id` -> ID Woo.
- `woo_parent_id` -> ID padre Woo.
- `woo_sku` -> SKU Woo.
- `woo_name` -> Nombre Woo.
- `woo_categories` -> Categorías Woo.
- `woo_link_status` -> Estado vínculo Woo.
- `order_calculated_price` -> Coste calculado desde pedido.
- `weighted_average_cost` -> Coste medio ponderado.
- `supplier_order_qty` -> Cantidad en pedido proveedor.
- `supplier_order_provider` -> Proveedor del pedido.

## Reglas importantes

- No usar `subgroup` como material.
- No usar `size` como M3.
- No usar coste interno como precio visible.
- No inventar valores cuando un campo no existe.
- Los historiales se llenarán con registros guardados a partir de cambios futuros.

## Pantalla principal

- Barra de búsqueda.
- Botón Exportación de inventario.
- Tabla con ID, Nombre, Precio Woo, Stock y Estado.
- Panel de detalle con scroll.
- Botones fijos abajo:
  - Abrir detalle completo.
  - Agregar a Propuesta de precios.

## Detalle completo

- Modal grande.
- Detalles a la izquierda con scroll interno.
- Gráficas/historiales a la derecha.
- Si no hay historial real, mostrar que aún no hay historial registrado.

## Exportación

Exportar inventario exporta exactamente el inventario visible en la tabla en ese momento.

Ejemplo: si el usuario filtra por futones de algodón, se exportan solo los futones de algodón visibles.

La exportación debe incluir:

- ID
- Nombre
- Familia
- Subgrupo
- Materiales
- Medidas
- M3
- Stock tienda
- Stock almacén
- Stock total
- Precio Woo
- Woo ID
- Woo SKU
- Estado vínculo Woo
- Coste calculado pedido
- Coste medio ponderado
- Proveedor pedido
- Cantidad pedido
- Estado

## Acciones que no debe hacer Inventario v1

- No cambia precios directamente.
- No aplica cambios a WooCommerce.
- No modifica stock real sin flujo protegido.
- No borra productos.
- No recibe pedidos.
- No toca constantes de cálculo.

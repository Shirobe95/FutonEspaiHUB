# Changelog

## [0.4.0-rc.1] - 2026-07-03

### Añadido

- P.V.P. automático de Pedidos obtenido desde WooCommerce en vivo mediante lectura `GET`.
- Nueva fuente comercial `woo_price` para distinguir P.V.P. real de WooCommerce.
- Trazabilidad de origen de P.V.P.: WooCommerce, Manual P.V.P., Manual Margen, Margen global o Pendiente.
- Exportación de Pedidos con bloque inicial: Coste Final, Ponderado, P.V.P., Margen de Venta y Origen P.V.P.

### Cambiado

- El cálculo automático de Pedidos usa P.V.P. real de WooCommerce y calcula el Margen de Venta desde Ponderado.
- Las líneas sin edición manual intentan resolver su vínculo Woo desde `inventory_items` antes de consultar WooCommerce.
- Las ediciones manuales de P.V.P., Margen individual o Margen global conservan prioridad sobre WooCommerce.

### Corregido

- Resolución de `woo_id` para líneas crudas de pedido desde Inventario/Supabase.
- Checkbox `Usar margen global` en líneas con origen WooCommerce.
- Tratamiento controlado de productos o variaciones Woo no encontrados.
- Evita inventar P.V.P. cuando WooCommerce no devuelve un precio válido.

### Validación

- 94 tests específicos de Pedidos.
- 382 tests en la suite completa.
- `py_compile` correcto.
- AST correcto.
- Smoke manual pendiente.

### Nota

- Esta es una versión de prueba para validación mediante Launcher. No es el cierre estable final de FUNC-PED-004.

## [0.3.0] - 2026-07-03

### Añadido

- Cálculo bidireccional entre P.V.P. y Margen de Venta.
- Persistencia de la fuente comercial por línea: `global_margin`, `individual_margin` o `pvp`.
- Compatibilidad con márgenes individuales negativos derivados de un P.V.P. válido.
- Editor de artículos con cuerpo desplazable y footer fijo.

### Cambiado

- P.V.P. y Margen de Venta pasan a calcularse desde el Precio Ponderado.
- Renombrado visible de Rentabilidad a Margen de Venta.
- Orden de columnas: Coste Final, Ponderado, P.V.P. y Margen de Venta.
- Exportación alineada con el nuevo orden comercial.

### Corregido

- Conservación del último campo editado al recalcular, guardar y reabrir.
- Botones Aceptar y Cancelar ocultos en pantallas de baja altura.
- Popup confuso cuando Inventario no tenía cambios secundarios que aplicar.
- Recálculo y persistencia de márgenes individuales negativos.

### Validación

- 64 tests específicos de Pedidos.
- 352 tests en la suite completa.
- `py_compile` correcto.
- AST correcto.
- Smoke manual aprobado mediante `Abrir ERP.bat`.

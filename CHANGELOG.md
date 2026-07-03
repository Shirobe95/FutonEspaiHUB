# Changelog

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

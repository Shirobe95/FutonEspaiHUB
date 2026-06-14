# v56.2 - Cuenta para descarga en pantalla real de Pedidos

Corrección aplicada en `GestorWoo/src/futonhub/ui/erp/prototype.py`, que es la pantalla real **Operaciones > Pedidos > Calcular nuevo pedido**.

## Cambios

- `Cuenta pedido` pasa a mostrarse como `Cuenta para descarga`.
- La columna muestra `Sí`/`No`, no cantidades.
- El doble click usa `ttk.Combobox` cerrado con `Sí`/`No`.
- La ventana de completar datos aumenta tamaño para que se vean Aceptar/Cancelar.
- Al cargar Excel/PDF se guarda `source_row` dentro del `OrderItem`, para que las reglas lleguen a la tabla real.
- La descarga por producto se reparte solo entre líneas con `Cuenta para descarga = Sí`.
- Las líneas con `No` mantienen transporte por M3, pero no reciben coste fijo de descarga por unidad.

## Regla

No cuentan: funda, cover, topper, pillow(s), almohada(s).

Sí cuentan por excepción: `0727007`, `0730009`, `1242001`, `1242002`, `1243001`, `1244001`, `1245001`, `1249001`.

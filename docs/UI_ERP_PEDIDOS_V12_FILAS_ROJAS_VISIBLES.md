# UI ERP Pedidos v12 - Filas rojas visibles

## Cambio

Se corrigió un conflicto de estilo global de `ttk.Treeview`.

El estilo del ERP estaba fijando el fondo de todas las filas no seleccionadas a `CARD`, y eso pisaba los colores por `tags`. Por eso en la tabla de cálculo de Pedidos no se veían las filas rojas/amarillas aunque la lógica sí las marcaba.

## Resultado

- filas con error bloqueante: rojo
- filas con warning: amarillo
- fila seleccionada: azul índigo

## Archivo tocado

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

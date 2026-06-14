# UI ERP Pedidos v2 - Tabla normal y editor de líneas

## Cambios incluidos

### Pantalla principal de Pedidos

- Se quitó el indicador visual `Accesos rápidos` de la zona de proveedores.
- La tabla de pedidos se ordena por fecha descendente.
- La primera columna pasa de `ID Pedido` a `Pedido`, para trabajar con el nombre/identificador visible del pedido.
- En el detalle rápido se añadió un bloque de `Elementos pendientes para calcular`.

### Calcular nuevo pedido

- Se eliminó la tabla de tres zonas con columnas fijas.
- Se vuelve a una tabla normal `Treeview` con scroll vertical y horizontal.
- La tabla completa se mueve junta, evitando que la selección quede dividida entre varias tablas.
- Se mantiene el nombre de la columna final como `Coste Final del Producto`.

### Campos faltantes

- Las filas con datos pendientes se resaltan visualmente.
- Las filas con warning tienen color suave de aviso.
- Las filas correctas quedan limpias.

### Doble click en línea de cálculo

Se ubicó la lógica antigua en:

```text
CalculoCoste/coste_pedido.py
```

Zonas relevantes:

```text
estado_previo_linea()
abrir_editor_linea()
on_tree_double_click()
tree.bind("<Double-1>", on_tree_double_click)
```

En el ERP se dejó preparada la versión visual:

- doble click sobre una línea
- abre `Completar datos para calcular`
- marca en rojo campos faltantes
- permite revisar descripción, unidades, M3, precio proveedor y cuenta para descarga

La persistencia real hacia inventario se conectará cuando migremos el puente completo de cálculo desde `coste_pedido.py`.

## Verificación

Ejecutado:

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

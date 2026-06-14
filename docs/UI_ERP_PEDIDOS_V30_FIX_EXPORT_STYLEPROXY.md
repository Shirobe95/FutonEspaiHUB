# UI ERP Pedidos v30 - Fix exportación premium StyleProxy

## Problema

La exportación premium fallaba con:

```text
TypeError: unhashable type: 'StyleProxy'
```

## Causa

OpenPyXL no permite reasignar directamente algunos estilos existentes:

```python
cell.fill = cell.fill
```

Ese `cell.fill` puede ser un `StyleProxy`, que no es hashable.

## Solución

En el resaltado de estados ya no se toca el estilo existente de todas las celdas.

Ahora solo se pintan las columnas:

- Estado
- Motivos / errores

Esto conserva el formato visual general y evita el error de OpenPyXL.

## Archivo tocado

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

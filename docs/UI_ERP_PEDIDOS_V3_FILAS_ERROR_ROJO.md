# UI ERP Pedidos v3 - Filas con error en rojo

## Cambio

En la tabla de calculo de pedido, cualquier fila con error, critical, bloqueado o datos obligatorios faltantes queda con relleno rojo completo.

Objetivo:

- localizar rapido el item que impide calcular el pedido
- usar doble click sobre la fila para abrir el editor de datos faltantes
- mantener warnings en amarillo
- mantener filas OK sin relleno especial

## Regla visual

- Error / Critical / bloqueado / campos faltantes: rojo
- Warning: amarillo
- OK: normal

## Archivo modificado

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

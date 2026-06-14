# UI ERP Pedidos v7 - Cinta al warning y filas con objetivo visual

## Objetivo

Cerrar dos detalles de carga de pedidos:

1. Silenciar el warning inocuo de openpyxl sobre areas de impresion mal definidas.
2. Asegurar color visual inmediato en la tabla de calculo despues de cargar Excel/PDF.

## Warning openpyxl

Algunos Excel de proveedor traen areas de impresion con nombres definidos que openpyxl no puede resolver:

```text
UserWarning: Print area cannot be set to Defined name...
```

Este warning no afecta a la lectura de datos del pedido. Se silencia solo alrededor de `openpyxl.load_workbook()` y solo para ese mensaje.

## Colores de filas tras cargar pedido

La tabla de calculo aplica colores al cargar:

- Rojo: filas con errores o campos obligatorios faltantes.
- Amarillo: warnings no bloqueantes.
- Normal: filas OK.

Criterios rojos iniciales:

- ID / referencia pendiente.
- unidades invalidas o cero.
- M3 pendiente.
- estado error / critical / bloqueado.

## Limpieza adicional

Se elimina la fila mock `FUNDA-90` que se insertaba siempre como ejemplo en la tabla de calculo. La tabla ahora muestra solo las lineas cargadas del pedido.

## Archivos modificados

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

## Prueba recomendada

1. Abrir Pedidos.
2. Calcular nuevo pedido.
3. Cargar Excel con lineas reales.
4. Confirmar que no sale warning de area de impresion.
5. Confirmar que las filas con datos faltantes salen rojas.
6. Confirmar que no aparece una fila extra de ejemplo.

# FutonHUB v57.2 - Revisión final de fórmulas e indicadores de pedidos

## Norma operativa

El ERP se abre siempre desde `Abrir ERP.bat`. No se deben ejecutar módulos Python sueltos para las pruebas diarias.

## Objetivo

Cerrar la revisión de la tabla de Resultado del cálculo para los 4 proveedores:

- Ekomat
- Pascal
- Cipta
- Heimei

La tabla visible debe enseñar solo los valores que intervienen en la fórmula real de cada proveedor hasta llegar a `Coste Final Articulo`.

## Cambios de UI

Se elimina el indicador fijo `Tabla de calculo del pedido` junto al título `Resultado del calculo`.

En su lugar se muestran dos indicadores operativos:

- `Items: X · No descarga: Y`
- `M3 total: Z`

Donde:

- `Items` es el total de unidades del pedido.
- `No descarga` son las unidades que no participan en el reparto del coste fijo de descarga.
- `M3 total` es la suma de M3 de las líneas cargadas/calculadas.

Estos indicadores se actualizan al cargar el pedido, editar líneas y recalcular.

## Revisión de fórmula general: Ekomat / Pascal / Cipta

La tabla muestra:

1. Precio proveedor
2. IVA + RE
3. Precio compra IVA+RE
4. Transporte M3/Und.
5. Descarga/Und.
6. Coste final con descarga
7. Almacenaje + IVA
8. Picking + IVA
9. Rentabilidad %
10. Coste Final Articulo
11. Precio ponderado lote
12. Coste Total Cantidad

No se muestran columnas de dólares ni tasa de cambio porque no forman parte de esta fórmula.

La descarga fija solo se reparte entre líneas con `Cuenta para descarga = Sí`.

## Revisión de fórmula Heimei

La tabla muestra:

1. Precio proveedor
2. Precio en Dolares
3. Precio en Euros
4. Tasa cambio
5. Precio articulo EUR
6. % Transporte
7. % Descarga
8. % Varios
9. % Manipulacion
10. % Financiacion
11. Gastos aplicables
12. Coste sin almacenaje
13. Almacenaje + IVA
14. Picking + IVA
15. Rentabilidad %
16. Coste Final Articulo
17. Precio ponderado lote
18. Coste Total Cantidad

La tasa se calcula como:

`Precio en Dolares / Precio en Euros`

El precio unitario en euros se calcula como:

`Precio proveedor / Tasa cambio`

## Exportación

La exportación de auditoría de pedido mantiene las columnas equivalentes y añade en resumen:

- Unidades que cuentan para descarga
- Unidades que NO cuentan para descarga
- M3 total pedido

## Validación local

Ejecutado:

```text
python -m compileall -q GestorWoo/src/futonhub/ui/erp/prototype.py
pytest -q
```

Resultado:

```text
11 passed
```

# UI ERP Pedidos v57 - Tabla de resultado alineada con fórmulas

## Norma operativa

El HUB debe abrirse siempre desde:

```text
Abrir ERP.bat
```

Así se usa el punto de entrada real del ERP y se evitan pruebas sobre módulos sueltos.

## Problema detectado

En `Operaciones > Pedidos > Calcular nuevo pedido`, la tabla de resultado era común para todos los proveedores y mostraba cabeceras mixtas:

- `Precio dolares / Transporte`
- `Precio pagado EUR / M3 camion`
- `Tasa cambio / C.Transp. M3`

Esto hacía que pedidos generales como Ekomat/Pascal/Cipta mostraran columnas de dólares y tasa de cambio aunque su fórmula no usa esos datos.

## Revisión de fórmulas heredadas

### Ekomat / Pascal / Cipta

Fórmula general:

```text
coste_transporte_m3 = coste_transporte_iva / m3_total_camion
coste_transporte_producto = coste_transporte_m3 * m3_unidad
coste_descarga_producto = coste_total_descarga_iva / cantidad_total_productos_que_cuentan
iva_re = precio_proveedor * iva_recargo_equivalencia
precio_con_iva = precio_proveedor + iva_re
coste_final_con_descarga = precio_con_iva + coste_transporte_producto + coste_descarga_producto
coste_almacenaje_iva = coste_diario_almacenaje_m3 * m3_unidad * rotacion_c * 1.21
coste_picking_iva = ((bultos * 0.3) + 4.12) * 1.21
coste_final_articulo = coste_final_con_descarga + coste_almacenaje_iva + coste_picking_iva
```

Si hay rentabilidad configurada, se aplica al coste final unitario.

### Heimei / Tatamis importados

Fórmula con dólares y tasa:

```text
tasa_cambio = precio_dolares / precio_euros
importe_transporte = factura_transporte + derechos_aranceles
pc_transporte = importe_transporte / precio_euros * 100
pc_descarga = importe_descarga_mt * 100 / precio_euros
pc_varios = importes_varios / precio_euros * 100
pc_suma = pc_transporte + pc_descarga + pc_varios + pc_manipulacion + pc_financiacion
precio_articulo_eur = precio_proveedor_usd / tasa_cambio
gastos_aplicables = precio_articulo_eur * pc_suma / 100
coste_sin_almacenaje = precio_articulo_eur + gastos_aplicables
coste_almacenaje_iva = coste_diario_almacenaje_m3 * m3_unidad * rotacion_c * 1.21
coste_picking_iva = ((bultos * 0.3) + 4.12) * 1.21
coste_final_articulo = coste_sin_almacenaje + coste_almacenaje_iva + coste_picking_iva
```

## Cambio v57

La tabla de resultado ahora se dibuja por modo de cálculo:

### Tabla general

Muestra únicamente columnas usadas para llegar al coste final general:

- Precio proveedor
- IVA + RE
- Precio compra IVA+RE
- Transporte M3/Und.
- Descarga/Und.
- Coste final con descarga
- Almacenaje + IVA
- Picking + IVA
- Rentabilidad %
- Coste Final Articulo
- Precio ponderado lote
- Coste Total Cantidad

### Tabla Heimei

Mantiene las columnas propias de fórmula con dólares:

- Precio proveedor USD
- Tasa cambio
- Precio articulo EUR
- % Transporte
- % Descarga
- % Varios
- % Manipulación
- % Financiación
- Gastos aplicables
- Coste sin almacenaje
- Almacenaje + IVA
- Picking + IVA
- Rentabilidad %
- Coste Final Articulo
- Precio ponderado lote
- Coste Total Cantidad

## Cuenta para descarga

La columna `Cuenta para descarga` se conserva en ambos modos, pero en la fórmula general es la que decide si la línea participa o no en el reparto del coste fijo de descarga.

No cuentan por regla automática:

```text
funda, cover, topper, pillow, pillows, almohada, almohadas
```

Cuentan por excepción:

```text
0727007, 0730009, 1242001, 1242002, 1243001, 1244001, 1245001, 1249001
```

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

## Validación

```text
python -m compileall -q GestorWoo/src/futonhub/ui/erp/prototype.py
pytest -q
```

Resultado:

```text
11 passed
```

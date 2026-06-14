# UI ERP Pedidos v25 - Fix cálculo y tabla

## Error corregido

Al pulsar **Calcular pedido** fallaba con un error de argumentos.

Causa real:

```text
_money_float() aceptaba solo value
pero la fórmula legacy la llamaba como _money_float(value, default)
```

Esto generaba error al entrar en cálculo con campos opcionales como `rotation_c` o `packages`.

## Solución

`_money_float` ahora acepta:

```python
_money_float(value, default=0.0)
```

## Tabla de cálculo

Se amplía el pintado para que no queden tantas columnas como "Pendiente":

- en proveedor general muestra transporte total de referencia
- descarga total de referencia
- IVA + RE
- coste descarga
- almacenaje
- picking
- rentabilidad

Para Heimei mantiene:

- precio dólares
- precio euros
- tasa cambio
- precio artículo EUR
- factura transporte
- aranceles
- porcentajes de transporte/descarga/varios/manipulación/financiación

## Detalle completo

Los indicadores inferiores dejan de usar valores mock y leen `calculation_inputs` reales cuando existan.

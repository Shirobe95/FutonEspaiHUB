# FutonHUB v57.1 - Columnas Heimei: proveedor, pedido USD/EUR y tasa

## Objetivo

Alinear la tabla **Resultado del cálculo** de Heimei con el flujo real de la fórmula.

## Cambio visible

En **Operaciones > Pedidos > Calcular nuevo pedido**, para Heimei/Tatamis la tabla queda con este bloque de precio:

1. **Precio proveedor**: precio unitario del artículo según el proveedor.
2. **Precio pedido USD**: importe total del pedido en dólares.
3. **Precio pedido EUR**: importe total pagado del pedido en euros.
4. **Tasa cambio**: relación calculada entre USD y EUR del pedido.
5. **Precio articulo EUR**: precio unitario convertido a euros que entra en la fórmula.

## Fórmula relacionada

```text
tasa_cambio = precio_pedido_usd / precio_pedido_eur
precio_articulo_eur = precio_proveedor / tasa_cambio
```

Después siguen los porcentajes/gastos aplicables y el camino hasta **Coste Final Articulo**.

## Seguridad

No cambia la fórmula. Solo hace visible la descomposición correcta en la tabla y en la exportación de detalle.

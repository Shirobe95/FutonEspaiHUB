# FutonHUB v61 - Publicación de precio efectiva y rollback real

## Correcciones implementadas

1. La propuesta representa el precio efectivo visible en WooCommerce.
2. Si existe `sale_price` activo:
   - Si el nuevo precio es menor que `regular_price`, se actualiza `sale_price`.
   - Si el nuevo precio es igual o superior a `regular_price`, se actualiza `regular_price` y se limpia `sale_price`.
3. Si no existe rebaja activa, se actualiza `regular_price` y se limpia `sale_price`.
4. Después del PUT, FutonHUB vuelve a leer WooCommerce y verifica que `price` coincide con la propuesta.
5. Si la verificación falla, intenta compensar restaurando inmediatamente `regular_price` y `sale_price` anteriores.
6. Supabase solo se confirma después de la lectura de verificación.
7. El log exitoso usa severidad INFO o WARNING, nunca CRITICAL.
8. El snapshot de publicación Woo puede restaurarse realmente:
   - escribe el precio anterior en WooCommerce,
   - vuelve a leer Woo,
   - verifica `regular_price` y `sale_price`,
   - actualiza el espejo Supabase,
   - marca la propuesta como `rolled_back`,
   - genera un nuevo audit log.

## Prueba de aceptación recomendada

Usar una variación con rebaja activa, por ejemplo SKU 0201014:

1. Confirmar en Woo el estado inicial: regular 165, rebajado 128.
2. Crear propuesta a 138.
3. Aprobar propuesta.
4. Generar preview de publicación.
5. Publicar escribiendo PUBLICAR y aceptando warnings si aparecen.
6. Confirmar en Woo: regular 165, rebajado 138, precio visible 138.
7. Revisar log: estado OK, severidad INFO/WARNING y datos posteriores completos.
8. Pulsar Restaurar estado anterior en el snapshot.
9. Confirmar en Woo: regular 165, rebajado 128, precio visible 128.
10. Confirmar log nuevo de rollback y propuesta en estado rolled_back.

Abrir siempre mediante `Abrir ERP.bat`.

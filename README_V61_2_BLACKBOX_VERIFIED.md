# FutonHUB v61.2 · Caja negra verificada

Corrección tras detectar una publicación WooCommerce correcta que no aparecía en logs ni snapshots.

## Cambio
- El snapshot se escribe y se verifica por `operation_id` antes de tocar WooCommerce.
- Si no existe realmente en `operation_snapshots`, la publicación queda bloqueada.
- El audit log final se escribe y se verifica por `operation_id`.
- Si no queda persistido, el HUB no declara el circuito completamente cerrado.
- Se mantiene la publicación por precio efectivo y el rollback real de v61.1.

## Prueba recomendada
1. Abrir con `Abrir ERP.bat`.
2. Crear propuesta 128 -> 138 para la variación 9909 / SKU 0201014.
3. Publicar.
4. Confirmar precio efectivo 138 en WooCommerce.
5. Buscar el mismo `WOOPUBLISH-...` en `audit_logs` y `operation_snapshots`.
6. Ejecutar rollback desde ese snapshot y confirmar vuelta a 128.

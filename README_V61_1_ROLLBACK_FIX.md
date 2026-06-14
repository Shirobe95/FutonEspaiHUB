# FutonHUB v61.1 - rollback de precio

## Corrección
- El rollback Woo ya realizado y verificado no falla si la base antigua no admite `rolled_back`.
- Se incluye migración SQL para añadir `rolled_back` al CHECK de `price_change_proposals.status`.
- La ventana de confirmación informa correctamente cuando el snapshot sí tocará WooCommerce.
- La UI reconoce el estado `rolled_back` como `Restaurada`.

## Orden recomendado
1. Ejecutar `011_price_proposals_add_rolled_back_status.sql` en Supabase.
2. Abrir el ERP con `Abrir ERP.bat`.
3. Publicar una propuesta controlada.
4. Restaurar desde el snapshot del log de esa publicación.

# FutonEspaiHUB v11.4 · Publicación WooCommerce protegida

Esta versión añade la primera publicación real de precio hacia WooCommerce, pero solo con una propuesta aprobada y con triple candado.

## Qué permite

- Publicar **una sola** propuesta aprobada por operación.
- Releer WooCommerce justo antes de publicar.
- Bloquear errores rojos.
- Exigir confirmación escrita `PUBLICAR`.
- Exigir `--ack-woo-warning` si el preview tiene warnings amarillos.
- Crear `operation_snapshot` antes del cambio real.
- Crear `audit_log` después del cambio.
- Marcar la propuesta como `published` en Supabase.
- Actualizar el espejo de precio en Supabase (`products` o `product_variations`).

## Qué NO hace

- No publica en lote.
- No permite workers.
- No ignora errores rojos.
- No toca productos sin `proposal_id` concreto.
- No cambia `sale_price`; solo actualiza `regular_price`.

## Flujo recomendado

1. Crear propuesta real interna.
2. Aprobarla como admin.
3. Ejecutar preview:

```powershell
python gestorwoo.py cloud-woocommerce-publish-preview --proposal-id ID_PROPUESTA
```

4. Si hay warnings, revisarlos.
5. Publicar:

```powershell
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id ID_PROPUESTA --confirm PUBLICAR
```

Si el preview tiene warnings amarillos y decides continuar:

```powershell
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id ID_PROPUESTA --confirm PUBLICAR --ack-woo-warning
```

## Seguridad

- `new_price <= 0` bloquea.
- Producto padre variable bloquea publicación directa.
- Bajada roja configurada por `GESTORWOO_PRICE_DROP_BLOCK_PERCENT` bloquea.
- Warnings amarillos requieren confirmación extra.
- El snapshot guarda propuesta, item cloud, preview y estado Woo antes del PUT.

WooCommerce deja de estar dormido en esta versión, pero solo se despierta dentro de una jaula con tres cerraduras.

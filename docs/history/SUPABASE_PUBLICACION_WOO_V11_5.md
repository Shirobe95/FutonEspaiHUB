# FutonHUB Supabase publicación Woo protegida v11.5

Parche de seguridad para la publicación WooCommerce protegida.

## Qué corrige

En v11.4, si WooCommerce aceptaba el cambio pero Supabase no tenía la columna `price_change_proposals.published_by`, la operación podía fallar al marcar la propuesta como `published`.

v11.5 añade:

- SQL para crear `published_by` si falta.
- Recarga de schema cache de Supabase/PostgREST.
- Fallback Python: si la columna aún no aparece por cache, marca la propuesta como publicada sin perder el rastro del usuario en `source_row`.

## SQL requerido

Ejecutar en Supabase SQL Editor:

```text
docs/supabase/16_fix_price_publish_columns_v11_5.sql
```

## Reintento seguro

Si la operación anterior ya actualizó WooCommerce pero falló al marcar Supabase, puedes repetir el mismo comando:

```powershell
python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id TU_ID --confirm PUBLICAR --ack-woo-warning
```

Para el producto test, repetir el PUT con el mismo precio es idempotente a efectos prácticos: WooCommerce queda con el mismo precio y Supabase se marca como `published`.

## Nota

WooCommerce solo se toca con el comando explícito `cloud-woocommerce-publish-execute` y confirmación escrita `PUBLICAR`.

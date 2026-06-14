# v11.2 - Preview protegido de publicación WooCommerce

Esta versión añade una fase de seguridad antes de publicar precios en WooCommerce.

## Qué hace

- Lee propuestas reales con `status = approved` desde Supabase.
- Lee WooCommerce en modo solo lectura para comparar el precio actual real.
- Calcula diferencia en euros y porcentaje.
- Aplica las reglas de seguridad de precio:
  - precio propuesto `<= 0`: ERROR
  - precio actual WooCommerce vacío/0 en item vendible: ERROR
  - bajada >= `GESTORWOO_PRICE_DROP_BLOCK_PERCENT`: ERROR
  - bajada >= `GESTORWOO_PRICE_DROP_WARNING_PERCENT`: WARNING
  - old_price de propuesta distinto del precio actual WooCommerce: WARNING
- Genera `audit_log` del preview.
- No ejecuta `PUT` ni publica cambios en WooCommerce.

## Comando

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-woocommerce-publish-preview --limit 20
```

Para una propuesta concreta:

```powershell
python gestorwoo.py cloud-woocommerce-publish-preview --proposal-id ID_DE_PROPUESTA
```

## Resultado esperado

El resultado muestra cada propuesta aprobada con estado:

- `OK`: candidata limpia para una futura publicación.
- `WARNING`: requiere revisión admin antes de publicar.
- `ERROR`: bloqueada; no debe publicarse.

WooCommerce solo se lee. No se cambia ningún precio.

# FutonHUB v12 - Bandeja de propuestas y publicación protegida

## Objetivo

Llevar a interfaz el flujo operativo de propuestas:

- Worker y admin pueden crear, aprobar y rechazar propuestas internas.
- Solo admin puede hacer preview/publicación WooCommerce.
- Publicación WooCommerce sigue con confirmación escrita `PUBLICAR` y warnings explícitos.

## SQL opcional recomendado

Ejecutar en Supabase:

```txt
docs/supabase/17_permisos_propuestas_operativas_v12.sql
```

## Flujo de prueba

1. Login como worker.
2. Menú `Pruebas` > `Bandeja propuestas`.
3. Ver propuestas `pending`.
4. Aprobar o rechazar una propuesta.
5. Login como admin.
6. Ver logs/snapshots.
7. En bandeja, admin puede usar `Preview Woo` y `Publicar Woo`.

## Seguridad

- Aprobar/rechazar no toca WooCommerce.
- Publicar WooCommerce solo aparece para admin.
- Publicar exige confirmación escrita `PUBLICAR`.
- Warnings amarillos exigen confirmación adicional.
- Errores rojos bloquean publicación.

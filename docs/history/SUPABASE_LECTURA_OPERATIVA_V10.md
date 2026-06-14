# FutonHUB v10 - Lectura operativa desde Supabase

Objetivo: empezar a usar Supabase como base operativa interna tras la migración SQLite.

## Qué incluye

- Búsqueda de productos/variaciones reales en Supabase.
- Creación de propuesta de precio real interna sobre producto migrado.
- Revisión admin de propuesta real interna.
- Caja negra: audit_log + snapshot.
- WooCommerce NO se toca.

## Comandos

```powershell
python gestorwoo.py cloud-search-products --query "futon" --limit 15
python gestorwoo.py cloud-real-price-proposal --item-kind product --woo-id 123 --new-price 199 --notes "prueba interna"
python gestorwoo.py cloud-review-real-price-proposal approved
python gestorwoo.py cloud-review-real-price-proposal rejected
```

## Prueba visual

1. Login como worker.
2. Menú Pruebas > Buscar productos cloud.
3. Copiar `item_kind` y `woo_id`.
4. Menú Pruebas > Propuesta real precio.
5. Login como admin.
6. Caja negra > Aprobar propuesta real o Rechazar propuesta real.
7. Revisar Logs cloud y Snapshots cloud.

No publicar en WooCommerce todavía.

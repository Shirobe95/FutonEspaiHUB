# FutonEspaiHUB v12.3 · Inventario real interno Supabase

Objetivo: probar cambios operativos reales de inventario interno sobre Supabase, sin tocar WooCommerce.

## Qué incluye

- Buscar items en `inventory_items` por nombre, Woo ID, SKU, HECA o item_id.
- Previsualizar cambio de `store_stock` y/o `warehouse_stock`.
- Aplicar cambio solo tras confirmación.
- Generar `operation_snapshot` antes del cambio.
- Generar `audit_log` después del cambio.
- WooCommerce no se lee ni se modifica en este flujo.

## Comandos

Buscar inventario:

```powershell
python gestorwoo.py cloud-search-inventory --query "tatami" --limit 20
```

Preview de cambio sin aplicar:

```powershell
python gestorwoo.py cloud-inventory-update-internal --item-id 201001 --store-stock 15 --notes "Prueba inventario interno"
```

Aplicar cambio:

```powershell
python gestorwoo.py cloud-inventory-update-internal --item-id 201001 --store-stock 15 --notes "Prueba inventario interno" --execute
```

La ejecución pide confirmación escrita:

```txt
APLICAR
```

## HUB visual

Menú `Pruebas` → `Inventario real interno`.

1. Buscar item.
2. Seleccionar fila.
3. Aplicar cambio interno.
4. Ver preview.
5. Confirmar.
6. Revisar como admin en Logs/Snapshots.

## Seguridad

- Stock negativo bloqueado.
- Si no indicas tienda ni almacén, bloqueado.
- WooCommerce no se toca.
- Workers y admin pueden operar inventario interno.
- Solo admin ve caja negra.

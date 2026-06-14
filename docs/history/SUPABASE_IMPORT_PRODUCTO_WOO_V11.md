# FutonHUB v11 - Importación quirúrgica de producto WooCommerce a Supabase

Objetivo: importar **un solo producto WooCommerce** y sus variaciones a Supabase para pruebas internas de propuestas de precio.

No publica cambios en WooCommerce. Solo lee WooCommerce y actualiza Supabase.

## Caso de prueba

Producto creado en WooCommerce después de la migración:

- `Test Product + Var`
- variaciones: `Test1`, `Test2`, `Test3`

## Comandos

Desde `FutonEspaiHUB/GestorWoo`:

```powershell
python gestorwoo.py cloud-import-woocommerce-product --query "Test Product + Var"
```

O por ID del producto padre:

```powershell
python gestorwoo.py cloud-import-woocommerce-product --woo-id 12345
```

Después:

```powershell
python gestorwoo.py cloud-search-products --query "Test Product" --limit 20
```

Con el `woo_id` del producto o de una variación, se puede crear una propuesta interna:

```powershell
python gestorwoo.py cloud-real-price-proposal --item-kind product --woo-id 12345 --new-price 199 --notes "Prueba interna producto test"
python gestorwoo.py cloud-real-price-proposal --item-kind variation --woo-id 67890 --new-price 219 --notes "Prueba interna variación test"
```

La revisión sigue siendo interna:

```powershell
python gestorwoo.py cloud-review-real-price-proposal approved
python gestorwoo.py cloud-review-real-price-proposal rejected
```

## Seguridad

- Requiere login admin.
- Usa WooCommerce solo en modo lectura.
- Genera `audit_logs`.
- Genera `operation_snapshots` si el producto o variaciones ya existían en Supabase.
- No toca WooCommerce.

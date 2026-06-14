# FutonEspaiHUB v12.2 · Pruebas ataque al corazón de precios

Esta versión añade una prueba rápida para validar las tres barreras críticas de precio sin crear propuestas, sin tocar Supabase y sin tocar WooCommerce.

## Comando

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-price-heart-attack-tests --item-kind variation --woo-id 12557
```

También funciona con producto simple:

```powershell
python gestorwoo.py cloud-price-heart-attack-tests --item-kind product --woo-id 12345
```

## Qué prueba

1. Precio propuesto 0: debe devolver `ERROR`.
2. Bajada amarilla según `GESTORWOO_PRICE_DROP_WARNING_PERCENT`: debe devolver `WARNING`.
3. Bajada roja según `GESTORWOO_PRICE_DROP_BLOCK_PERCENT`: debe devolver `ERROR`, siempre que haya precio base válido.

Si el item tiene precio actual 0, vacío o nulo, la prueba de bajadas devuelve warning porque no puede calcular porcentaje real. Esto coincide con la lógica definida: precio base vacío es aviso, no bloqueo por sí mismo.

## En interfaz

En el HUB, tras login:

`Pruebas` → `Test estrés precios`

La prueba pide `item_kind` y `woo_id`, y muestra el resultado en una ventana de texto.

## Seguridad

- No crea propuestas.
- No publica en WooCommerce.
- No modifica Supabase.
- Solo ejecuta validaciones usando la misma lógica que protege el flujo real de propuestas.

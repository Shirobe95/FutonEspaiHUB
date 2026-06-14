# FutonEspaiHUB v11.1 - Validaciones de precio

Esta versión añade cinturones de seguridad antes de crear propuestas reales internas de precio.

## Reglas principales

- Precio propuesto `<= 0`: **ERROR**, bloquea.
- Producto padre variable (`type=variable`) como objetivo de propuesta: **ERROR**, bloquea. La propuesta debe hacerse sobre una variación concreta.
- Variación con precio actual vacío, nulo o `0`: **ERROR**, bloquea.
- Producto simple con precio actual vacío, nulo o `0`: **ERROR**, bloquea.
- Bajada de precio mayor o igual que `GESTORWOO_PRICE_DROP_BLOCK_PERCENT`: **ERROR**, bloquea.
- Bajada de precio mayor o igual que `GESTORWOO_PRICE_DROP_WARNING_PERCENT`: **WARNING**, requiere confirmación explícita.

## Configuración en .env

```env
GESTORWOO_PRICE_DROP_WARNING_PERCENT=30
GESTORWOO_PRICE_DROP_BLOCK_PERCENT=60
```

Valores por defecto:

- Aviso amarillo: 30%
- Bloqueo rojo: 60%

## CLI

Si una bajada supera el aviso amarillo, el comando pedirá repetir con confirmación explícita:

```powershell
python gestorwoo.py cloud-real-price-proposal --item-kind variation --woo-id 12557 --new-price 80 --notes "Prueba bajada"
```

Si el aviso es revisado y aceptado:

```powershell
python gestorwoo.py cloud-real-price-proposal --item-kind variation --woo-id 12557 --new-price 80 --notes "Prueba bajada" --ack-price-warning
```

`--ack-price-warning` no evita bloqueos rojos ni permite precios cero.

## HUB visual

En la interfaz, si una propuesta genera aviso amarillo, el HUB muestra confirmación antes de crearla.
Los errores rojos bloquean directamente.

WooCommerce no se toca en esta versión.

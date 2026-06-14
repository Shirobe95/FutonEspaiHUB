# FutonEspaiHUB v11.3 - Preview WooCommerce con warning para precio actual vacío/0

Esta versión ajusta las reglas de seguridad de precio para que el precio actual vacío, nulo o 0 en WooCommerce no sea un bloqueo rojo automático durante el preview.

## Regla ajustada

- Precio propuesto <= 0: ERROR, bloquea.
- Producto padre variable: ERROR para propuesta directa; se debe trabajar con variaciones.
- Precio actual interno vacío/0 en producto vendible: WARNING.
- Precio actual WooCommerce vacío/0: WARNING.
- Bajada superior al aviso configurado: WARNING.
- Bajada superior al bloqueo configurado: ERROR cuando se puede calcular contra un precio actual válido.

## Motivo

Un producto o variación puede existir temporalmente sin precio base, especialmente en pruebas o durante preparación de catálogo. El HUB debe avisar de forma visible, pero no bloquear toda la operación solo por no tener referencia anterior.

## Seguridad mantenida

WooCommerce sigue sin ser modificado en esta fase. El comando de preview solo lee WooCommerce y Supabase.

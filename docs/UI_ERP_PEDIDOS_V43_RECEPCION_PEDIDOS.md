# UI ERP Pedidos v43 - Recepción parcial/completa

## Objetivo

Activar el botón `Recibido` de Pedidos con flujo real sobre Supabase.

## Qué hace

Desde:

```text
Operaciones → Pedidos → Recibido
```

permite:

- Recibir pendiente completo.
- Recibir parcial por línea.
- Elegir destino:
  - Almacén
  - Tienda
- Hacer preview obligatorio.
- Confirmar recepción.

## Escrituras Supabase

Actualiza:

```text
inventory_items.store_stock
inventory_items.warehouse_stock
supplier_order_items.quantity_received
supplier_orders.status
```

Estados del pedido:

```text
Recibido parcial
Recibido completo
```

## Seguridad

- No toca WooCommerce.
- No toca Hexa.
- No permite cantidades negativas.
- Bloquea si la recepción supera cantidad pedida.
- Genera operation_snapshot.
- Genera audit_log.

## Preview

Muestra por línea:

- item
- cantidad a recibir
- stock tienda antes/después
- stock almacén antes/después
- nuevo estado esperado del pedido

## Nota

Esta es la primera versión funcional de recepción. Más adelante se conectará con lógica avanzada de stock/Hexa.

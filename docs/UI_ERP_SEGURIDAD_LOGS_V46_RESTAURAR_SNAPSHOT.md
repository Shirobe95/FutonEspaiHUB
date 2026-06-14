# UI ERP v46 - Restaurar estado anterior desde snapshot

## Objetivo

Hacer funcional el botón:

```text
Seguridad / Logs → Detalle de log → Snapshot asociado → Restaurar estado anterior
```

## Seguridad aplicada

- Solo admin.
- Solo desde snapshot asociado.
- Preview obligatorio.
- Confirmación por palabra exacta:

```text
RESTAURAR
```

- Genera audit_log de restauración.
- No toca WooCommerce.
- No toca Hexa.

## Snapshots soportados en v46

### Inventario

Restaura:

```text
inventory_items
```

por `item_id`.

### Pedidos

Restaura:

```text
supplier_orders
```

por `order_id`.

### Recepción de pedidos

Restaura el snapshot compuesto de `receive_order`:

```text
supplier_orders
supplier_order_items
inventory_items
```

Esto permite revertir:

- estado del pedido
- cantidades recibidas
- stock tienda/almacén interno

## Snapshots no soportados todavía

### Creación de artículo

Si el snapshot tiene:

```text
created_payload
```

se bloquea en v46, porque restaurar estado anterior implicaría borrar el registro creado. Eso se deja para rollback v2 con reglas específicas.

### Entidades desconocidas

Si no se reconoce la tabla/entidad, bloquea con mensaje claro.

## Checklist de prueba

1. Editar un artículo desde Inventario.
2. Ir a Seguridad / Logs.
3. Abrir detalle del log.
4. Pulsar Restaurar estado anterior.
5. Ver preview.
6. Escribir RESTAURAR.
7. Confirmar que el artículo vuelve al valor anterior.
8. Confirmar que aparece un nuevo log de Seguridad · Restaurar snapshot.

Prueba adicional:

1. Recibir parcialmente un pedido pequeño.
2. Verificar stock subido.
3. Restaurar desde snapshot del log `receive_order`.
4. Confirmar que stock y cantidades recibidas vuelven atrás.

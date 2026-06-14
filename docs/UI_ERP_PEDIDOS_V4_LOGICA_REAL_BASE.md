# UI ERP Pedidos v4 - Lógica real base

## Objetivo

Primer enganche real de Pedidos con Supabase.

## Cambios

- Nuevo servicio `futonhub.cloud.services.orders`.
- Lectura real de `supplier_orders`.
- Lectura real de `supplier_order_items`.
- Pedidos ya no dependen de mock data cuando hay sesión Supabase.
- Si Supabase no devuelve pedidos, la UI muestra estado vacío real.
- Añadido botón `Actualizar` en Pedidos.
- El detalle rápido muestra líneas reales asociadas al pedido.

## Tablas usadas

- `supplier_orders`
- `supplier_order_items`

## Regla

Este parche solo conecta lectura real. No calcula, no recibe, no cancela ni modifica stock todavía.

## Próximo paso

Conectar carga/guardado de borrador y cálculo real desde `CalculoCoste/coste_pedido.py`.

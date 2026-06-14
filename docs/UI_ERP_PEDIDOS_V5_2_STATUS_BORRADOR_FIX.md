# UI ERP Pedidos v5.2 - Fix estado Borrador

## Problema

Al guardar un pedido en estado `Borrador`, el registro se creaba correctamente en Supabase y volvía a cargar al reiniciar el ERP, pero la UI fallaba al pintar el detalle porque `Borrador` no existía en `STATUS_STYLES`.

Error observado:

```text
KeyError: 'Borrador'
```

## Corrección

- Añadido estilo visual para estados de pedidos:
  - Borrador
  - Pendiente archivo
  - Validación
  - Calculado
  - Guardado
  - Recibido parcial
  - Recibido completo
  - Exportado
  - Cancelado
- `_metric(...)` ahora tiene fallback seguro para estados no registrados.

## Resultado

El pedido en Borrador puede seleccionarse y mostrarse en detalle sin romper Tkinter.

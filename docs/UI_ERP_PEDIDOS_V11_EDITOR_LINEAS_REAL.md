# UI ERP Pedidos v11 - Editor real de líneas de cálculo

## Objetivo

Completar la quest de Pedidos para que una fila roja de la tabla de cálculo pueda corregirse desde el doble click y volver al flujo normal de cálculo.

## Cambios incluidos

### Doble click funcional

En la tabla de cálculo:

- doble click sobre una fila abre el editor de línea
- los campos obligatorios faltantes se marcan en rojo
- al aceptar se valida:
  - Descripción
  - Unidades
  - M3/Und.
  - Precio proveedor

### Actualización de la línea en memoria

Al aceptar:

- se actualiza la línea del pedido en la tabla
- se recalcula M3 total de la línea
- se limpia el estado de error de esa línea
- la tabla se redibuja sin volver a cargar todo el pedido
- el pedido queda listo para volver a pulsar **Calcular pedido**

### Persistencia hacia inventory_items

Si la referencia del item es numérica y coincide con `inventory_items.item_id`, se intenta actualizar en Supabase:

- `name`
- `cubic_meters`

Esto permite que el dato completado no vuelva a faltar en pedidos futuros.

No toca WooCommerce.

### Seguridad

La actualización de inventory_items usa el servicio existente:

```python
update_inventory_item_fields(...)
```

Ese servicio ya crea:

- snapshot
- audit log

Si la actualización de inventory_items falla por RLS o porque el item no existe, el pedido sigue actualizándose en memoria y muestra warning.

## Flujo recomendado de prueba

1. Abrir pedido en Validación con filas rojas.
2. Doble click sobre una fila roja.
3. Completar M3/Und. y Precio proveedor.
4. Aceptar.
5. Confirmar que la fila deja de estar roja.
6. Pulsar **Calcular pedido**.
7. Guardar pedido.
8. Cerrar ERP.
9. Reabrir y verificar que el pedido conserva los datos.

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

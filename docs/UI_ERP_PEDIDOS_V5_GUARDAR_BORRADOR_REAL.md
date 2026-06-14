# UI ERP Pedidos v5 - Guardar borrador real

## Objetivo

Permitir guardar un pedido en estado Borrador aunque todavía no se haya calculado.

Esto permite:

- crear el pedido desde la ventana Calcular nuevo pedido
- cerrar la ventana
- volver a abrir Pedidos
- ver el borrador cargado desde Supabase

## Cambios incluidos

### Servicio cloud

Nuevo helper en:

```text
GestorWoo/src/futonhub/cloud/services/orders.py
```

Función:

```python
create_supplier_order_draft(...)
```

Hace:

- inserta en `supplier_orders`
- status = `Borrador`
- total_items = 0
- total_cost = 0
- guarda `source_row.ui_order_name`
- guarda inputs actuales en `source_row.inputs`
- registra audit log
- intenta crear snapshot de creación

No toca:

- inventario
- WooCommerce
- líneas calculadas
- stock

### UI Pedidos

En la ventana **Calcular nuevo pedido**:

- `Guardar borrador` ya guarda en Supabase.
- `Guardar pedido` usa el mismo guardado básico si todavía no hay cálculo.
- si el nombre está vacío, pide poner un nombre.
- al guardar, refresca la lista de Pedidos.
- al cerrar/reabrir el ERP o entrar de nuevo en Pedidos, el borrador debe aparecer desde `supplier_orders`.

### Prueba recomendada

1. Abrir Pedidos.
2. Pulsar Calcular nuevo pedido en un proveedor.
3. Poner nombre, por ejemplo: `Pedido prueba borrador Heimei`.
4. Pulsar Guardar borrador.
5. Cerrar ventana.
6. Ver que aparece en la tabla de Pedidos.
7. Cerrar ERP.
8. Reabrir ERP.
9. Entrar en Pedidos.
10. Ver que sigue apareciendo desde Supabase.

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/cloud/services/orders.py GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

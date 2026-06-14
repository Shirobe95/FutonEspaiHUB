# UI ERP Pedidos v10 - Fix duplicado al modificar Validación

## Problema detectado

Al guardar un pedido calculado en estado `Validación` y reabrirlo con **Modificar**, las líneas se duplicaban.

Ejemplo:

```text
5 líneas reales
→ reabrir Modificar
→ 10 líneas visibles
```

El borrador normal no duplicaba, así que el problema estaba en el flujo de guardado/relectura de pedidos calculados o en Validación.

## Causa

Al guardar cálculo se reemplazan líneas en `supplier_order_items`.

Si Supabase/RLS no permite borrar físicamente las líneas antiguas, puede quedar una mezcla de:

- líneas antiguas del borrador
- líneas nuevas calculadas

Al volver a leer el pedido, la UI recibía ambas versiones y las mostraba juntas.

## Corrección

En `GestorWoo/src/futonhub/cloud/services/orders.py` se reforzó `list_cloud_supplier_order_items`:

- filtra líneas marcadas con `source_row.ui_deleted`
- deduplica por `source_row.ui_line_index`
- conserva la versión más reciente según `updated_at`
- evita que Modificar duplique visualmente líneas al reabrir pedidos en `Validación` o `Calculado`

## Impacto

No cambia la lógica de cálculo.
No toca inventario.
No toca WooCommerce.

Solo corrige la lectura de líneas del pedido para que la UI muestre una única versión activa por línea.

## Prueba recomendada

1. Abrir pedido borrador con 5 líneas.
2. Calcular pedido dejando alguna línea en error para que quede en `Validación`.
3. Guardar pedido.
4. Cerrar ERP.
5. Reabrir ERP.
6. Seleccionar el pedido.
7. Pulsar Modificar.
8. Confirmar que siguen saliendo 5 líneas, no 10.

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/cloud/services/orders.py GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

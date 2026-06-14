# UI ERP Pedidos v9 - Calcular pedido real en memoria

## Objetivo

Conectar el botón **Calcular pedido** para que use las líneas cargadas del Excel/PDF y los inputs del proveedor, calcule en memoria y pinte resultados reales en la tabla.

Esta fase no toca inventario ni WooCommerce.

## Flujo implementado

```text
Borrador con líneas
→ completar inputs de proveedor
→ Calcular pedido
→ calcular costes en memoria
→ actualizar tabla
→ Guardar pedido
→ persistir cálculo en Supabase
```

## Proveedores

### Heimei

Usa:

- Precio en Dólares
- Precio pagado en Euros
- Factura transporte
- Derechos aranceles
- Rentabilidad %, opcional

### Ekomat / Pascal / Cipta

Usan:

- Coste transporte + IVA
- Rentabilidad %, opcional

## Tabla

Al calcular:

- se rellenan coste final y columnas base disponibles
- filas calculadas quedan OK/Calculado
- filas con campos pendientes quedan en rojo
- se mantiene doble click para editar/completar datos

## Guardado

Si el pedido fue calculado y se pulsa **Guardar pedido**:

- actualiza `supplier_orders`
- actualiza/reemplaza `supplier_order_items`
- guarda `unit_cost`
- guarda `line_cost`
- guarda `source_row.calculation_inputs`
- status = `Calculado` si todo está bien
- status = `Validación` si hay líneas con error
- genera snapshot
- genera audit log

## Limitaciones de esta fase

No actualiza inventario.

No recibe pedido.

No toca WooCommerce.

No aplica todavía la fórmula completa legacy exacta de `coste_pedido.py` línea por línea, pero deja el puente funcional para cálculo en memoria y persistencia real. La siguiente fase puede sustituir la fórmula interna por el adaptador definitivo a la lógica legacy.

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/cloud/services/orders.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

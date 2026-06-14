# UI ERP v22 - Borrar pedido con UUID real y Configuración funcional

## Fix borrar pedido

Problema:

```text
invalid input syntax for type uuid: "Pedido Heimei"
```

Causa:

La UI estaba usando el nombre visual del pedido como si fuera `supplier_orders.order_id`.

Solución:

- Para mostrar seguimos usando el nombre visible.
- Para borrar/cancelar usamos el ID real desde `order.raw["order_id"]`.
- Si no existe ID real, no borra y muestra warning.
- El borrado sigue siendo cancelación lógica:
  - `status = cancelled`
  - `source_row.ui_cancelled = true`

## Configuración / Cálculos

Se activa lectura y guardado de constantes desde Supabase.

Servicio nuevo:

```text
GestorWoo/src/futonhub/cloud/services/business_constants.py
```

Constantes gestionadas:

```text
IMPORTE_DESCARGA_MT
PC_GASTOS_MANIPULACION
PC_GASTOS_FINANCIACION
IMPORTES_VARIOS
COSTE_TOTAL_DESCARGA_FUTONES_IVA
COSTE_DESCARGA_FUTONES_UNIDAD
IVA_RECARGO_EQUIVALENCIA
COSTE_DIARIO_ALMACENAJE_M3
PRICE_DROP_BLOCK_PERCENT
```

Botones funcionales:

- Recargar
- Guardar cálculos
- Cancelar

Guardar genera snapshot y audit log.

## SQL diagnóstico

Se añade:

```text
docs/SQL_DIAGNOSTICO_BUSINESS_CONSTANTS.sql
```

Si el esquema de `business_constants` usa nombres diferentes a `key/value/unit/description`, el SQL nos lo dirá.

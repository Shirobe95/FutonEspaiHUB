# UI ERP Pedidos v24 - Fórmulas legacy completas

## Objetivo

Verificar y corregir el cálculo de Pedidos para que use las fórmulas reales heredadas de `CalculoCoste/coste_pedido.py` y no una fórmula simplificada.

## Fórmulas conectadas

### Ekomat / Pascal / Cipta

Se replica la lógica de:

```python
calcular_coste_unitario_pedido(...)
```

Campos calculados:

- coste transporte por M3
- coste transporte producto
- coste transporte total referencia
- coste descarga producto IVA
- coste descarga total referencia
- IVA + recargo equivalencia
- precio con IVA
- coste descarga
- coste almacenaje IVA
- coste picking IVA
- precio coste final

### Heimei / Tatamis

Se replica la lógica de:

```python
calcular_coste_unitario_tatamis_pedido(...)
```

Campos calculados:

- tasa cambio
- importe transporte
- porcentaje transporte
- porcentaje descarga
- porcentaje varios
- manipulación
- financiación
- suma porcentajes
- precio artículo EUR
- gastos aplicables
- coste sin almacenaje
- coste almacenaje IVA
- coste picking IVA
- precio coste final

## Constantes

Ahora el cálculo lee las constantes desde Configuración/Supabase mediante:

```python
list_business_constants(...)
```

Si Supabase no responde, usa los defaults definidos en `DEFAULT_BUSINESS_CONSTANTS`.

Constantes usadas por cálculo:

- IMPORTE_DESCARGA_MT
- PC_GASTOS_MANIPULACION
- PC_GASTOS_FINANCIACION
- IMPORTES_VARIOS
- COSTE_TOTAL_DESCARGA_FUTONES_IVA
- IVA_RECARGO_EQUIVALENCIA
- COSTE_DIARIO_ALMACENAJE_M3

## Datos de inventario usados

Al cargar o calcular una línea, el ERP intenta enriquecerla desde `inventory_items`:

- primary_supplier_price / pascal_price
- cubic_meters
- rotation_c
- packages

Si falta `rotation_c` o `packages`, la línea queda en rojo porque el cálculo legacy los necesita para almacenaje y picking.

## Tabla

La tabla de cálculo deja de mostrar tantos `Pendiente` y rellena los campos que correspondan según proveedor.

## Seguridad

No toca WooCommerce.
No actualiza stock.
No recibe pedidos.
Solo calcula en memoria y luego guarda el pedido si el usuario pulsa Guardar.

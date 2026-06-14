# UI ERP Pedidos v27 - Exportación auditoría de cálculo

## Objetivo

Exportar pedidos calculados con toda la información necesaria para auditar fórmulas.

## Botones activados

- Exportar en la ventana de cálculo de pedido.
- Exportar en el detalle rápido de pedido.
- Exportar detalle en la vista completa del pedido.

## Formato

Exporta Excel `.xlsx` con hojas:

### Resumen

- Pedido
- ID real Supabase
- Proveedor
- Fecha
- Estado
- Inputs usados
- Total unidades
- Total coste cantidades

### Constantes usadas

Todas las constantes devueltas por `_current_business_constant_values()`:

- IMPORTE_DESCARGA_MT
- PC_GASTOS_MANIPULACION
- PC_GASTOS_FINANCIACION
- IMPORTES_VARIOS
- COSTE_TOTAL_DESCARGA_FUTONES_IVA
- COSTE_DESCARGA_FUTONES_UNIDAD
- IVA_RECARGO_EQUIVALENCIA
- COSTE_DIARIO_ALMACENAJE_M3
- etc.

### Líneas calculadas

Incluye:

- ID
- nombre
- cantidad
- M3 unidad
- M3 total línea
- precio proveedor
- precio artículo EUR
- tasa cambio
- % transporte
- % descarga
- % varios
- % manipulación
- % financiación
- transporte/factura
- aranceles/descarga
- IVA+RE
- coste descarga
- almacenaje IVA
- picking IVA
- rentabilidad
- Coste Final Artículo
- Coste Total Cantidad
- estado
- motivos/errores
- origen del precio proveedor
- match de precio

### Detalle fórmula

Vuelca `source_row`, `calculation_inputs`, `calculation_details` y snapshot de constantes por línea.

## Uso

Sirve para comparar ERP vs cálculo manual y verificar si:

- las constantes usadas son correctas
- el precio proveedor viene de la columna correcta
- la fórmula aplicada es la esperada
- se está mostrando coste unitario y coste total correctamente

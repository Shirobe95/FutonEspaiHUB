# UI ERP Pedidos v28 - Revisión de fórmulas de coste

## Resultado de revisión

La exportación del ERP coincide con una exportación previa de la Fábrica de Botones para el pedido H-2026-02. Eso valida que el cálculo implementado en el ERP reproduce el comportamiento histórico esperado.

## Archivo revisado

ERP:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
función: _calculate_supplier_order_in_memory
```

Legacy encontrado:

```text
CalculoCoste/coste_pedido.py
```

## Fórmulas cubiertas

### Proveedor general: Ekomat / Pascal / Cipta

La lógica ERP contempla:

```text
coste_transporte_m3 = coste_transporte_iva / m3_total_camion
descarga_por_producto = COSTE_TOTAL_DESCARGA_FUTONES_IVA / cantidad_total_productos
iva_re = precio_proveedor * IVA_RECARGO_EQUIVALENCIA_FACTOR
precio_con_iva = precio_proveedor + iva_re
coste_descarga = coste_transporte_producto + descarga_por_producto + precio_con_iva
coste_almacenaje_iva = COSTE_DIARIO_ALMACENAJE_M3 * m3_unidad * rotacion_c * 1.21
coste_picking_iva = ((bultos * 0.3) + 4.12) * 1.21
coste_final_articulo = coste_descarga + coste_almacenaje_iva + coste_picking_iva
```

### Heimei / Tatamis

La lógica ERP contempla:

```text
tasa_cambio = precio_dolares / precio_euros
importe_transporte = factura_transporte + derechos_aranceles
pc_transporte = importe_transporte / precio_euros * 100
pc_descarga = IMPORTE_DESCARGA_MT * 100 / precio_euros
pc_varios = IMPORTES_VARIOS / precio_euros * 100

pc_suma =
  pc_transporte
+ pc_descarga
+ PC_GASTOS_FINANCIACION
+ PC_GASTOS_MANIPULACION
+ pc_varios

precio_articulo_eur = precio_proveedor / tasa_cambio
gastos_aplicables = precio_articulo_eur * pc_suma / 100
coste_sin_almacenaje = precio_articulo_eur + gastos_aplicables
coste_almacenaje_iva = COSTE_DIARIO_ALMACENAJE_M3 * m3_unidad * rotacion_c * 1.21
coste_picking_iva = ((bultos * 0.3) + 4.12) * 1.21
coste_final_articulo = coste_sin_almacenaje + coste_almacenaje_iva + coste_picking_iva
```

## Validación automática por tokens

```json
{
  "general_coste_transporte_m3": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "general_descarga_por_producto": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "general_iva_re": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "general_almacenaje": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "general_picking": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "heimei_tasa_cambio": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "heimei_transporte_aranceles": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "heimei_porcentajes": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "heimei_precio_articulo_eur": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  },
  "heimei_coste_final": {
    "erp_has_all_tokens": true,
    "missing_in_erp": []
  }
}
```

## Conclusión

El ERP calcula de forma consistente con la Fábrica de Botones en el pedido probado.

Puntos ya fijados como criterio final:

```text
Coste Final Artículo = coste unitario real
Coste Total Cantidad = coste unitario real * cantidad pedida
```

La exportación de auditoría v27 queda como herramienta oficial para verificar futuros pedidos.

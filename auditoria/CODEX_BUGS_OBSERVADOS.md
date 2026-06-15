# FutonHUB - Bugs observados durante caracterizacion

Fecha: 2026-06-14

## BUG-CANDIDATO-001 - Rama CLI de diagnostico de precios proveedor

Archivo:

```text
GestorWoo/src/gestorwoo/cli.py
```

Hallazgo:

La rama del comando `cloud-supplier-prices-diagnostic` parece devolver una tupla/llamadas mezcladas en vez de ejecutar unicamente `run_cloud_supplier_prices_diagnostic()`.

Fragmento observado:

```text
if args.command == "cloud-supplier-prices-diagnostic":
    return run_cloud_supplier_prices_diagnostic, run_cloud_import_inventory_items_csv_preview, run_cloud_import_inventory_items_csv_execute, run_cloud_upsert_inventory_items_csv_preview, run_cloud_upsert_inventory_items_csv_execute()
```

Impacto posible:

- El comando puede no ejecutar el diagnostico esperado.
- La devolucion no parece compatible con el contrato habitual `int` de `main()`.
- No forma parte directa de la red de caracterizacion autorizada.

Estado:

- Documentado.
- No corregido.
- Requiere autorizacion separada si se decide arreglarlo.

## DEUDA-TECNICA-002 - Codificacion/Unicode en textos con acentos

Archivos observados:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/src/futonhub/ui/erp/dashboard.py
GestorWoo/src/futonhub/ui/erp/inventory_list.py
GestorWoo/src/futonhub/ui/erp/inventory_detail.py
```

Hallazgo:

Hay textos de UI y documentacion interna con acentos o simbolos representados como secuencias mojibake, por ejemplo `atenciÃ³n`, `validaciÃ³n`, `artÃ­culo`, `â‚¬` y `â€¦`.

Impacto posible:

- La UI puede mostrar acentos y simbolos corruptos en algunas vistas.
- Dificulta revisar cambios de texto sin mezclar refactorizacion con normalizacion de encoding.
- Puede afectar Dashboard y otras vistas heredadas del monolito.

Estado:

- Documentado como deuda tecnica independiente durante el Corte 004B.
- No corregido en este corte para no mezclar refactor estructural con cambios de textos/encoding.
- Requiere autorizacion separada y pruebas visuales si se decide normalizar.

## BUG-004B1-001 - Smoke fallido de historial completo para SKU 0201014

Fecha: 2026-06-15

Flujo manual observado:

- Publicacion Woo 128 -> 138 sobre SKU `0201014`.
- WooCommerce quedo actualizado y la web mostro el precio nuevo.
- Inventario siguio mostrando el precio anterior.
- `Historial completo` permanecio vacio.

Causa raiz tecnica:

- Inventario muestra `Precio Woo` desde `inventory_items.woo_price`.
- El primer cierre 004B.1 actualizaba Woo y el espejo `products`/`product_variations`, pero no cerraba obligatoriamente `inventory_items.woo_price`.
- `record_woo_price_inventory_history` podia devolver fallo sin convertirlo en error de operacion completa.

Estado:

- Corregido localmente mediante sincronizacion estricta de `inventory_items.woo_price` + `inventory_change_history`.
- Pendiente de smoke manual controlado con una unica repeticion sobre `0201014`.

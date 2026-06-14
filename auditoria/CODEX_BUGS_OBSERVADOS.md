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


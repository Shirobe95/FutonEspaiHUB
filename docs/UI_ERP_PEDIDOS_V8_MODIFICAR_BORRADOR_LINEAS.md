# UI ERP Pedidos v8 - Modificar borrador con líneas guardadas

## Objetivo

Permitir que un pedido guardado como borrador pueda volver a abrirse desde **Modificar** con sus líneas reales cargadas.

Flujo validable:

1. Cargar Excel/PDF.
2. Guardar borrador con líneas.
3. Cerrar ERP.
4. Reabrir ERP.
5. Entrar en Pedidos.
6. Seleccionar borrador.
7. Pulsar **Modificar**.
8. Ver la ventana de cálculo con:
   - nombre del pedido
   - proveedor heredado
   - archivo/tipo si se guardó
   - inputs guardados
   - líneas del pedido en la tabla
9. Guardar otra vez sin duplicar el pedido.

## Cambios incluidos

### UI

- `Modificar` ya abre la ventana de cálculo reutilizando datos del borrador real.
- La tabla de cálculo se rellena con las líneas guardadas en `supplier_order_items`.
- El chip del archivo muestra `order_file`.
- El indicador muestra `XLSX`, `PDF` o `BORRADOR` según `source_row.file_type`.
- Los inputs se precargan desde `source_row.inputs`.

### Servicio orders

Se agregó:

```python
update_supplier_order_draft(...)
```

Hace:

- actualiza la cabecera del pedido existente.
- borra/reemplaza las líneas del pedido.
- conserva estado `Borrador`.
- registra snapshot.
- registra audit log.
- no toca inventario.
- no toca WooCommerce.

## Importante

Guardar un borrador existente ya no crea un pedido duplicado: actualiza el pedido original usando `order_id` real de Supabase.

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/cloud/services/orders.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

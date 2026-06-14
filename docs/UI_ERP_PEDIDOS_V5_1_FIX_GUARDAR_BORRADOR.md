# UI ERP Pedidos v5.1 - Fix Guardar borrador

## Problema corregido

Al pulsar `Guardar borrador` o `Guardar pedido` en la ventana de cálculo, Tkinter lanzaba:

```text
AttributeError: '_tkinter.tkapp' object has no attribute '_save_supplier_order_draft_from_calc'
```

Causa:

- Los botones ya llamaban a `self._save_supplier_order_draft_from_calc(...)`.
- El método no estaba definido dentro de la clase del prototipo ERP.
- Al no encontrarlo en la clase, Tkinter terminaba buscando el atributo en el root interno.

## Solución

Se añadió el método:

```python
_save_supplier_order_draft_from_calc(...)
```

en:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

El método ahora:

- valida que exista sesión Supabase.
- lee los entries de la ventana de cálculo.
- exige `Nombre del pedido`.
- llama a `create_supplier_order_draft(...)`.
- guarda el borrador en `supplier_orders`.
- cierra la ventana.
- refresca la vista Pedidos.
- muestra confirmación.

## Verificación

```text
py_compile OK
pytest OK
11 passed
```

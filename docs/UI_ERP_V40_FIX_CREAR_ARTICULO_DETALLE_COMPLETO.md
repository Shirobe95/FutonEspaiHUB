# UI ERP v40 - Fix crear artículo y detalle completo de inventario

## Fix crear artículo

Problema:

```text
OperationSnapshot.__init__() got an unexpected keyword argument 'after_data'
```

Causa:

La firma real de `OperationSnapshot` en este proyecto no acepta `after_data`.

Solución:

El snapshot de creación ahora guarda el payload creado dentro de `before_data` como:

```python
{"created_payload": payload}
```

El audit log sí mantiene `after_data`.

## Detalle completo de inventario

Se amplía la ventana de detalle completo para editar los mismos campos base del formulario de nuevo artículo:

- Nombre
- Estado comercial
- Familia
- Subgrupo
- Medida
- Materiales
- M3 unidad
- Rotación C
- Bultos
- Precio proveedor
- Precio Pascal
- HECA reference
- Woo SKU
- Stock tienda
- Stock almacén
- Notas internas

## Guardado

El guardado sigue usando:

```text
update_inventory_item_fields()
```

Por tanto:

- actualiza Supabase
- genera snapshot
- genera audit log
- no toca WooCommerce

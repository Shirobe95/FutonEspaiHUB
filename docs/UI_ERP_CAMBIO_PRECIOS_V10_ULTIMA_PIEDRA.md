# UI ERP Cambio de Precios v10 - Última piedra

## Cambios incluidos

### Borrar propuesta completa

En el detalle de propuesta se añadió el botón:

- Borrar propuesta

Ubicación:

- al lado de Modificar

Comportamiento:

- si la propuesta es real, borra la propuesta completa desde Supabase.
- si la propuesta pertenece a un grupo visual por `source_row.ui_proposal_name`, elimina todos los registros asociados a ese nombre.
- si Supabase/RLS no permite borrado físico, se aplica borrado lógico usando `source_row.ui_deleted = true` y se oculta de la bandeja.
- si la propuesta está en estado `published` o `publishing`, no se permite borrar directamente.

### Logs y snapshots

El borrado de propuesta genera:

- snapshot previo por cada registro afectado
- audit log de borrado
- audit log de error si falla

### Propuestas vacías

Se corrigió el bug donde, al borrar el último item de una propuesta en edición, el listado se repoblaba automáticamente desde la propuesta original.

Ahora:

- una propuesta puede quedar vacía en edición.
- si se borra el último item, el listado queda vacío.
- no se reconstruye automáticamente con los items originales.
- se limpia también la fuente asociada del item borrado.

### Seguridad

No se cambió la lógica de WooCommerce.

Aceptar propuesta sigue siendo el flujo que aplica cambios protegidos según la lógica definida previamente.

## Archivos modificados

- `GestorWoo/src/futonhub/ui/erp/prototype.py`
- `GestorWoo/src/futonhub/cloud/services/price_proposals.py`

## Verificación

Ejecutado:

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/cloud/services/price_proposals.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

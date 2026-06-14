# UI ERP Cambio de Precios v11 - Fix borrado de propuesta

## Problema corregido

Al borrar una propuesta desde el botón **Borrar propuesta**, el popup y el flujo terminaban correctamente, pero la propuesta seguía apareciendo en la bandeja incluso tras pulsar **Actualizar**.

Causa principal:

- En Supabase/RLS, un `DELETE` puede ejecutarse sin lanzar excepción pero no eliminar realmente la fila.
- El servicio marcaba la operación como `hard_deleted=True` sin verificar que la fila hubiera desaparecido.
- La UI volvía a usar propuestas mock o la lista anterior cuando la recarga no devolvía propuestas visibles.

## Solución aplicada

### Servicio `delete_real_price_proposal_group`

Archivo:

```text
GestorWoo/src/futonhub/cloud/services/price_proposals.py
```

Cambios:

- Después de intentar `DELETE`, se verifica si los IDs siguen existiendo.
- Si siguen existiendo, se aplica borrado lógico:
  - `source_row.ui_deleted = true`
  - `source_row.ui_deleted_at`
  - `source_row.ui_deleted_by_email`
  - `source_row.ui_delete_operation_id`
  - `status = rejected`
- `list_real_price_proposals` excluye robustamente propuestas con `source_row.ui_deleted` incluso si viene como booleano, string o número.
- El audit log distingue entre:
  - `hard_deleted`
  - `soft_deleted`

### UI ERP

Archivo:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

Cambios:

- Al terminar el borrado, la propuesta se elimina inmediatamente de la lista local.
- Si la propuesta forma parte de un grupo por `ui_proposal_name`, se quitan todas las propuestas locales con ese nombre.
- Luego se fuerza recarga real desde Supabase.
- Cuando hay sesión cloud, una lista vacía es un estado real y ya no se rellena con propuestas mock.

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

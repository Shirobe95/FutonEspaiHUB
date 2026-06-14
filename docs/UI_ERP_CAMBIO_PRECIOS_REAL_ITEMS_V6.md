# UI-ERP Cambio de Precios v6 - Items reales y editor funcional

## Objetivo

Ajustar la edición de propuestas para trabajar con items reales de Supabase y simplificar la zona de subida de precio.

## Cambios de UI

### Pie de tabla de Items

La zona de subida queda en una sola línea:

```text
Subida % [entry pequeño]  Valor [entry pequeño]  Añadir
```

Regla:

- Se usa Subida % o Valor.
- No se pueden usar ambos a la vez.
- Si ambos tienen valor, se bloquea el añadido con aviso.

### Pie de tabla de Variaciones

Mismo patrón:

```text
Subida % [entry pequeño]  Valor [entry pequeño]  Añadir  Añadir Todas Variaciones
```

## Items reales

La tabla de items para añadir a propuestas carga datos reales desde Supabase usando:

- `list_cloud_inventory_items`
- `search_cloud_inventory_items`

No se usan items mock como fuente principal del editor.

## Barra de búsqueda

La búsqueda en edición de propuestas es funcional:

- Enter ejecuta búsqueda.
- Botón Buscar ejecuta búsqueda.
- Botón Recargar carga el listado general real.

## Variaciones reales

Al seleccionar un item real en la tabla de Items:

- se guarda como item seleccionado
- se recarga la sección de Variaciones
- las variaciones se leen desde `product_variations` usando `parent_woo_id`

Si no hay variaciones, la tabla queda vacía.

## Guardar cambios

Guardar cambios crea/actualiza propuestas reales en Supabase usando:

- `create_real_price_proposal`

Notas:

- WooCommerce no se toca al guardar.
- La publicación se mantiene para el flujo de aceptar propuesta.
- Se exige vínculo Woo válido para guardar propuesta real.
- Warnings de precio, como precio anterior 0, se aceptan desde UI porque el usuario ya está en flujo explícito de edición.

## Quitado

Se quita la acción visual:

- Importar aprobado

No se usará de momento.

## Verificación

```text
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado esperado:

```text
11 passed
```

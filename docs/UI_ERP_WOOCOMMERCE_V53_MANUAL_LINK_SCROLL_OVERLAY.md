# FutonHUB v53 - Woo Sync: enlace manual, filtros, scroll y overlay multi-monitor

## Objetivo

Convertir la v52 en una herramienta operativa de revisión Woo ↔ Supabase, manteniendo el modo seguro: WooCommerce no se escribe desde esta pantalla.

## Cambios principales

### 1. Enlace manual Woo ↔ Supabase

En la tarjeta de detalle Woo Sync aparece el botón **Enlazar con item Supabase** cuando `manual_link_candidate.available = true`.

Flujo implementado:

1. Buscar candidatos Supabase sin Woo por nombre, referencia, familia, subgrupo o material.
2. Mostrar tabla de candidatos sin `woo_id` y sin estado de enlace activo.
3. Generar preview obligatorio del enlace.
4. Bloquear si el Woo ya está enlazado con otro item.
5. Bloquear si el item Supabase elegido ya tiene Woo.
6. Confirmar escribiendo `ENLAZAR`.
7. Escribir solo en `inventory_items`.
8. Generar `operation_snapshot` y `audit_log`.

Campos escritos en Supabase:

- `woo_item_kind`
- `woo_id`
- `woo_parent_id`
- `woo_sku`
- `woo_name`
- `woo_type`
- `woo_price`
- `woo_categories`
- `woo_link_status = Enlazado manual`
- `woo_link_notes`

También rellena huecos seguros de clasificación si están vacíos: familia, subgrupo, medida, materiales, estado comercial e indicador pack.

### 2. Filtros de revisión

Añadido bloque de filtros en WooCommerce:

- Texto libre
- Revisión: todos, solo revisar, solo OK
- Estado: OK, Info, Warning, Error, Critical
- Caso: candidato enlace manual, sin enlace Supabase, safe to apply later, pack/composición, medida pendiente, material pendiente

La tabla muestra un contador `Mostrando X de Y líneas`.

### 3. Scroll en detalle derecho

El panel **Detalle Woo Sync** ahora usa canvas + scrollbar vertical. Esto permite llegar siempre a los botones inferiores:

- Editar clasificación preview
- Enlazar con item Supabase
- Ver JSON línea

### 4. Overlay de trabajo multi-monitor

El overlay de trabajo ya no se centra solo en la pantalla principal. Se posiciona respecto a la ventana ERP activa, usa `transient`, `grab_set`, `topmost`, `lift` y `focus_force` para evitar que se pierda al trabajar con varios monitores.

Aplica al proceso **Sincronizar + Autoclasificar** y a operaciones protegidas como aplicar enlace manual.

### 5. Texto de versión actualizado

La pantalla WooCommerce ya no muestra el aviso antiguo de v49/v50. Ahora indica que la v53 incluye preview seguro, filtros, edición de clasificación y enlace manual protegido.

## Validación

- `python -m compileall -q src`: OK
- `pytest -q`: 11 passed

## Seguridad

- No se escribe en WooCommerce.
- El enlace manual escribe solo en Supabase.
- Se bloquean duplicados por `woo_id`.
- Se bloquea enlazar sobre un item Supabase que ya tenga Woo.
- Se exige confirmación escrita `ENLAZAR`.
- Se genera snapshot antes de escribir.
- Se genera audit log después de escribir.

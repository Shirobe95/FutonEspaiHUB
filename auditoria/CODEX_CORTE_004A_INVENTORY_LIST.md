# FutonHUB - Corte 004A inventory list view

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract inventory list view
```

## Alcance

Primer subcorte de Inventario autorizado:

- construccion de la vista principal de Inventario;
- tabla/listado;
- filtros y busqueda;
- refresco del listado;
- seleccion de fila;
- navegacion basica hacia detalle existente;
- transformacion de refresco exclusiva del listado.

No se extrajeron:

- ventana de detalle;
- historial;
- edicion;
- movimientos de stock;
- creacion;
- exportacion;
- packs;
- conexion con Cambio de Precios.

No se tocaron servicios.
No se alteraron columnas, filtros, textos ni comportamiento.
`FutonHubErpPrototype` sigue siendo el adaptador principal.

## Simbolos movidos

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/inventory_list.py
```

Mixin temporal:

```text
ErpInventoryListMixin
```

Metodos movidos a `ErpInventoryListMixin`:

```text
_build_inventory
_refresh_inventory
_finish_inventory_refresh
```

Adaptador:

```text
class FutonHubErpPrototype(ErpInventoryListMixin, ErpDashboardMixin, ErpShellNavigationMixin, ErpSharedUiMixin, tk.Tk)
```

## Simbolos no movidos

Permanecen en `prototype.py` por estar fuera de alcance o por tener consumidores fuera del listado:

```text
_inventory_item_from_cloud_row
_inventory_query_is_code_like
_merge_inventory_rows
_accent_insensitive_inventory_search
_inventory_pack_contents_text
_inventory_item_type_text
_render_inventory_detail
_open_create_inventory_item_modal
_export_inventory_visible
_open_inventory_status_diagnostics_modal
```

Nota: `_inventory_item_from_cloud_row`, `_inventory_query_is_code_like`, `_merge_inventory_rows` y `_accent_insensitive_inventory_search` tambien son usados por Cambio de Precios. Se mantienen en el adaptador para no mezclar este subcorte con Precios.

## Compatibilidad de navegacion

La clave real historica sigue siendo:

```text
inventario
```

Para cumplir compatibilidad solicitada, se anadio alias en `ErpShellNavigationMixin._show_view`:

```text
inventory -> inventario
```

No se modifico `NAV_ITEMS`, labels, grupos ni orden.

## Dependencias sobre estado de instancia

`ErpInventoryListMixin` asume atributos ya inicializados por `FutonHubErpPrototype.__init__`:

```text
_cloud_session
_inventory_items
_inventory_error
_inventory_loading
_inventory_loaded_once
_inventory_query
_selected_inventory_item
_current_key
```

Tambien llama a metodos que siguen definidos en `FutonHubErpPrototype` u otros mixins:

```text
after
_show_view
_button
_card
_inventory_pack_contents_text
_inventory_item_type_text
_render_inventory_detail
_open_create_inventory_item_modal
_export_inventory_visible
_open_inventory_status_diagnostics_modal
_inventory_query_is_code_like
_merge_inventory_rows
_accent_insensitive_inventory_search
_inventory_item_from_cloud_row
```

## Servicios consumidos

El listado de Inventario consume los mismos servicios que antes, ahora desde `inventory_list.py`:

```text
futonhub.cloud.services.inventory.search_cloud_inventory_items
futonhub.cloud.services.inventory.list_cloud_inventory_items
```

No se modificaron firmas, queries, payloads, esquemas Supabase, RLS, RPC, tablas ni columnas.

## Tests de caracterizacion anadidos

Nuevo archivo:

```text
GestorWoo/tests/test_characterization_inventory_list.py
```

Comportamiento protegido:

- busqueda vacia sin `allow_empty` muestra error local y no consulta servicios;
- sin sesion cloud bloquea antes de consultar servicios;
- busqueda tipo codigo usa `search_cloud_inventory_items` sin merge contra inventario completo;
- busqueda textual mezcla resultados del servidor con busqueda local sin acentos;
- refresco vacio permitido carga ventana por defecto con `list_cloud_inventory_items(limit=150)`.

Test adicional en:

```text
GestorWoo/tests/test_characterization_entrypoint.py
```

Comportamiento protegido:

- `_show_view("inventory")` se normaliza a `_current_key == "inventario"`.

Los tests usan dobles/mocks y no escriben en WooCommerce ni Supabase.

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/inventory_list.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/src/futonhub/ui/erp/shell.py
GestorWoo/tests/test_characterization_inventory_list.py
GestorWoo/tests/test_characterization_entrypoint.py
auditoria/CODEX_CORTE_004A_INVENTORY_LIST.md
```

## Tests

Antes del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 43 tests in 0.081s
OK
```

Verificacion de imports/compilacion tras mover simbolos:

```powershell
python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/ui/erp/inventory_list.py GestorWoo/src/futonhub/ui/erp/shell.py GestorWoo/tests/test_characterization_inventory_list.py GestorWoo/tests/test_characterization_entrypoint.py
```

Resultado:

```text
OK
```

Despues del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 49 tests in 0.100s
OK
```

## Checklist manual

Pendiente de ejecutar manualmente por requerir UI/login:

- `Abrir ERP.bat`
- login
- abrir Inventario desde sidebar
- verificar columnas del listado:
  - ID
  - Tipo
  - Nombre
  - Contenido pack
  - Precio Woo
  - Stock
  - Estado
- busqueda vacia con recarga permitida
- busqueda por codigo/SKU
- busqueda textual
- busqueda sin resultados
- seleccion de fila
- apertura/render del detalle existente en lateral
- navegacion Inventario -> Dashboard -> Inventario
- cierre del ERP

Checklist tecnico automatizado:

- `prototype.py` compila.
- `inventory_list.py` compila.
- La suite completa sigue pasando.
- No se tocaron servicios.
- No se extrajeron detalle, historial, edicion, creacion, exportacion, packs ni Precios.

## Limitaciones

- No se ejecuta login real en tests automaticos.
- No se abre Tkinter durante la suite automatica.
- No se escribe en WooCommerce ni Supabase.

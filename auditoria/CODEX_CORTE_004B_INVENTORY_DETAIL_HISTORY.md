# FutonHUB - Corte 004B inventory detail and history

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract inventory detail and history
```

Commit real:

```text
6a1aa15b3e5ef5f984b49547b03919dac2433877
```

Hash padre:

```text
c953a3bd4736c2cccf73ce33f5f7b7604792b03f
```

Estado de push:

```text
Pendiente de push. Rama local ahead 3 respecto a origin/refactor/modularizacion-v1.
```

## Alcance

Segundo subcorte de Inventario autorizado:

- renderizado del detalle del item seleccionado;
- panel lateral de detalle;
- carga y presentacion del historial del item;
- helpers de detalle e historial;
- acciones de lectura ya existentes relacionadas con detalle/historial.

No se extrajeron:

- edicion de campos;
- movimientos o actualizacion de stock;
- creacion de items;
- exportacion;
- publicacion Woo;
- packs y componentes;
- conexion con Cambio de Precios.

No se tocaron servicios.
No se cambiaron textos, campos ni comportamiento.
El listado extraido en 004A queda intacto.
`FutonHubErpPrototype` sigue siendo el adaptador principal.

## Simbolos movidos

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/inventory_detail.py
```

Mixin temporal:

```text
ErpInventoryDetailMixin
```

Metodos movidos a `ErpInventoryDetailMixin`:

```text
_inventory_detail_rows
_render_inventory_detail
_load_inventory_history
_render_inventory_history
_render_inventory_history_error
_render_inventory_history_card
```

Adaptador:

```text
class FutonHubErpPrototype(ErpInventoryDetailMixin, ErpInventoryListMixin, ErpDashboardMixin, ErpShellNavigationMixin, ErpSharedUiMixin, tk.Tk)
```

## Simbolos no movidos

Permanecen en `prototype.py` por estar fuera del alcance 004B:

```text
_open_inventory_detail_window
_inventory_editable_initial_values
_collect_inventory_detail_changes
_editable_detail_row
_open_inventory_changes_review
_apply_inventory_detail_changes
_after_inventory_item_updated
_open_inventory_stock_preview_modal
_open_inventory_proposal_modal
```

La ventana completa de detalle mantiene su estructura actual, incluida la parte editable heredada. Solo delega la carga/presentacion del historial a `_load_inventory_history`.

Permanecen en `prototype.py` o en modulos previos por pertenecer a otros subcortes:

```text
_inventory_pack_contents_text
_inventory_pack_parent_code
_render_inventory_pack_inline_box
_open_inventory_pack_contents_popup
```

El panel lateral sigue llamando a helpers de packs existentes para conservar comportamiento, pero no se movio la logica de packs/componentes.

## Dependencias sobre estado de instancia

`ErpInventoryDetailMixin` asume atributos ya inicializados por `FutonHubErpPrototype.__init__`:

```text
_cloud_session
```

Tambien llama a metodos definidos en `FutonHubErpPrototype` u otros mixins:

```text
after
_card
_button
_detail_row
_clean_inventory_value
_inventory_pack_parent_code
_inventory_pack_contents_text
_render_inventory_pack_inline_box
_open_inventory_detail_window
_open_inventory_proposal_modal
```

## Servicios consumidos

La carga de historial consume el mismo servicio que antes, ahora desde `inventory_detail.py`:

```text
futonhub.cloud.services.inventory.fetch_inventory_item_history
```

No se modificaron firmas, queries, payloads, esquemas Supabase, RLS, RPC, tablas ni columnas.

## Tests de caracterizacion anadidos

Nuevo archivo:

```text
GestorWoo/tests/test_characterization_inventory_detail.py
```

Comportamiento protegido:

- las filas de detalle conservan campos del item seleccionado y posicion del contenido pack cuando ya viene calculado;
- el historial separa filas de precio y stock en tarjetas distintas;
- la carga de historial llama a `fetch_inventory_item_history(session, item_id, limit=120)`;
- sin sesion Supabase se renderizan tarjetas de error sin llamar al servicio.

Los tests usan dobles/mocks y no escriben en WooCommerce ni Supabase.

## Deuda tecnica registrada

Actualizado:

```text
auditoria/CODEX_BUGS_OBSERVADOS.md
```

Se documento `DEUDA-TECNICA-002 - Codificacion/Unicode en textos con acentos`.

No se corrigio durante este corte para no mezclar normalizacion de encoding con refactor estructural.

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/inventory_detail.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/tests/test_characterization_inventory_detail.py
auditoria/CODEX_CORTE_004B_INVENTORY_DETAIL_HISTORY.md
auditoria/CODEX_BUGS_OBSERVADOS.md
```

## Tests

Antes del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 49 tests in 0.091s
OK
```

Verificacion de imports/compilacion tras mover simbolos:

```powershell
python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/ui/erp/inventory_detail.py GestorWoo/src/futonhub/ui/erp/inventory_list.py GestorWoo/tests/test_characterization_inventory_detail.py
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
Ran 53 tests in 0.086s
OK
```

## Checklist manual

Pendiente de ejecutar manualmente por requerir UI/login:

- `Abrir ERP.bat`
- login
- abrir Inventario desde sidebar
- seleccionar fila del listado
- verificar panel lateral de detalle existente
- abrir detalle completo existente
- verificar historial de precios
- verificar historial de stock
- comprobar estado sin historial
- comprobar error de historial si no hay sesion/servicio disponible
- navegacion Inventario -> Dashboard -> Inventario
- cierre del ERP

Checklist tecnico automatizado:

- `prototype.py` compila.
- `inventory_detail.py` compila.
- La suite completa sigue pasando.
- No se tocaron servicios.
- No se extrajeron edicion, stock, creacion, exportacion, packs ni Precios.

## Limitaciones

- No se ejecuta login real en tests automaticos.
- No se abre Tkinter durante la suite automatica.
- No se escribe en WooCommerce ni Supabase.

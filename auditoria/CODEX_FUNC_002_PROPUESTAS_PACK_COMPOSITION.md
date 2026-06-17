# FutonHUB - FUNC-002 Propuestas de precios composicion legible de packs

Fecha: 2026-06-17

Estado:

```text
Implementado con FUNC-002D. Pendiente de smoke manual.
```

## Objetivo

Mostrar la composicion legible de packs Woo en la columna `Nombre` de la tabla de propuestas de precios.

Los articulos normales mantienen:

```text
ID | Nombre | Precio
```

FUNC-002B ajusta los packs Woo a composicion compacta en una sola linea:

```text
2x0201001xTatami 80 | 1x0728003xFuton Algodon
```

FUNC-002C corrige el enriquecimiento de nombres cuando los componentes llegan sin `component_name` y evita que la composicion se solape con los botones de las lineas anadidas.

FUNC-002D corrige la equivalencia de codigos numericos con y sin ceros iniciales durante busqueda, comparacion y cache.

## Alcance

Archivos funcionales:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/src/futonhub/cloud/services/inventory.py
```

Tests nuevos:

```text
GestorWoo/tests/test_characterization_price_proposal_pack_composition.py
```

## Comportamiento preservado

- Articulos normales mantienen su nombre actual.
- `ID`, `Precio`, SKU, Woo ID y logica de publicacion no cambian.
- No se hacen consultas por fila.
- No se modifican servicios, Supabase, RLS, RPCs ni esquema en FUNC-002B.
- FUNC-002C modifica solo el enriquecimiento de lectura de nombres en el servicio de inventario; no cambia escrituras, Supabase, RLS, RPCs ni esquema.
- No se modifica WooCommerce.

## Implementacion

Se reutilizan datos ya enriquecidos en `InventoryItem.raw`:

```text
hub_pack_components
hub_pack_components_text
hub_pack_components_multiline
```

La composicion de packs se agrupa por `component_item_code`, suma cantidades repetidas y ordena por codigo de componente.

Formato:

```text
{cantidad}x{ID}x{nombre}
{cantidad}x{ID}
```

Los componentes se separan con `|`.

Si no existe composicion enriquecida, se mantiene el nombre tecnico como fallback. Ese fallback queda considerado incidencia de datos pendiente de revisar manualmente.

FUNC-002B aumenta el ancho de la columna `Nombre` en la tabla de seleccion y el area disponible para el nombre de las lineas ya anadidas a la propuesta.

La busqueda de propuestas reutiliza la busqueda rankeada existente de Inventario para que buscar un componente, por ejemplo `0201001`, devuelva el articulo normal y los packs que contienen ese componente. No se anaden consultas por fila desde la UI.

FUNC-002C reemplaza la resolucion anterior de nombres por componente por resolucion en bloque contra `inventory_items`, usando cache por codigo y consultas batch sobre `heca_reference`, `hub_item_code`, `woo_sku` e `item_id`.

En lineas ya anadidas a propuesta, la tabla conserva el nombre compacto en `ProposalLine.name`, pero la UI lo presenta en varias lineas reemplazando ` | ` por saltos de linea. Los botones `Modificar` y `Borrar` quedan en una zona propia.

FUNC-002D anade normalizacion interna solo para codigos exclusivamente numericos:

```text
0201001 -> 201001
201001 -> 201001
0000 -> 0
```

Los codigos alfanumericos no se modifican. El codigo mostrado al usuario sigue siendo el codigo original del componente; la normalizacion se usa solo para buscar, comparar y cachear nombres.

## Simbolos tocados

```text
_price_inventory_item_is_pack
_price_pack_component_quantity
_price_format_pack_component_quantity
_price_pack_component_from_text
_price_pack_components_from_raw
_price_pack_components_display_name
_price_display_name_for_inventory_item
_prepare_price_edit_state
_price_proposal_from_cloud_row
_build_price_edit_workspace
_fill_component_names_from_inventory
_normalize_inventory_numeric_code
_price_line_display_name
_proposal_edit_line
```

## Tests

Cobertura automatizada:

- articulo normal sin cambios;
- pack con varios componentes;
- componentes repetidos sumados;
- orden estable por `component_item_code`;
- cantidades enteras y decimales sin decimales innecesarios;
- componente sin nombre;
- pack sin composicion usa fallback tecnico;
- composicion cacheada en texto se reutiliza sin consultas;
- `ProposalLine` conserva nombre, ID y precio;
- propuesta cloud reutiliza `source_row.ui_line_name`;
- composicion compacta cacheada se reutiliza;
- busqueda por componente devuelve articulo y packs que lo contienen;
- busqueda por ID de pack sigue funcionando;
- componentes sin `component_name` resuelven nombres en bloque desde inventario;
- no se usa la busqueda rankeada por componente durante la resolucion batch de nombres;
- linea anadida presenta la composicion en varias lineas para evitar solape con botones;
- `0201001` resuelve inventario guardado como `201001`;
- `201001` resuelve inventario guardado como `0201001`;
- busqueda por codigo normalizado devuelve articulo y packs con nombres;
- codigos alfanumericos permanecen intactos;
- `0000` se normaliza de forma segura.

Resultado automatizado:

```text
Ran 115 tests
OK
```

`py_compile`:

```text
OK
```

## Commit funcional

```text
785989cc234e7d1e95a24a1adb98f07d5c215026
```

## Commit funcional FUNC-002B

```text
5e6009928717e1cd8b3574327ffca2575a1e6a2f
```

## Commit funcional FUNC-002C

```text
05adb5e9fc1e90ccc22841125ef8af2610ab9487
```

## Commit funcional FUNC-002D

```text
6a5323bab50bf231bfcdb562315cc1390c3e1fc2
```

## Smoke manual

Pendiente.

Checklist propuesto:

- Abrir ERP con `Abrir ERP.bat`.
- Ir a propuestas de precios.
- Confirmar que un articulo normal mantiene `ID | Nombre | Precio`.
- Confirmar que un pack Woo muestra composicion compacta en `Nombre`.
- Confirmar formato `{cantidad}x{ID}x{nombre}` separado por `|`.
- Verificar agrupacion de componentes repetidos.
- Verificar orden por ID de componente.
- Buscar un componente, por ejemplo `0201001`, y confirmar que aparecen el articulo normal y los packs que lo contienen.
- Buscar tambien el mismo componente sin cero inicial, por ejemplo `201001`, y confirmar que aparecen articulo normal y packs.
- Confirmar que esos packs muestran nombres de componentes, no solo cantidad e ID.
- Buscar por ID de pack y confirmar que sigue apareciendo.
- Anadido un pack a la propuesta, confirmar que todos los componentes quedan visibles y los botones no pisan el texto.
- Verificar fallback tecnico solo si no hay composicion.
- Guardar una propuesta y recargarla.
- Confirmar que `ProposalLine.name` mantiene la composicion legible.
- Confirmar que no se publica nada en WooCommerce.
- Confirmar cierre sin traceback.

## Riesgos conocidos

- Packs sin composicion enriquecida seguiran mostrando el nombre tecnico.
- Si una fila solo trae `woo_sku` sin nombres, no se intenta resolver por consulta para cumplir la regla de no hacer consultas por fila.
- El orden usado es por `component_item_code`, no por orden comercial de Woo.
- El smoke manual sigue pendiente, por lo que FUNC-002 no esta cerrado.

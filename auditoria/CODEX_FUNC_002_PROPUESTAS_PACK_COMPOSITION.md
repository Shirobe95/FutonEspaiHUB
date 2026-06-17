# FutonHUB - FUNC-002 Propuestas de precios composicion legible de packs

Fecha: 2026-06-17

Estado:

```text
Implementado. Pendiente de smoke manual.
```

## Objetivo

Mostrar la composicion legible de packs Woo en la columna `Nombre` de la tabla de propuestas de precios.

Los articulos normales mantienen:

```text
ID | Nombre | Precio
```

Los packs Woo muestran una linea por componente:

```text
2 × 0201001 · Tatami
1 × 0728003 · Futon
```

## Alcance

Archivos funcionales:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

Tests nuevos:

```text
GestorWoo/tests/test_characterization_price_proposal_pack_composition.py
```

## Comportamiento preservado

- Articulos normales mantienen su nombre actual.
- `ID`, `Precio`, SKU, Woo ID y logica de publicacion no cambian.
- No se hacen consultas por fila.
- No se modifican servicios, Supabase, RLS, RPCs ni esquema.
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
{cantidad} × {ID} · {nombre}
{cantidad} × {ID}
```

Si no existe composicion enriquecida, se mantiene el nombre tecnico como fallback. Ese fallback queda considerado incidencia de datos pendiente de revisar manualmente.

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
- propuesta cloud reutiliza `source_row.ui_line_name`.

Resultado automatizado:

```text
Ran 107 tests
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

## Smoke manual

Pendiente.

Checklist propuesto:

- Abrir ERP con `Abrir ERP.bat`.
- Ir a propuestas de precios.
- Confirmar que un articulo normal mantiene `ID | Nombre | Precio`.
- Confirmar que un pack Woo muestra composicion multilinea en `Nombre`.
- Verificar agrupacion de componentes repetidos.
- Verificar orden por ID de componente.
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

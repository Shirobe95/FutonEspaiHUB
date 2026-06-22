# FutonHUB - FUNC-002 Propuestas de precios composicion legible de packs

Fecha: 2026-06-18

Estado:

```text
Implementado con FUNC-002I. Pendiente de smoke manual.
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

FUNC-002E corrige el corte temprano de la ruta rankeada: si buscar `201001` devuelve el articulo normal, igualmente se fusionan los packs cuyo componente esta guardado como `0201001`.

FUNC-002G usa los tokens reales de `woo_sku` como fuente estructurada cuando no existen relaciones, resuelve nombres en bloque y elimina el limite silencioso de los primeros 500 packs.

FUNC-002H simplifica la composicion visible, evita cortes/solapes y aplica un orden final comun a las busquedas equivalentes.

FUNC-002I recupera espacio vertical en Cambio de Precios y permite altura distinta por resultado sin aplicar un `rowheight` grande global.

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

Diagnostico FUNC-002E:

```text
Dato observado en smoke:
- inventory_items.item_id = 201001
- inventory_items.heca_reference = 201001 o equivalente sin cero
- inventory_item_components.component_item_code = 0201001

Punto de perdida:
- la vista rankeada respondia para 201001 con el articulo normal;
- el servicio retornaba en esa rama sin ejecutar la busqueda complementaria de packs por componente normalizado;
- la cache no registraba simultaneamente valor original y canonico para todas las claves.
```

Correccion FUNC-002E:

- `_inventory_code_cache_keys` registra clave original y clave canonica.
- La ruta rankeada tambien fusiona padres de componentes comparando con `_normalize_inventory_numeric_code`.
- El codigo mostrado sigue usando `component_item_code` original, por ejemplo `0201001`.

## FUNC-002G

Parte ya implementada antes del cierre:

- agrupacion y presentacion compacta de componentes en propuestas;
- normalizacion equivalente de codigos numericos con y sin ceros iniciales;
- resolucion batch/cache de nombres;
- mezcla de resultados rankeados con packs encontrados por componente.

Ajuste completado en FUNC-002G:

- `_components_from_woo_sku` convierte `0201001|0201001|0728003` en componentes estructurados;
- agrupa tokens repetidos conservando el codigo original mostrado;
- `hub_pack_components`, texto y multilinea se construyen desde `woo_sku` cuando no hay relaciones;
- los nombres se resuelven en una unica fase batch para todos los componentes del resultado;
- buscar `0201001` o `201001` devuelve los mismos packs;
- la seleccion y la propuesta reciben cantidad, ID y nombre.

Revision de rendimiento:

- no se creo migracion, vista, RPC ni cambio de esquema;
- la vista rankeada existente no garantiza ambas formas `0201001`/`201001`;
- la busqueda complementaria usa `inventory_items.woo_sku ILIKE '%<codigo normalizado>%'` para reducir candidatos en servidor;
- despues valida tokens completos normalizados en Python para evitar falsos positivos;
- pagina mediante `range` en bloques de 500 ordenados por `item_id`;
- no existe corte en los primeros 500 candidatos;
- `inventory_item_components` se conserva como fallback compatible, tambien paginado y resuelto en batch;
- no se hacen consultas por fila.

## FUNC-002H

Solucion visual:

- la composicion visible usa `{cantidad}x{nombre}`;
- los IDs de componentes permanecen en `hub_pack_components`;
- el ID del articulo o pack permanece en `ProposalLine.code`;
- articulos normales conservan su nombre;
- la tabla de resultados usa `Nombre` mas ancho, saltos de linea por componente y altura de fila calculada;
- los estilos de altura de items y variaciones son independientes;
- el detalle lateral muestra un componente por linea;
- `Modificar` y `Borrar` se renderizan debajo del texto, en una zona propia.

Ejemplo visible:

```text
2xTatami 80x200x5,5 | 1xFuton algodon 150x200x14
```

Comparacion de busqueda:

- se comparan conjuntos para `0201001` y `201001`, no el orden de origen;
- ambas formas devuelven los mismos IDs y la misma cantidad;
- se verifica ausencia de duplicados;
- la finalizacion aplica el mismo orden estable en ambas rutas;
- criterio: articulos normales primero; despues packs; dentro de cada grupo por `item_id` y codigo como desempate;
- no se modifico la logica de coincidencia de FUNC-002G.

La comparacion automatizada ejecuta el servicio con respuestas rankeadas asimetricas para ambas formas. La comparacion contra datos vivos requiere login interactivo y queda pendiente en el smoke manual.

## FUNC-002I

Limitacion confirmada:

- `ttk.Treeview` aplica `rowheight` al estilo completo;
- no soporta altura diferente por fila de forma nativa;
- aumentar la altura global hace que articulos simples consuman el mismo espacio que packs largos.

Solucion localizada:

- solo el selector `Items` deja de usar `Treeview`;
- usa `Canvas`, scrollbar y una fila `Frame` por resultado;
- conserva cabecera y columnas `ID | Nombre | Precio`;
- articulo normal usa una linea compacta;
- cada componente de un pack ocupa una linea;
- el viewport se limita a 210 px y activa scroll cuando el contenido crece;
- subida `%`, subida por valor y `Anadir` quedan fuera del viewport desplazable;
- `Variaciones` conserva el `Treeview` existente y permanece visible debajo;
- se mantienen seleccion, doble clic y boton `Anadir`;
- las tuplas originales de ID, nombre y precio son las usadas para anadir.

Shell:

- la busqueda global superior se oculta mediante `grid_remove()` solo para `precios`;
- se restaura automaticamente en Dashboard, Inventario y el resto de vistas;
- el estado de sesion sigue visible con padding vertical reducido en Cambio de Precios.

No se modifican calculos, propuestas, servicios, Supabase ni WooCommerce.

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
_inventory_code_cache_keys
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
- `0000` se normaliza de forma segura;
- si la busqueda rankeada por `201001` devuelve solo el articulo normal, tambien se fusionan packs con componente `0201001`;
- la evidencia de tests captura llamadas a `v_inventory_hub_search_ranked`, `inventory_item_components` e `inventory_items`.
- composicion visible usa cantidad y nombre sin ID;
- IDs internos de componentes y `ProposalLine.code` permanecen;
- filas largas se convierten en multilinea con altura suficiente;
- detalle lateral separa texto y botones;
- `0201001` y `201001` producen el mismo conjunto, cardinalidad y orden final;
- resultados sin duplicados;
- articulos normales sin cambios.
- barra global oculta solo en Cambio de Precios;
- barra global visible en Dashboard e Inventario;
- simples usan una linea y packs usan tantas lineas como componentes, con limite de seis para calculo;
- viewport de resultados limitado a 210 px con scroll;
- controles inferiores fuera del area desplazable;
- `Items` usa filas widget y `Variaciones` conserva `Treeview`;
- seleccion, doble clic y `Anadir` mantienen ID, nombre y precio.

Resultado automatizado:

```text
Tests del corte: Ran 39 tests
Suite completa: Ran 127 tests
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

## Commit funcional FUNC-002E

```text
5ba422f8c7c7ca1c79702f7c254be1c75b1639a6
```

## Commit funcional FUNC-002G

```text
5bc2503122147f16c201c6b56205d38b488314be
```

## Commit funcional FUNC-002H

```text
824b5b9faf0475b94c2b145076dfe90c9bce23d8
```

## Commit funcional FUNC-002I

```text
b510998b7032ac6de71ff9aff54073e94504e783
```

## Smoke manual

Pendiente.

Checklist propuesto:

- Abrir ERP con `Abrir ERP.bat`.
- Ir a propuestas de precios.
- Confirmar que la busqueda global superior desaparece en Cambio de Precios.
- Volver a Dashboard e Inventario y confirmar que la busqueda global reaparece.
- Confirmar que un articulo normal mantiene `ID | Nombre | Precio`.
- Confirmar que un pack Woo muestra composicion compacta en `Nombre`.
- Confirmar formato visible `{cantidad}x{nombre}` separado por `|`.
- Confirmar que la tabla muestra cada componente completo, con salto de linea cuando sea necesario.
- Confirmar que un articulo normal ocupa una fila compacta.
- Confirmar que un pack de dos componentes ocupa dos lineas.
- Cargar suficientes resultados y confirmar que aparece scroll sin empujar fuera subida %, valor, Anadir ni Variaciones.
- Confirmar seleccion, doble clic y boton Anadir.
- Verificar agrupacion de componentes repetidos.
- Verificar orden por ID de componente.
- Buscar un componente, por ejemplo `0201001`, y confirmar que aparecen el articulo normal y los packs que lo contienen.
- Buscar tambien el mismo componente sin cero inicial, por ejemplo `201001`, y confirmar que aparecen articulo normal y packs.
- Comparar ambos listados y confirmar mismos IDs, misma cantidad y mismo orden final.
- Confirmar que esos packs muestran cantidad y nombres completos, sin IDs dentro de la composicion visible.
- Buscar por ID de pack y confirmar que sigue apareciendo.
- Anadido un pack a la propuesta, confirmar que todos los componentes quedan visibles y los botones no pisan el texto.
- Confirmar en el detalle lateral un componente por linea y botones en una zona inferior independiente.
- Verificar fallback tecnico solo si no hay composicion.
- Guardar una propuesta y recargarla.
- Confirmar que `ProposalLine.name` mantiene la composicion legible.
- Confirmar que no se publica nada en WooCommerce.
- Confirmar cierre sin traceback.

## Riesgos conocidos

- Packs sin composicion enriquecida seguiran mostrando el nombre tecnico.
- La busqueda `ILIKE` puede devolver candidatos parciales, pero siempre se validan tokens completos antes de aceptar un pack.
- La paginacion puede requerir varias lecturas si existen mas de 500 candidatos parciales; no omite resultados por ese motivo.
- El orden interno de componentes sigue siendo por `component_item_code`, no por orden comercial de Woo.
- La igualdad contra datos vivos requiere login interactivo y sigue pendiente de smoke.
- El smoke manual sigue pendiente, por lo que FUNC-002I no esta cerrado.

## Cierre FUNC-002K.2 a FUNC-002K.8

Estado: aprobado por smoke manual mediante `Abrir ERP.bat` el 2026-06-22.

- recuperada la compatibilidad del listado con propuestas historicas y con estado vacio, sin traceback;
- el guardado valida completamente el modelo antes de la primera escritura;
- la propuesta usa una identidad canonica unica: `product|variation|pack:woo_id`;
- los packs se resuelven desde el snapshot autoritativo del buscador y, como compatibilidad, desde filas `inventory_items` de tipo `woo_pack` o `manual_pack`;
- variaciones y packs con el mismo `woo_id` permanecen como entidades distintas;
- la recarga conserva tipo, precios, codigo HUB y composicion del pack;
- el borrado opera exclusivamente sobre IDs reales y mantiene soft-delete con `ui_deleted=true` cuando el borrado fisico no es posible;
- se auditaron 200 filas ocultas: pertenecian a cuatro propuestas de prueba/smoke y no requieren restauracion;
- smoke final: propuesta mixta guardada y recargada con 109 lineas, 109 subidas, borrado correcto y sin errores.

Los diagnosticos temporales masivos se retiraron tras el cierre. Solo permanece
salida compacta para errores operativos o de integridad.

# FutonHUB - FUNC-003 Pedidos con rentabilidad individual

Fecha: 2026-06-18

Estado:

```text
Implementado y verificado automaticamente.
FUNC-003A implementado el 2026-06-19.
FUNC-003B implementado el 2026-06-19.
FUNC-003C implementado el 2026-06-19.
Pendiente de smoke manual mediante Abrir ERP.bat.
```

## Objetivo

Aplicar margen de venta en el calculo de pedidos y permitir una rentabilidad
individual por articulo sin alterar el coste real.

## Formula

```text
P.V.P. = Coste Final / (1 - Rentabilidad / 100)
```

Validacion:

```text
0 <= Rentabilidad < 100
```

El nombre visible sigue siendo `Rentabilidad`.

## Columnas

La tabla comienza por:

```text
ID | Nombre | Coste Final | Rentabilidad | P.V.P. | Ponderado | resto
```

El orden se aplica a proveedores generales y Heimei.

## Modelo de rentabilidad

Campos persistidos dentro de `supplier_order_items.source_row`:

```text
rentabilidad_individual_percent = porcentaje individual opcional
use_global_rentability = true | false
rentabilidad_percent = porcentaje efectivo del ultimo calculo
rentabilidad_global_percent = porcentaje global del ultimo calculo
rentabilidad_source = global | individual
```

Reglas:

- si `use_global_rentability` es `false` y existe
  `rentabilidad_individual_percent`, se usa el valor individual;
- en cualquier otro caso se usa la rentabilidad global;
- aplicar una nueva rentabilidad global no modifica los valores individuales;
- una linea puede volver explicitamente a `Usar rentabilidad global`;
- al volver a global se elimina `rentabilidad_individual_percent` de esa linea.

## Coste Final

`Coste Final` continua calculandose exclusivamente desde los costes reales:

- precio de proveedor;
- transporte;
- descarga;
- almacenaje;
- picking;
- restantes constantes del calculo existente.

El editor muestra el Coste Final calculado solo como referencia. No existe
campo editable, override ni persistencia manual de Coste Final.

Editar Rentabilidad conserva sin cambios:

```text
unit_cost
precio_coste_final
line_cost
final_cost
precio_ponderado_lote
```

Cuando cambian los costes generales:

1. se recalcula Coste Final;
2. se mantiene la rentabilidad individual o global efectiva;
3. se recalcula P.V.P. con el nuevo Coste Final.

## Ponderado

`precio_ponderado_lote` se calcula desde costes reales y stock. No usa
Rentabilidad ni campos `pvp_*`.

## Persistencia y recarga

No se modifica el esquema ni el servicio de pedidos.

La persistencia existente conserva `source_row` en
`supplier_order_items`. La cobertura automatizada ejecuta el servicio real
`update_supplier_order_calculation` contra un cliente Supabase en memoria,
serializa los datos como JSON, recarga el pedido mediante el flujo de lectura
ERP y vuelve a calcularlo.

La prueba confirma:

- persistencia de rentabilidad individual;
- persistencia del modo global/individual;
- proteccion del valor individual ante una nueva rentabilidad global;
- recálculo de Coste Final al cambiar costes;
- recálculo de P.V.P. desde el nuevo Coste Final.

## Compatibilidad historica

Pedidos antiguos sin `rentabilidad_individual_percent` ni
`use_global_rentability` usan la rentabilidad global.

Filas historicas sin `pvp_unit` calculan el valor de presentacion y exportacion
con la formula nueva, sin reescribir el pedido hasta que el usuario lo guarde.

## Exportacion

La exportacion mantiene separados:

```text
Coste Final Articulo | Rentabilidad % | P.V.P.
```

El fallback de P.V.P. usa la formula de margen de venta de FUNC-003.

## Recepcion e inventario

Recepcion, inventario, coste total y coste ponderado continúan usando:

```text
unit_cost
line_cost
total_cost
```

Nunca usan `pvp_unit` ni `pvp_line` para valorar inventario.

## Archivos funcionales

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/tests/test_characterization_supplier_order_costs.py
```

Commit de codigo:

```text
2cb5939 feat: add individual supplier order profitability
```

## Verificacion automatizada

Tests especificos:

```powershell
python -m unittest tests.test_characterization_supplier_order_costs -v
```

Resultado:

```text
Ran 20 tests
OK
```

Suite completa:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 138 tests
OK
```

Compilacion:

```powershell
python -m py_compile GestorWoo\src\futonhub\ui\erp\prototype.py GestorWoo\tests\test_characterization_supplier_order_costs.py
```

Resultado:

```text
OK
```

Integridad del diff:

```powershell
git diff --check
```

Resultado:

```text
OK
```

Finales de linea:

```text
prototype.py: index LF, working tree LF
test_characterization_supplier_order_costs.py: index LF, working tree LF
```

## FUNC-003A - Codigos numericos con ceros iniciales

Fecha: 2026-06-19

Estado:

```text
Implementado y verificado automaticamente.
Pendiente de smoke manual mediante Abrir ERP.bat.
```

### Incidencia

Una linea de pedido con codigo:

```text
0201001
```

no recuperaba el articulo guardado en Inventario como:

```text
item_id = 201001
```

El flujo terminaba solicitando manualmente RotC y precio de proveedor.

### Punto de perdida

`_fill_supplier_prices_for_order_items` llamaba a `get_supplier_price` una vez
por linea.

El resolver anterior:

- hacia intentos independientes con `limit(1)`;
- no consultaba `hub_item_code`;
- no construia un indice global de codigos;
- no podia detectar colisiones canonicas;
- mezclaba conversiones parciales de ceros iniciales dentro del propio
  resolver.

El editor tambien derivaba `inventory_items.item_id` directamente del codigo
visible del pedido. Esto era incorrecto cuando el match real procedia de
`heca_reference` o `hub_item_code`.

### Funcion canonica unica

Se creo:

```text
futonhub.core.codes.normalize_inventory_numeric_code
```

Reglas:

```text
0201001   -> 201001
000201001 -> 201001
0000      -> 0
AB0201001 -> AB0201001
```

La funcion solo se usa para busqueda, comparacion y cache. No modifica los
codigos almacenados, mostrados, guardados ni exportados.

Inventario reutiliza esta funcion mediante su alias privado compatible, por lo
que FUNC-002D y FUNC-003A no mantienen implementaciones duplicadas.

### Resolucion batch

`resolve_supplier_order_inventory_items` realiza una lectura paginada de
`inventory_items` para todo el pedido y construye dos indices:

```text
exact_index
canonical_index
```

Campos indexados:

```text
item_id
heca_reference
hub_item_code
woo_sku
```

Orden de resolucion:

1. coincidencia exacta;
2. si no existe y el codigo es numerico, coincidencia canonica;
3. si existen varias filas candidatas, se lanza
   `SupplierOrderCodeAmbiguityError`;
4. nunca se selecciona silenciosamente una coincidencia ambigua.

La lectura se pagina en bloques de 500. No se hacen consultas por linea.

### Datos enriquecidos

Tras resolver el articulo se recuperan desde la misma fila:

```text
name
rotation_c
packages
cubic_meters
primary_supplier_price o pascal_price
stock
weighted_average_cost
order_calculated_price
```

La linea conserva trazabilidad:

```text
inventory_matched_item_id
inventory_matched_by
inventory_order_original_code
supplier_price_item_id
```

El editor usa el `item_id` resuelto para cualquier actualizacion interna. Ya no
convierte el codigo visible del pedido directamente a `item_id`.

### Comportamiento preservado

- el codigo original sigue en `OrderItem.code`;
- guardado y recarga conservan los ceros iniciales;
- exportacion conserva el codigo original;
- no se crean articulos;
- no se modifican codigos de Inventario;
- no se modifica Supabase, esquema, RLS ni RPCs;
- no se modifica WooCommerce;
- Coste Final, Ponderado, Rentabilidad y P.V.P. conservan sus formulas;
- solo cambia que ahora reciben correctamente los datos reales del articulo.

### Compatibilidad historica

Pedidos historicos guardados con codigos como `0201001` se vuelven a enriquecer
al abrir o recalcular. El articulo se resuelve canonicamente y el codigo
historico permanece intacto.

### Archivos FUNC-003A

```text
GestorWoo/src/futonhub/core/codes.py
GestorWoo/src/futonhub/cloud/services/inventory.py
GestorWoo/src/futonhub/cloud/services/supplier_prices.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/tests/test_characterization_supplier_order_costs.py
```

Commit de codigo:

```text
8499a6b fix: normalize supplier order item codes
```

### Verificacion FUNC-003A

Tests especificos:

```text
Ran 27 tests
OK
```

Suite completa:

```text
Ran 145 tests
OK
```

`py_compile`:

```text
OK
```

`git diff --check`:

```text
OK
```

## FUNC-003B - Packs excluidos del calculo de pedidos

Fecha: 2026-06-19

Estado:

```text
Implementado y verificado automaticamente.
Pendiente de smoke manual mediante Abrir ERP.bat.
```

### Incidencia

Para el codigo de pedido `0724001`, el indice canonico de FUNC-003A podia
contener simultaneamente:

- el articulo normal;
- un pack Woo equivalente o relacionado.

El resolver lanzaba `SupplierOrderCodeAmbiguityError`, aunque los packs no son
articulos elegibles para calcular pedidos.

### Regla aplicada

Los packs quedan excluidos de:

- resolucion del articulo del pedido;
- nombre, RotC, M3, bultos y precio de proveedor;
- Coste Final y Ponderado;
- Rentabilidad y P.V.P.;
- recepcion e inventario asociados a la linea del pedido.

La ambiguedad se mantiene si dos o mas articulos normales elegibles coinciden
exacta o canonicamente.

### Detector central

Se centralizo:

```text
futonhub.core.codes.is_inventory_pack_row
```

Una fila se considera pack si cumple cualquiera de estas señales persistidas:

```text
item_record_type o hub_search_record_type = woo_pack | manual_pack
is_pack = true | 1 | yes | si
item_id, hub_search_code o hub_item_code empieza por WOO-PACK-
woo_sku contiene |
existen metadatos hub_pack_components*
```

El detector revisa tambien `source_row` cuando la señal no esta proyectada en
la raiz.

El panel de Inventario reutiliza el mismo detector en lugar de mantener su
implementacion local. No se cambia el formato, busqueda ni composicion visible
de packs en Cambio de Precios.

### Punto exacto del filtro

El filtro se ejecuta en:

```text
resolve_supplier_order_inventory_items
```

inmediatamente despues de leer cada fila y antes de construir:

```text
exact_index
canonical_index
exact_field
canonical_field
```

Por tanto, un pack nunca llega a ser candidato exacto ni canonico de un
pedido.

La consulta batch incluye:

```text
item_record_type
is_pack
```

ademas de las señales ya disponibles `item_id`, `hub_item_code`, `woo_sku` y
`source_row`.

### Comportamiento validado

- articulo normal y pack equivalente seleccionan el normal;
- varios packs equivalentes no generan ambiguedad;
- dos articulos normales equivalentes siguen bloqueando;
- coincidencia exacta normal mantiene prioridad;
- packs por prefijo `WOO-PACK-` quedan excluidos;
- packs por SKU compuesto quedan excluidos;
- codigos alfanumericos normales siguen resolviendo;
- `0201001` sigue resolviendo `201001`;
- RotC y precio se recuperan del articulo normal;
- codigo visible, guardado y exportado permanece intacto;
- la resolucion sigue siendo batch, sin consultas por linea.

### Archivos FUNC-003B

```text
GestorWoo/src/futonhub/core/codes.py
GestorWoo/src/futonhub/cloud/services/supplier_prices.py
GestorWoo/src/futonhub/ui/erp/cloud_inventory.py
GestorWoo/tests/test_characterization_supplier_order_costs.py
```

Commit de codigo:

```text
72b9158 fix: exclude packs from supplier order resolution
```

### Verificacion FUNC-003B

Tests especificos:

```text
Ran 32 tests
OK
```

Suite completa:

```text
Ran 150 tests
OK
```

`py_compile`:

```text
OK
```

`git diff --check`:

```text
OK
```

## FUNC-003C - Solo articulos base operativos

Fecha: 2026-06-19

Estado:

```text
Implementado y verificado automaticamente.
Pendiente de smoke manual mediante Abrir ERP.bat.
```

### Investigacion de candidatos reales

La consulta anonima de solo lectura a Supabase fue aceptada, pero RLS devolvio
cero filas. La identidad se verifico contra los fixtures operativos usados para
cargar esos mismos registros.

Articulo base, fixture:

```text
docs/imports/E-2026-03_inventory_items_from_upload.csv
```

Campos:

```text
item_id = 724004
hub_item_code = vacio/no definido en el fixture
hub_search_code = no aplica
item_record_type = vacio; el buscador lo trata como simple
hub_search_record_type = no aplica
is_pack = false/no definido
heca_reference = 0724004
woo_sku = vacio
name = Futon de Algodon 150 x 200 x 14 cm.
cubic_meters = 0.35
rotation_c = 0.051780822
packages = 1
primary_supplier_price = 80.64
pascal_price = 77.5
source_row/metadatos = import E-2026-03; sin relacion de pack
```

Fila sintetica Woo, fixture:

```text
010_woo_cierre_lote_D_FINAL.sql
```

Campos:

```text
item_id = 930000012860
hub_item_code = WOO-ITEM-12860
hub_search_code = no persistido
item_record_type = woo_item
hub_search_record_type = no aplica
is_pack = false
heca_reference = no establecido por este lote
woo_sku = 0724003-724004
woo_item_kind = variation
woo_id = 12860
woo_parent_id = 12856
name = 14,5 cm, 140x200x14,5 cm, Crudo
source_row.source = woo_cierre_lote_D
source_row.original_sku = 0724003-724004
componentes/relaciones = variacion Woo sintetica; no articulo de compra
```

El SQL actualiza filas existentes sin limpiar `heca_reference`. Por tanto, una
fila sintetica preexistente puede conservar un alias numerico relacionado y
entrar en los indices de pedidos.

### Causa de la falsa ambiguedad

FUNC-003B solo respondia a la pregunta:

```text
¿es un pack?
```

La fila `930000012860` supera ese filtro porque:

- `is_pack=false`;
- `item_record_type=woo_item`, no `woo_pack`;
- `hub_item_code` empieza por `WOO-ITEM-`, no por `WOO-PACK-`;
- `woo_sku` usa `-`, no `|`.

El resolver trataba todos los campos indexados con la misma autoridad. Una
coincidencia auxiliar por alias podia competir con el `item_id` canonico del
articulo base.

### Criterio definitivo de elegibilidad

Se creo el predicado central:

```text
is_supplier_order_eligible_inventory_row
```

Una fila es elegible solo si:

- no es pack segun `is_inventory_pack_row`;
- tiene `item_id` numerico;
- `item_record_type` es vacio o `simple`;
- no usa prefijos sinteticos `WOO-ITEM-`, `WOO-VAR-`, `WOO-ALIAS-`,
  `SEARCH-` o `ALIAS-`;
- no tiene `base_item_code`;
- no contiene tipos de relacion `alias`, `component`, `pack_component`,
  `search` o `search_alias`;
- no contiene metadatos de componente, padre, relacionado o proyeccion.

Se excluyen explicitamente:

```text
woo_item
woo_product
woo_variation
woo_pack
manual_pack
alias
component
pack_alias
pack_component
search_alias
search_projection
synthetic
```

El predicado reutiliza `is_inventory_pack_row`, pero no considera elegible una
fila simplemente por no ser pack.

### Prioridad semantica

Los indices se construyen solo con filas elegibles. La resolucion recorre estos
niveles:

```text
1. item_id exacto
2. item_id canonico
3. hub_item_code exacto
4. hub_item_code canonico
5. heca_reference exacto
6. heca_reference canonico
7. woo_sku exacto autorizado
8. woo_sku canonico autorizado
```

La primera prioridad con candidatos decide el resultado.

`SupplierOrderCodeAmbiguityError` solo se lanza cuando hay dos o mas articulos
base elegibles dentro del mismo nivel. Una coincidencia auxiliar de menor
prioridad no compite con un `item_id` unico.

### Comportamiento validado

- `0724004` resuelve `item_id=724004`;
- la variacion `930000012860` queda excluida;
- `0724001` resuelve `724001`;
- `0201001` resuelve `201001`;
- articulos base ganan frente a packs, componentes, aliases y sinteticos;
- `item_id` exacto gana frente a `hub_item_code`;
- `item_id` canonico gana frente a aliases canonicos;
- dos articulos base en igual prioridad siguen bloqueando;
- nombre, RotC, M3, bultos y precio proceden del articulo base;
- recepcion e inventario conservan `inventory_matched_item_id` del articulo
  base;
- codigo visible, guardado y exportado permanece intacto;
- la lectura sigue siendo batch, sin consultas por linea;
- Cambio de Precios y composicion de packs no cambian.

### Archivos FUNC-003C

```text
GestorWoo/src/futonhub/core/codes.py
GestorWoo/src/futonhub/cloud/services/supplier_prices.py
GestorWoo/tests/test_characterization_supplier_order_costs.py
```

Commit de codigo:

```text
008cac9 fix: resolve orders only to base inventory items
```

### Verificacion FUNC-003C

Tests especificos:

```text
Ran 36 tests
OK
```

Suite completa:

```text
Ran 154 tests
OK
```

`py_compile`:

```text
OK
```

`git diff --check`:

```text
OK
```

## Smoke manual pendiente

Ejecutar mediante:

```text
Abrir ERP.bat
```

Validar:

1. abrir un pedido historico sin campos de FUNC-003;
2. calcular con rentabilidad global;
3. asignar rentabilidad individual a una linea;
4. guardar, cerrar y recargar;
5. confirmar valor individual y modo individual;
6. cambiar rentabilidad global y confirmar que la individual no cambia;
7. cambiar transporte u otro coste general y recalcular;
8. confirmar nuevo Coste Final y nuevo P.V.P.;
9. volver una linea a `Usar rentabilidad global`;
10. exportar y revisar columnas/formula;
11. comprobar que recepcion e inventario usan costes reales;
12. cerrar sin traceback.

Smoke adicional FUNC-003A:

1. cargar un pedido real con codigo `0201001`;
2. confirmar match con `inventory_items.item_id=201001`;
3. confirmar nombre, RotC y precio de proveedor automaticos;
4. calcular Coste Final, Ponderado, Rentabilidad y P.V.P.;
5. confirmar que UI y exportacion siguen mostrando `0201001`;
6. guardar, cerrar y recargar el pedido;
7. confirmar que el codigo original y el match siguen intactos;
8. probar un codigo alfanumerico;
9. si existen candidatos canonicos ambiguos, confirmar bloqueo visible;
10. cerrar sin traceback.

Smoke adicional FUNC-003B:

1. cargar el pedido real con codigo `0724001`;
2. confirmar que el articulo normal se selecciona aunque exista un pack Woo;
3. confirmar nombre, RotC y precio de proveedor automaticos;
4. calcular Coste Final, Ponderado, Rentabilidad y P.V.P.;
5. confirmar que UI y exportacion conservan `0724001`;
6. comprobar que el pack no participa en recepcion ni inventario del pedido;
7. comprobar que dos articulos normales equivalentes siguen mostrando error de
   ambiguedad;
8. cerrar sin traceback.

Smoke adicional FUNC-003C:

1. cargar el pedido real con codigo `0724004`;
2. confirmar seleccion de `inventory_items.item_id=724004`;
3. confirmar que la fila `WOO-ITEM-12860` no participa;
4. comprobar nombre, RotC, M3, bultos y precio de proveedor del articulo base;
5. calcular Coste Final, Ponderado, Rentabilidad y P.V.P.;
6. guardar, cerrar y recargar;
7. confirmar `0724004` intacto en UI y exportacion;
8. comprobar recepcion e inventario contra `724004`;
9. confirmar que dos articulos base en la misma prioridad siguen bloqueando;
10. cerrar sin traceback.

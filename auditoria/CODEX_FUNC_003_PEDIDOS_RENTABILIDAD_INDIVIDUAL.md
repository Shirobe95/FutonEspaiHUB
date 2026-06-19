# FutonHUB - FUNC-003 Pedidos con rentabilidad individual

Fecha: 2026-06-18

Estado:

```text
Implementado y verificado automaticamente.
FUNC-003A implementado el 2026-06-19.
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

# FutonHUB - FUNC-001 Pedidos coste, rentabilidad y P.V.P.

Fecha: 2026-06-16

Estado:

```text
Cerrado y aprobado.
```

## Objetivo

Separar en Pedidos el coste real del articulo, el porcentaje de rentabilidad y el precio de venta resultante.

## Regla funcional

```text
P.V.P. = Coste Final del Articulo x (1 + Rentabilidad / 100)
```

La formula anterior:

```text
coste / (1 - rentabilidad / 100)
```

queda eliminada del flujo de calculo de pedidos ERP.

## Alcance

Archivo funcional modificado:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

Tests nuevos:

```text
GestorWoo/tests/test_characterization_supplier_order_costs.py
```

No se modifico:

```text
GestorWoo/src/futonhub/cloud/services/orders.py
```

## Campos separados

```text
unit_cost = coste real unitario
line_cost = unit_cost x cantidad
total_cost = suma de costes reales
rentabilidad_percent = porcentaje aplicado
pvp_unit = unit_cost x (1 + rentabilidad_percent / 100)
pvp_line = pvp_unit x cantidad
```

## UI y exportacion

La tabla de calculo y la exportacion muestran:

```text
Coste Final Articulo | Rentabilidad % | P.V.P.
```

## Persistencia

El payload guardado mantiene `unit_cost`, `line_cost` y `total_cost` como coste real.

`pvp_unit` y `pvp_line` se conservan dentro de `source_row`.

## Recepcion e inventario

Recepcion, inventario y coste ponderado siguen usando `unit_cost`, `line_cost` y `total_cost`.

No se usan campos `pvp_*` para valorar inventario.

## Compatibilidad historica

Filas antiguas sin `pvp_unit` mantienen fallback visual/exportable:

```text
pvp_unit = unit_cost x (1 + rentabilidad_percent / 100)
```

No se reescriben pedidos historicos.

## Tests

Cobertura añadida:

- proveedor general: coste 100, rentabilidad 30, P.V.P. 130;
- rentabilidad 0;
- proveedor Heimei;
- formula antigua no usada;
- `unit_cost` y `line_cost` mantienen coste real;
- `pvp_unit` y `pvp_line` quedan separados;
- `total_cost` usa coste real;
- tabla muestra coste, rentabilidad y P.V.P. en orden;
- exportacion contiene las tres columnas;
- recepcion no usa `pvp_*`;
- compatibilidad con filas antiguas sin `pvp_unit`.

Resultado automatizado:

```text
Ran 98 tests
OK
```

`py_compile`:

```text
OK
```

## Smoke manual

Resultado: aprobado por el usuario el 2026-06-16.

Evidencia manual:

- Verificado en UI y exportaciones reales de Ekomat y Heimei.
- Orden correcto: `Coste Final Articulo | Rentabilidad % | P.V.P.`
- P.V.P. calculado con `coste x (1 + rentabilidad / 100)`.
- Coste real separado del P.V.P.
- Coste total por cantidad basado en coste real.
- Proveedor general y Heimei correctos.
- Exportacion correcta.
- Recepcion e inventario no usan `pvp_*`.
- Cierre sin incidencias funcionales.

Estado final:

- FUNC-001 cerrado y aprobado.
- No se modificaron esquemas, RLS, RPCs ni pedidos historicos.
- No se inicio FUNC-002 ni 004D2.

## Riesgos conocidos

- Pedidos ya guardados antes de FUNC-001 pueden tener `unit_cost` historicamente inflado por la formula anterior.
- Este cambio no reescribe historicos ni migra datos existentes.
- El fallback para filas antiguas es visual/exportable y no reescribe historicos.

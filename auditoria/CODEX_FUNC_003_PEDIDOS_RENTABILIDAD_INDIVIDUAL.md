# FutonHUB - FUNC-003 Pedidos con rentabilidad individual

Fecha: 2026-06-18

Estado:

```text
Implementado y verificado automaticamente.
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

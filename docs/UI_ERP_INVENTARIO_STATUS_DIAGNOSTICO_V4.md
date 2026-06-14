# UI ERP Inventario - Diagnóstico de estados v4

## Objetivo

Corregir el problema visual donde todos los items aparecían como `Error` por una interpretación demasiado estricta de `woo_link_status`.

El precio operativo del inventario es siempre `woo_price`, porque es el precio de venta en WooCommerce.

## Cambios aplicados

Archivo principal:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

### 1. Diagnóstico de valores reales recibidos

Se añadió el botón:

```text
Diagnosticar estados
```

En Inventario.

Este botón abre un popup que analiza los items cargados desde Supabase y muestra:

- conteo por estado UI
- valores reales recibidos en `woo_link_status`
- campos vacíos recibidos desde Supabase
- motivos que generan los estados actuales

Esto permite comparar:

```text
valor real recibido desde Supabase
→ interpretación del semáforo UI
→ motivo que genera Warning / Error / Critical
```

### 2. Semáforo menos bruto y más fiel al dato real

Antes, cualquier `woo_link_status` distinto de:

```text
linked
ok
matched
```

caía como `Error`.

Eso podía marcar todo el inventario como error si Supabase usaba otros valores válidos como:

```text
synced
linked_by_sku
matched_by_sku
variation
parent
simple
variable
manual
```

Ahora los estados Woo desconocidos pasan a `Warning` con motivo visible, no a `Error` automático.

### 3. Motivos del estado en detalle completo

En el detalle completo del item, debajo de `Estado`, se añadió:

```text
Motivos del estado
```

Ahí se lista por qué el item tiene ese estado.

Ejemplos:

```text
Precio Woo igual a 0. Es el precio de venta de la web.
Familia sin definir.
M3 / cubic_meters pendiente.
Estado vínculo Woo desconocido para el semáforo: synced_custom.
```

Si el item está bien:

```text
Sin incidencias detectadas con las reglas actuales.
```

## Reglas actuales de estado

### Critical

- Falta `item_id`.
- `woo_price` es 0.

### Error

- `woo_link_status` indica rotura explícita:
  - broken
  - error
  - missing
  - not_found
  - orphan
  - woo_missing
  - invalid

### Warning

- `woo_price` pendiente o no numérico.
- `woo_link_status` incompleto, pendiente o desconocido.
- falta `family`.
- falta `cubic_meters`.

### Info

- falta `materials`.
- falta `subgroup`.
- falta `size`.
- falta `woo_id`.

### OK

- no se detectan incidencias con las reglas actuales.

## Verificación

```text
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

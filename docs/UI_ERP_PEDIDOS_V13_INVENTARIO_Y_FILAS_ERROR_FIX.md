# UI ERP Pedidos v13 - Inventario y filas rojas

## Correcciones

### Inventario

Se corrige un `NameError: index is not defined` al abrir Inventario después de refrescar desde Supabase.

Causa:
- el diccionario interno `item_by_iid` guardaba `(index, item)`, pero en esa rama del bucle no existía `index`.

Solución:
- se usa índice seguro generado durante la inserción de filas.

### Pedidos

Se refuerza el detector de errores en líneas de cálculo.

Ahora una fila se marca roja si falta:

- ID / referencia
- nombre
- cantidad
- M3
- precio proveedor/base
- coste bloqueado
- estado Error / Critical / Bloqueado
- motivos internos del parser en `source_row`

Esto permite que al cargar un Excel/PDF con datos raros la tabla marque directamente la fila problemática sin tener que abrir línea por línea.

## Archivos

- `GestorWoo/src/futonhub/ui/erp/prototype.py`

# UI ERP · Cambio de Precios v8 · búsqueda, scroll y selección estable

## Objetivo

Corrección de usabilidad en Cambio de Precios / Propuestas tras probar la edición real de propuestas.

## Cambios aplicados

### Barra de búsqueda de propuestas

- Se añadió el método `_set_proposal_search` que faltaba y podía provocar error Tkinter al usar la barra de búsqueda.
- La búsqueda filtra propuestas cargadas por nombre, fecha, estado, conteos e items incluidos.

### Búsquedas sin sensibilidad a acentos

Se reforzó la búsqueda normalizada para que `Algodon` encuentre `Algodón`.

Aplicado en:

- Inventario.
- Items disponibles en edición de propuestas.
- Propuestas guardadas.

La búsqueda contra Supabase ahora combina:

1. Resultado directo del servicio.
2. Filtro local normalizado sobre items listados desde Supabase.

Así se evita depender solo de `ilike`, que puede no resolver acentos según configuración de la base.

### Tabla de items estable

Antes, al seleccionar un item en la tabla del editor de propuestas, la vista completa se reconstruía y la tabla volvía al inicio.

Ahora:

- La selección solo actualiza el item seleccionado.
- La tabla de items no se refresca completa.
- La zona de variaciones se reconstruye de forma localizada.

### Auto-scroll al modificar item de propuesta

Al pulsar `Modificar` en un item incluido en la propuesta:

- Se prepara búsqueda por el código del item.
- Se recarga la tabla de items con ese filtro.
- El item queda seleccionado y visible mediante `tree.see`.

### Scroll en listado de items de propuesta

El panel derecho de items incluidos en la propuesta ahora tiene scroll interno.

Esto evita que una propuesta larga o con muchas variaciones deje items inaccesibles.

### Anchos de tabla ajustados

En las tablas de items y variaciones:

- `ID` queda más estrecho.
- `Precio` queda más estrecho.
- `Nombre` gana espacio y se estira.

Objetivo: mejorar lectura de nombres largos sin desperdiciar espacio en campos cortos.

## Verificación

- `python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py`
- `PYTHONPATH=GestorWoo/src python -m pytest -q`

Resultado: 11 tests OK.

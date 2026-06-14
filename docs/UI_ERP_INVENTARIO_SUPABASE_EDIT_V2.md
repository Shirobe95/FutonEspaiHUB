# UI ERP Inventario - Supabase real + edicion controlada v2

## Objetivo

Inventario deja de depender de items de prueba en el ERP y pasa a trabajar contra `inventory_items` en Supabase.

## Cambios principales

- La vista de Inventario carga inventario real desde Supabase al entrar al modulo.
- El boton `Buscar / recargar` permite listar inventario completo o buscar por texto/ID.
- Se elimina el fallback visual a `INVENTORY_ITEMS` mock en la tabla principal.
- Si no hay datos reales visibles, la tabla muestra estado vacio.
- La exportacion de inventario exporta solamente los items visibles en la tabla en ese momento.

## Mapeo de campos

- `woo_price` -> Precio Woo.
- `materials` -> Materiales.
- `subgroup` -> Subgrupo.
- `size` -> Medidas.
- `cubic_meters` -> M3.
- `store_stock` -> Stock tienda.
- `warehouse_stock` -> Stock almacen.
- `store_stock + warehouse_stock` -> Stock total.

## Detalle completo editable

En el detalle completo se pueden editar campos internos del HUB:

- Nombre.
- Familia.
- Subgrupo.
- Materiales.
- Medidas.
- M3.
- Stock tienda.
- Stock almacen.
- Notas internas.

No se toca WooCommerce desde esta ventana.

## Flujo de cierre con cambios

Si el usuario pulsa `Cerrar` y hay cambios pendientes:

1. Se abre un popup de revision.
2. Se muestran campo, valor anterior y valor nuevo.
3. El usuario puede:
   - descartar cambios;
   - cancelar y volver;
   - aceptar y guardar.

Si acepta:

1. Se genera preview interno.
2. Se crea `operation_snapshot`.
3. Se actualiza `inventory_items` en Supabase.
4. Se escribe `audit_log`.
5. Se recarga Inventario.

## Historiales

Las graficas de historial ya no son un dibujo fijo.

- Leen historial real desde `inventory_change_history` si existe.
- Leen tambien `audit_logs` asociados al item.
- Si no hay historial real, muestran estado vacio.
- No se fabrican puntos.

## Validaciones

- Campos numericos (`cubic_meters`, `store_stock`, `warehouse_stock`) se normalizan.
- Stock tienda y stock almacen no pueden ser negativos.
- Solo se pueden editar campos permitidos desde Inventario.
- WooCommerce no se modifica desde Inventario.

## Pruebas realizadas

- `python -m py_compile GestorWoo/src/futonhub/cloud/services/inventory.py GestorWoo/src/futonhub/ui/erp/prototype.py`
- `PYTHONPATH=src python -m pytest -q`

Resultado: 11 tests OK.

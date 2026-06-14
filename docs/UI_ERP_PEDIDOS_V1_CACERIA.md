# UI ERP Pedidos v1 - Comienza la cacería

## Objetivo

Primer parche real sobre el módulo Pedidos del prototipo ERP. Se ajusta la UI al contrato funcional definido antes de conectar la lógica completa de cálculo/persistencia.

## Cambios aplicados

### Proveedores dentro de Pedidos

- Se eliminan los estados visuales de proveedor.
- Las tarjetas de proveedor quedan como accesos rápidos para calcular pedidos.
- Proveedores no se añade como módulo independiente del menú.

### Detalle rápido de pedido

Se añade botón:

- Modificar

Botones actuales:

- Modificar
- Recibido
- Borrar pedido
- Exportar

Modificar abre el flujo de cálculo usando el proveedor del pedido seleccionado.

### Calcular nuevo pedido

- La ventana sigue heredando el proveedor desde Pedidos.
- No hay selector interno de proveedor.
- Se elimina el botón Recalcular.
- El botón Calcular pedido sirve para calcular o recalcular.
- Se añade botón Guardar borrador.
- Se elimina el resumen inferior de resultados por ahora.
- Rentabilidad queda como campo simple: Rentabilidad %.

### Inputs por proveedor

Heimei muestra:

- Nombre del pedido
- Fecha
- Rentabilidad %
- Precio en Dólares
- Precio pagado en Euros
- Factura transporte
- Derechos aranceles

Ekomat / Pascal / Cipta muestran:

- Nombre del pedido
- Fecha
- Rentabilidad %
- Coste transporte + IVA

### Tabla de cálculo

Se implementa una estructura de tabla tipo ERP con columnas fijas:

- Izquierda fija: ID, Producto / Medida
- Centro desplazable horizontalmente: columnas de cálculo
- Derecha fija: Coste Final

La tabla mantiene scroll vertical sincronizado y scroll horizontal solo en la zona central.

### Detalle completo del pedido

Los indicadores económicos se adaptan según proveedor.

Heimei muestra:

- Precio en Euros
- Precio en Dólares
- Factura transporte
- Derechos aranceles
- Coste total pedido

Ekomat / Pascal / Cipta muestran:

- Coste transporte + IVA
- Coste total pedido

### Recepción de pedido

Se añade selector de destino:

- Almacén
- Tienda

Por defecto: Almacén.

### Borrado de pedido

El texto queda preparado para cancelación lógica futura:

- status=cancelled
- log
- sin borrado físico directo

## Pendiente para fase de conexión real

- Conectar carga real de Excel/PDF.
- Conectar cálculo real desde `CalculoCoste/coste_pedido.py`.
- Guardar borrador en `supplier_orders` / `supplier_order_items`.
- Guardar pedido calculado.
- Listar pedidos reales desde Supabase.
- Recibir total/parcial actualizando inventario con snapshot/log.
- Exportación completa con todos los elementos calculados.

## Verificación

Ejecutado:

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

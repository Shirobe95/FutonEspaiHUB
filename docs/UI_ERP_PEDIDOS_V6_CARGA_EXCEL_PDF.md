# UI ERP Pedidos v6 - Carga Excel/PDF real

## Objetivo

Permitir cargar pedidos desde archivo dentro de la ventana **Calcular nuevo pedido**.

Soporte v6:

- Excel: `.xlsx`, `.xlsm`
- PDF: solo Heimei/Hemei, usando extracción de texto con `pypdf` si está instalado

## Cambios principales

### Cargar pedido

El botón **Cargar pedido** abre selector de archivos:

- Excel
- PDF

Al cargar:

- se lee el archivo
- se detectan columnas por cabecera
- se extraen líneas con unidades mayores que 0
- se pinta la tabla de cálculo con esas líneas
- el indicador muestra nombre de archivo y tipo: `XLSX` o `PDF`

### Excel por proveedor

La lectura adapta columnas según proveedor:

- Heimei: `REF`, descripción, medida, unidades, color, precio, M3
- Cipta: código/item code, modelo, medida, color, cantidad, M3
- Ekomat/Pascal: referencia, composición, medida, color, unidades, M3

### PDF

PDF queda preparado para Heimei porque es el único flujo que estaba contemplado en la lógica antigua.

Si se carga PDF con otro proveedor:

```text
La lectura de PDF está preparada de momento para pedidos Heimei. Para este proveedor usa Excel.
```

Si falta `pypdf`, muestra:

```text
Para leer pedidos PDF instala pypdf: pip install pypdf.
```

### Guardar borrador con líneas

Si se cargó archivo y se pulsa **Guardar borrador**:

- se guarda la cabecera en `supplier_orders`
- se guardan las líneas en `supplier_order_items`
- el pedido queda como `Borrador`
- los costes quedan pendientes
- no toca inventario
- no toca WooCommerce

### Tabla

La tabla sigue siendo normal, con scroll horizontal y vertical.

Las líneas con datos pendientes quedan en Warning o rojo según las reglas ya definidas.

## Archivos modificados

- `GestorWoo/src/futonhub/ui/erp/prototype.py`
- `GestorWoo/src/futonhub/cloud/services/orders.py`

## Verificación

```powershell
PYTHONPATH=GestorWoo/src python -m py_compile GestorWoo/src/futonhub/cloud/services/orders.py GestorWoo/src/futonhub/ui/erp/prototype.py
PYTHONPATH=GestorWoo/src python -m pytest -q
```

Resultado:

```text
11 passed
```

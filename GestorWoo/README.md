# GestorWoo

Herramienta Python para cargar productos existentes desde WooCommerce y preparar una gestion centralizada de precios, packs y reglas comerciales.

## Objetivo inicial

WooCommerce ya contiene los productos y packs. El primer paso del sistema es sincronizar ese catalogo a una base local para poder analizar relaciones, recalcular precios y publicar cambios de forma controlada.

## Configuracion

Copia `.env.example` a `.env` y rellena los datos:

```env
WOOCOMMERCE_URL=https://tu-tienda.com
WOOCOMMERCE_CONSUMER_KEY=ck_xxx
WOOCOMMERCE_CONSUMER_SECRET=cs_xxx
GESTORWOO_DB_PATH=data/gestorwoo.sqlite3
```

Las claves se crean en WooCommerce desde:

`WooCommerce > Ajustes > Avanzado > REST API`

Permisos recomendados para empezar: lectura.

## Instalacion

Para empezar no hace falta instalar el paquete. Puedes ejecutar el lanzador local:

```powershell
python gestorwoo.py list-products
```

Si quieres instalarlo como comando del entorno:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e . --no-build-isolation
```

## Uso

Sincronizar productos:

```powershell
python gestorwoo.py sync-products
```

Este comando carga categorias, productos padre y tambien las variaciones de productos variables.

Ver resumen local:

```powershell
python gestorwoo.py list-products
```

Abrir la interfaz:

```powershell
python gestorwoo.py ui
```

Abrir el panel central Futon Espai:

```powershell
python gestorwoo.py hub
```

El panel central permite abrir GestorWoo y CalculoCoste desde una sola ventana,
manteniendo ambos proyectos separados para poder probarlos y evolucionarlos por
su cuenta.

Abrir la gestion de inventario:

```powershell
python gestorwoo.py inventory
```

La gestion de inventario importa inicialmente el Excel de CalculoCoste a SQLite
y muestra encabezados legibles para los precios de proveedor: **Precio CIPTA /
Ekomat** y **Precio Pascal**.

Desde Inventario se puede usar **Ver historico** para consultar los cambios de
precios, medidas y datos de coste del articulo seleccionado.

Abrir backups y restauracion:

```powershell
python gestorwoo.py backup
```

La herramienta crea copias fechadas de `data/gestorwoo.sqlite3` en
`data/backups/` y, antes de restaurar una copia, genera un backup previo de
seguridad.

CalculoCoste carga primero los articulos desde la tabla local `inventory_items`.
El Excel queda solo como respaldo temporal si no se encuentra la base local.

Desde la interfaz se puede usar **Crear pack** para vincular un producto pack de WooCommerce con sus componentes locales. La ventana calcula la suma fija de componentes y permite guardar una de tres reglas:

- dejar el precio actual del pack
- aplicar una rebaja porcentual
- aplicar una rebaja por monto fijo

Tambien se puede usar **Cambiar precio** para simular cambios de precio en local. Esta funcion muestra el precio actual, el nuevo precio, variaciones relacionadas y packs manuales afectados. El cambio se guarda como propuesta local; no escribe nada en WooCommerce.

## Siguiente paso

Despues de cargar todos los productos y variaciones, el siguiente modulo debe permitir relacionar manualmente cada pack con sus componentes. En este WooCommerce los packs no estan emparentados con los productos sueltos, asi que GestorWoo mantendra su propia relacion local pack -> componentes.

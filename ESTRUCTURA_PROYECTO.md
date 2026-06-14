# Organizacion del proyecto

## Decision tomada

Se consolido el proyecto en dos carpetas oficiales:

```txt
CalculoCoste/
GestorWoo/
```

La carpeta antigua `FutonEspaiHub/` contenia copias de ambas herramientas y generaba riesgo de editar una version equivocada. Por eso se elimina del paquete organizado.

## Que queda como version oficial

### `GestorWoo/`

Contiene el Hub, la gestion de WooCommerce, inventario, backups y publicacion controlada.

Puntos de entrada:

```txt
GestorWoo/gestorwoo.py
GestorWoo/FutonEspaiLauncher.py
```

`gestorwoo.py` se usa en desarrollo.

`FutonEspaiLauncher.py` se usa para crear el `.exe`, evitando el conflicto de nombre entre `gestorwoo.py` y el paquete `src/gestorwoo`.

### `CalculoCoste/`

Contiene:

```txt
coste_1.py       Calculo individual y gestor de constantes
coste_pedido.py  Calculo masivo de pedidos desde Excel
data.xlsx        Respaldo historico
```

## Flujo de datos

```txt
WooCommerce
   ↓ sincronizacion
GestorWoo/data/gestorwoo.sqlite3
   ↓ inventario local, precios, M3, rotacion, bultos
CalculoCoste/coste_1.py y coste_pedido.py
```

El calculo de pedido puede actualizar el M3 local de los productos usando el Excel cargado. No actualiza WooCommerce.

## Carpetas eliminadas del paquete

```txt
FutonEspaiHub/
.git/
.vs/
__pycache__/
build/
dist/
*.exe antiguos
```

## Archivos sensibles

```txt
GestorWoo/.env
GestorWoo/data/gestorwoo.sqlite3
GestorWoo/data/backups/
```

Estos archivos son utiles para el negocio, pero no deben subirse a GitHub publico ni compartirse fuera del equipo.

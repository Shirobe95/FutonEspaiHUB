# Parche estructura local estable

Este parche parte del último FutonHUB funcional local, antes de multi-máquina y Turso.

## Cambios aplicados

### 1. Limpieza de rutas

Las rutas críticas ahora se resuelven desde la estructura real del proyecto, no desde la carpeta desde donde se ejecute el comando.

Archivos tocados:

- `GestorWoo/src/gestorwoo/pathing.py`
- `GestorWoo/src/gestorwoo/config.py`

La base definida como ruta relativa en `.env`:

```txt
GESTORWOO_DB_PATH=data/gestorwoo.sqlite3
```

se interpreta siempre como:

```txt
FutonEspaiHUB/GestorWoo/data/gestorwoo.sqlite3
```

### 2. SQLite duplicada aislada

La base vacía que estaba en:

```txt
FutonEspaiHUB/data/gestorwoo.sqlite3
```

se movió a:

```txt
FutonEspaiHUB/_aislado_sqlite_duplicada_vacia/gestorwoo.sqlite3
```

La base activa sigue siendo:

```txt
FutonEspaiHUB/GestorWoo/data/gestorwoo.sqlite3
```

### 3. Diagnóstico del sistema

Se añadió un módulo nuevo:

```txt
GestorWoo/src/gestorwoo/diagnostics.py
```

Permite comprobar:

- raíz real del proyecto,
- carpeta `GestorWoo`,
- carpeta `CalculoCoste`,
- `.env` usado,
- base SQLite activa,
- conteos de tablas clave,
- duplicados de SQLite.

### 4. Botón visible en el HUB

El panel principal ahora muestra:

- una línea con la base activa,
- botón `Diagnóstico del sistema` en la parte inferior.

### 5. Comando de consola nuevo

Desde cualquier carpeta se puede ejecutar:

```powershell
python "RUTA\FutonEspaiHUB\GestorWoo\gestorwoo.py" diagnostic
```

O desde `GestorWoo`:

```powershell
python gestorwoo.py diagnostic
```

## Validación realizada

Se validó que el diagnóstico detecta como base activa:

```txt
FutonEspaiHUB/GestorWoo/data/gestorwoo.sqlite3
```

Conteos detectados:

```txt
products: 115
product_variations: 614
inventory_items: 235
supplier_prices: 397
heca_stock: 2930
price_change_proposals: 7
inventory_change_history: 8
```

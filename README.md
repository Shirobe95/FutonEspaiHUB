# Futon Espai - Herramientas internas

Proyecto consolidado para gestionar herramientas internas de Futon Espai.

## Estructura oficial

```txt
FutonEspai_Organizado/
├─ CalculoCoste/                 # Calculadora individual, pedido y constantes
│  ├─ coste_1.py                 # Calculo de coste individual + gestor de constantes
│  ├─ coste_pedido.py            # Calculo masivo desde Excel de pedido
│  ├─ constantes_negocio.json    # Se crea al cambiar constantes
│  └─ data.xlsx                  # Respaldo historico si no hay SQLite
├─ GestorWoo/                    # Aplicacion principal
│  ├─ gestorwoo.py               # Lanzador en desarrollo
│  ├─ FutonEspaiLauncher.py      # Lanzador usado para crear el .exe
│  ├─ src/gestorwoo/             # Codigo fuente del paquete
│  ├─ data/gestorwoo.sqlite3     # Base local: productos, inventario, precios, M3
│  ├─ .env                       # Credenciales locales WooCommerce
│  └─ .env.example               # Plantilla de configuracion
├─ abrir_futon_espai.py          # Arranque desde la raiz
├─ ABRIR_FUTON_ESPAI.bat         # Arranque rapido en Windows
├─ crear_exe_windows.bat         # Genera FutonEspai.exe
└─ crear_exe_windows_debug.bat   # Genera FutonEspai_DEBUG.exe
```

## Como abrir en desarrollo

Opcion recomendada desde Windows:

```bat
ABRIR_FUTON_ESPAI.bat
```

O por consola:

```bat
cd GestorWoo
python gestorwoo.py hub
```

## Como crear el exe

Ejecuta desde la carpeta raiz:

```bat
crear_exe_windows.bat
```

El ejecutable se creara en:

```txt
GestorWoo/FutonEspai.exe
```

No muevas el `.exe` solo. Debe quedarse dentro de `GestorWoo`, con `CalculoCoste` al lado.

## Notas importantes

- `FutonEspaiHub/` fue eliminado porque duplicaba `GestorWoo/` y `CalculoCoste/`.
- `.git`, `.vs`, `__pycache__`, `build`, `dist` y ejecutables antiguos fueron eliminados.
- La base local vive en `GestorWoo/data/gestorwoo.sqlite3`.
- Las constantes editables se guardan en `CalculoCoste/constantes_negocio.json`.
- No subas `.env` ni `.sqlite3` a repositorios publicos.

## Gestor WooCommerce - Organización visual v1

La pantalla de Gestor WooCommerce incluye una capa local de clasificación que no modifica WooCommerce.

Campos añadidos:
- Familia interna
- Subgrupo
- Medida
- Materiales
- Estado comercial
- Es pack
- Revisado
- Notas

Flujo recomendado:
1. Actualizar desde WooCommerce si hace falta.
2. Pulsar **Clasificar automaticamente** para crear una primera propuesta local.
3. Filtrar por familia, subgrupo, estado comercial, revisión o pack.
4. Doble click sobre un artículo, o botón **Editar clasificación**, para corregirlo manualmente.
5. Marcar como revisado cuando esté validado.
6. Exportar catálogo clasificado para revisión externa si hace falta.

Esta fase solo organiza el catálogo localmente. No publica precios ni cambia productos reales en WooCommerce.

## WooCommerce - organización visual y propuestas seguras

La pantalla de WooCommerce trabaja primero sobre datos locales. La clasificación interna permite filtrar por familia, subgrupo, medida, materiales, estado comercial, packs y revisión manual.

En la ventana de publicación de cambios se añadió un paso de seguridad:

- Exportar propuestas pendientes a Excel.
- Enviar/revisar el Excel antes de publicar.
- Cargar el Excel revisado de vuelta al HUB.
- Bloquear publicación si una propuesta tiene precio 0 o negativo.
- Marcar con aviso las bajadas de precio para revisión.

La publicación hacia WooCommerce sigue siendo una acción manual y explícita.

## WooCommerce - separación por función

La tarjeta **Gestor WooCommerce** del HUB se divide en dos accesos:

- **Gestión de Inventario**: organización visual del catálogo, autoclasificación, edición de familia/subgrupo/materiales, revisión y exportación limpia del catálogo clasificado. No publica cambios en WooCommerce.
- **Cambio de Precios**: creación de propuestas, exportación limpia a Excel, carga del Excel revisado y publicación segura con validaciones.

La idea es mantener separados los trabajos de organización y los trabajos que pueden terminar modificando precios reales.

## Auditoría funcional vigente

La revisión honesta de módulos, separando implementación real, parcial, legacy y solo interfaz, está en:

```text
auditoria/AUDITORIA_FUNCIONAL_V1.md
```

Este documento debe consultarse antes de asumir que una pantalla o botón representa lógica operativa completa.

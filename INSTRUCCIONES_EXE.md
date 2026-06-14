# Crear FutonEspai.exe

## Forma recomendada

1. Descomprime el ZIP.
2. Entra en la carpeta del proyecto.
3. Ejecuta:

```bat
crear_exe_windows.bat
```

El ejecutable se creara en:

```txt
GestorWoo\FutonEspai.exe
```

## Importante

No muevas el `.exe` solo. Para usarlo en el negocio, copia la carpeta completa:

```txt
FutonEspai_Organizado/
├─ CalculoCoste/
└─ GestorWoo/
   ├─ FutonEspai.exe
   ├─ .env
   └─ data/
      └─ gestorwoo.sqlite3
```

La carpeta `CalculoCoste` debe quedar al lado de `GestorWoo`, porque el ejecutable abre desde ahi las herramientas de calculo.

## Si falla

Ejecuta:

```bat
crear_exe_windows_debug.bat
```

Este genera:

```txt
GestorWoo\FutonEspai_DEBUG.exe
```

Abre ese ejecutable para ver el error completo en consola.

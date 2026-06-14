# FutonHUB ERP - Instalación multi-PC v34

## Cambio importante

El ERP debe instalarse con Python 3.11 o 3.12.

No usamos Python 3.14 porque algunas dependencias nuevas de Supabase pueden arrastrar paquetes como `pyiceberg`, que en Windows/Python 3.14 intentan compilar extensiones nativas y piden Microsoft Visual C++ Build Tools.

## Instalación limpia en una PC

1. Copia el proyecto a la PC.
2. Ejecuta:

```text
INSTALAR_DEPENDENCIAS_ERP.bat
```

3. Si instala Python 3.11 con winget, cierra la ventana y vuelve a ejecutar el instalador.
4. Copia el `.env` correcto.
5. Ejecuta:

```text
Abrir ERP.bat
```

## Si ya falló antes

Si la PC ya creó un entorno con Python 3.14, el instalador v34 lo detecta y recrea `.venv_erp`.

También puedes borrarlo manualmente:

```text
rmdir /s /q .venv_erp
```

y volver a ejecutar el instalador.

## Qué cambió en los .bat

- Se prefiere Python 3.11.
- Si no existe, se acepta Python 3.12.
- Se rechaza Python 3.14.
- Se usa directamente `.venv_erp\Scripts\python.exe`, sin depender de `activate`.
- `requirements_erp.txt` pinnea `supabase==2.10.0` para evitar dependencias problemáticas innecesarias.

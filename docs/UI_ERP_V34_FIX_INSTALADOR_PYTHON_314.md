# UI ERP v34 - Fix instalador Python 3.14 / pyiceberg

## Problema

En una PC el instalador detectó Python 3.14.4 y creó/usó `.venv_erp` con esa versión.

Durante la instalación de `supabase`, pip resolvió una cadena nueva:

```text
supabase -> storage3 -> pyiceberg
```

`pyiceberg` intentó compilar una extensión nativa en Windows y falló pidiendo:

```text
Microsoft Visual C++ 14.0 or greater is required
```

## Solución

Los `.bat` ahora fuerzan Python compatible:

- preferido: Python 3.11
- aceptado: Python 3.12
- rechazado: Python 3.14

También:

- recrean `.venv_erp` si fue creado con versión incorrecta
- usan `.venv_erp\Scripts\python.exe` directamente
- no dependen de `activate`
- pinnean `supabase==2.10.0` en `requirements_erp.txt`

## Archivos modificados

```text
INSTALAR_DEPENDENCIAS_ERP.bat
Abrir ERP.bat
requirements_erp.txt
README_MULTI_PC_ERP.md
```

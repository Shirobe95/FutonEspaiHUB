# UI ERP v33 - Preparación multi-PC

## Objetivo

Preparar el ERP para pruebas en varias PCs/trabajadores con Supabase como centro de datos.

## Archivos añadidos

```text
INSTALAR_DEPENDENCIAS_ERP.bat
Abrir ERP.bat
README_MULTI_PC_ERP.md
requirements_erp.txt
```

## INSTALAR_DEPENDENCIAS_ERP.bat

Hace:

- comprobar Python
- instalar Python con winget si no existe
- crear `.venv_erp`
- actualizar pip
- instalar dependencias desde `requirements_erp.txt`
- comprobar `gestorwoo.py`

## Abrir ERP.bat

Hace:

- comprobar estructura del proyecto
- comprobar `.venv_erp`
- activar entorno virtual
- entrar en `GestorWoo`
- ejecutar:

```powershell
python gestorwoo.py erp-prototype
```

## Consideraciones multiusuario

Cada PC debe tener:

- copia actual del proyecto
- `.env` funcional
- internet
- usuario Supabase propio
- permisos/rol correcto

## Seguridad

No incluir secretos reales dentro del ZIP si se comparte externamente.  
El `.env` debe tratarse como credencial.

@echo off
setlocal EnableExtensions
title FutonHUB ERP - Preview import 12 items

cd /d "%~dp0"

set "VENV_PY=%~dp0.venv_erp\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [ERROR] No existe .venv_erp. Ejecuta INSTALAR_DEPENDENCIAS_ERP.bat primero.
    pause
    exit /b 1
)

if not exist "GestorWoo\importar_12_items_e_2026_03.py" (
    echo [ERROR] No encuentro GestorWoo\importar_12_items_e_2026_03.py
    pause
    exit /b 1
)

cd /d "%~dp0GestorWoo"

"%VENV_PY%" importar_12_items_e_2026_03.py --csv "%~dp0GestorWoo\docs\imports\E-2026-03_12_items_faltantes_completos.csv"

pause
exit /b 0

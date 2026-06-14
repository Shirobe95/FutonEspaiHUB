@echo off
setlocal EnableExtensions
title FutonHUB ERP - Importar 12 items

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

echo ============================================================
echo  Importar 12 items faltantes E-2026-03 a Supabase
echo ============================================================
echo.
echo Esto inserta/actualiza ficha base en inventory_items.
echo NO toca WooCommerce ni stock.
echo.
set /p CONFIRMAR=Escribe IMPORTAR_ITEMS para continuar: 

if not "%CONFIRMAR%"=="IMPORTAR_ITEMS" (
    echo Cancelado.
    pause
    exit /b 2
)

cd /d "%~dp0GestorWoo"

"%VENV_PY%" importar_12_items_e_2026_03.py --csv "%~dp0GestorWoo\docs\imports\E-2026-03_12_items_faltantes_completos.csv" --execute --confirm IMPORTAR_ITEMS

pause
exit /b 0

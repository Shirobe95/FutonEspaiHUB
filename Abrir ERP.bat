@echo off
setlocal EnableExtensions
title FutonHUB ERP

cd /d "%~dp0"

if not exist "GestorWoo\gestorwoo.py" (
    echo [ERROR] No encuentro GestorWoo\gestorwoo.py
    echo Ejecuta este .bat desde la carpeta raiz del proyecto FutonHUB.
    pause
    exit /b 1
)

set "PYTHON_CMD=python"
py -3 --version >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
)

if not exist "GestorWoo\.env" (
    if not exist ".env" (
        echo [ADVERTENCIA] No encuentro archivo .env.
        echo El ERP puede abrir, pero Supabase/WooCommerce no funcionaran si faltan credenciales.
        echo.
        timeout /t 4 >nul
    )
)

cd /d "%~dp0GestorWoo"

echo ============================================================
echo  Abriendo FutonHUB ERP
echo ============================================================
echo.
echo Ejecutando con: %PYTHON_CMD%
echo.

%PYTHON_CMD% gestorwoo.py erp-prototype

echo.
echo ============================================================
echo  El ERP se ha cerrado.
echo ============================================================
pause
exit /b 0

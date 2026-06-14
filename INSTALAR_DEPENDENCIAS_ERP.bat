@echo off
setlocal EnableExtensions EnableDelayedExpansion
title FutonHUB ERP - Instalar dependencias

echo ============================================================
echo  FutonHUB ERP - Instalador de dependencias
echo ============================================================
echo.
echo Este script prepara esta PC para ejecutar el ERP.
echo Version v34: fuerza Python 3.11/3.12 y evita Python 3.14.
echo.

cd /d "%~dp0"

if not exist "GestorWoo\gestorwoo.py" (
    echo [ERROR] No encuentro GestorWoo\gestorwoo.py
    echo Ejecuta este .bat desde la carpeta raiz del proyecto FutonHUB.
    pause
    exit /b 1
)

echo [1/7] Buscando Python compatible...
set "PYTHON_CMD="
set "PYTHON_VERSION="

py -3.11 --version >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3.11"
    for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do set "PYTHON_VERSION=%%v"
) else (
    py -3.12 --version >nul 2>&1
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=py -3.12"
        for /f "tokens=2" %%v in ('py -3.12 --version 2^>^&1') do set "PYTHON_VERSION=%%v"
    )
)

if "%PYTHON_CMD%"=="" (
    echo No encuentro Python 3.11 ni 3.12.
    echo.
    echo Python 3.14 NO se usara para este ERP porque algunas dependencias
    echo intentan compilar paquetes nativos y pueden pedir Visual C++ Build Tools.
    echo.
    echo Intentando instalar Python 3.11 con winget...
    winget --version >nul 2>&1
    if %ERRORLEVEL%==0 (
        winget install -e --id Python.Python.3.11
        echo.
        echo Python 3.11 se ha intentado instalar.
        echo Cierra esta ventana y vuelve a ejecutar este instalador.
        pause
        exit /b 0
    ) else (
        echo [ERROR] No encuentro winget para instalar Python automaticamente.
        echo Instala Python 3.11 manualmente desde:
        echo https://www.python.org/downloads/release/python-3119/
        echo.
        echo IMPORTANTE: marca "Add python.exe to PATH" durante la instalacion.
        pause
        exit /b 1
    )
)

echo Python seleccionado: %PYTHON_CMD% ^(%PYTHON_VERSION%^)
echo.

echo [2/7] Revisando entorno virtual .venv_erp...
set "RECREATE_VENV=0"

if exist ".venv_erp\Scripts\python.exe" (
    for /f "tokens=2" %%v in ('.venv_erp\Scripts\python.exe --version 2^>^&1') do set "VENV_VERSION=%%v"
    echo Entorno existente: Python !VENV_VERSION!
    echo !VENV_VERSION! | findstr /B "3.11 3.12" >nul
    if ERRORLEVEL 1 (
        echo El entorno existente no usa Python 3.11/3.12. Se recreara.
        set "RECREATE_VENV=1"
    )
) else (
    set "RECREATE_VENV=1"
)

if "%RECREATE_VENV%"=="1" (
    if exist ".venv_erp" (
        echo Eliminando .venv_erp anterior...
        rmdir /s /q ".venv_erp"
    )
    echo Creando entorno virtual .venv_erp...
    %PYTHON_CMD% -m venv .venv_erp
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

set "VENV_PY=%~dp0.venv_erp\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] No encuentro Python dentro de .venv_erp.
    pause
    exit /b 1
)

echo.
echo [3/7] Python del entorno:
"%VENV_PY%" --version

echo.
echo [4/7] Actualizando pip del entorno...
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo actualizando pip.
    pause
    exit /b 1
)

echo.
echo [5/7] Instalando dependencias del ERP...
if exist "requirements_erp.txt" (
    "%VENV_PY%" -m pip install -r requirements_erp.txt
) else if exist "requirements.txt" (
    "%VENV_PY%" -m pip install -r requirements.txt
) else if exist "GestorWoo\requirements.txt" (
    "%VENV_PY%" -m pip install -r "GestorWoo\requirements.txt"
) else (
    echo No se encontro requirements. Instalando dependencias base conocidas...
    "%VENV_PY%" -m pip install ^
        "supabase==2.10.0" ^
        python-dotenv ^
        requests ^
        pandas ^
        openpyxl ^
        pillow ^
        pypdf ^
        PyPDF2 ^
        reportlab ^
        python-dateutil ^
        pytest
)

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo instalando dependencias.
    echo.
    echo Si aparece pyiceberg / Visual C++ Build Tools, casi seguro se esta usando
    echo Python 3.14 o un entorno antiguo. Borra .venv_erp y vuelve a ejecutar.
    pause
    exit /b 1
)

echo.
echo [6/7] Comprobando imports criticos...
"%VENV_PY%" -c "import supabase, openpyxl, pandas, requests; print('Imports OK')"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Alguna dependencia critica no importa correctamente.
    pause
    exit /b 1
)

echo.
echo [7/7] Comprobando arranque tecnico...
cd /d "%~dp0GestorWoo"
"%VENV_PY%" -m py_compile gestorwoo.py
if %ERRORLEVEL% NEQ 0 (
    echo [ADVERTENCIA] Python funciona, pero gestorwoo.py no compilo correctamente.
    echo Revisa el error anterior.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Instalacion completada.
echo ============================================================
echo.
echo Siguiente paso:
echo  1. Verifica que el archivo .env exista y tenga Supabase configurado.
echo  2. Ejecuta "Abrir ERP.bat".
echo.
pause
exit /b 0

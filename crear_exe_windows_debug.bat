@echo off
setlocal
cd /d "%~dp0GestorWoo"

py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo No se encontro Python 3.11 con el lanzador py.
    echo Instala Python 3.11 o cambia este script para usar tu comando python.
    pause
    exit /b 1
)

py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install openpyxl requests pypdf pyinstaller

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q FutonEspai_DEBUG.spec 2>nul

echo.
echo Creando FutonEspai_DEBUG.exe con consola para ver errores...
py -3.11 -m PyInstaller ^
    --onefile ^
    --console ^
    --name FutonEspai_DEBUG ^
    --paths "%CD%\src" ^
    --collect-submodules futonhub ^
    --collect-submodules gestorwoo ^
    --hidden-import futonhub.app.cli ^
    --hidden-import gestorwoo.cli ^
    --hidden-import gestorwoo.hub ^
    --hidden-import gestorwoo.ui ^
    --hidden-import gestorwoo.inventory ^
    --hidden-import gestorwoo.backup ^
    FutonEspaiLauncher.py

if errorlevel 1 (
    echo.
    echo ERROR creando el exe debug.
    pause
    exit /b 1
)

copy /Y "dist\FutonEspai_DEBUG.exe" "FutonEspai_DEBUG.exe" >nul

echo.
echo EXE debug creado:
echo %cd%\FutonEspai_DEBUG.exe
echo.
echo Abre este si el normal falla, para ver el traceback.
pause

@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-inventory-update-internal --item-id 201001 --store-stock 15 --notes "Prueba inventario interno" --execute
pause

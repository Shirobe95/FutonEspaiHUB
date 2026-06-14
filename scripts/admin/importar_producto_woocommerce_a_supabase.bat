@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-import-woocommerce-product --query "Test Product + Var"
pause

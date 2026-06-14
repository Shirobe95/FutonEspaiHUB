@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-woocommerce-publish-preview --limit 20
pause

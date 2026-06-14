@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-search-inventory --query "tatami" --limit 20
pause

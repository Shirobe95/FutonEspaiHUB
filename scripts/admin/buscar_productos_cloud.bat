@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-search-products --query "%~1" --limit 15
pause

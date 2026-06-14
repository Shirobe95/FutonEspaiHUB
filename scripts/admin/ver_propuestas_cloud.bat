@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-list-real-price-proposals --status pending --limit 50
pause

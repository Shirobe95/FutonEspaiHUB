@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-logs --limit 50
pause

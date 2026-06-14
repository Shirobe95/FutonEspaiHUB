@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-snapshots --limit 50
pause

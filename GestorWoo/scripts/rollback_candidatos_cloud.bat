@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py cloud-rollback-candidates --limit 30
pause

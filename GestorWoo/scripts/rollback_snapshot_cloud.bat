@echo off
cd /d "%~dp0..\GestorWoo"
set /p OPID=Operation ID del snapshot a revertir: 
python gestorwoo.py cloud-rollback-snapshot --operation-id "%OPID%"
pause

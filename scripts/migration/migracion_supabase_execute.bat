@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py migrate-sqlite-to-supabase-execute --confirm MIGRAR
pause

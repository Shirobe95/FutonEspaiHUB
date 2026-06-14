@echo off
cd /d "%~dp0..\GestorWoo"
python gestorwoo.py migrate-sqlite-to-supabase-preview
pause

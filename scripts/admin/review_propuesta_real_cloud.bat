@echo off
cd /d "%~dp0..\GestorWoo"
echo Uso: review_propuesta_real_cloud.bat approved  O rejected
python gestorwoo.py cloud-review-real-price-proposal %1
pause

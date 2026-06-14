@echo off
cd /d "%~dp0..\GestorWoo"
echo Uso: python gestorwoo.py cloud-real-price-proposal --item-kind product --woo-id 123 --new-price 199 --notes "nota"
python gestorwoo.py cloud-real-price-proposal %*
pause

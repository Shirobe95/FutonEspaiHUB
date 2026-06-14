@echo off
cd /d "%~dp0..\GestorWoo"
echo Uso: python gestorwoo.py cloud-woocommerce-publish-execute --proposal-id ID --confirm PUBLICAR [--ack-woo-warning]
python gestorwoo.py cloud-woocommerce-publish-execute %*
pause

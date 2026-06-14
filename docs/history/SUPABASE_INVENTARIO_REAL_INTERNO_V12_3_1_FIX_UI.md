# FutonEspaiHUB v12.3.1 - Fix UI inventario/precios

Correcciones sobre v12.3:

- Se restaura el método `_cloud_price_heart_attack_tests` usado por el menú `Pruebas > Test estrés precios`.
- Se corrige la ventana de preview de propuestas para pasar texto renderizado, no referencias de funciones.
- No cambia la lógica de Supabase, inventario ni WooCommerce.
- No requiere SQL nuevo.

Objetivo: evitar el error de Tkinter al reconstruir la interfaz después del login.

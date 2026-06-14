# FutonEspaiHUB v8.4 - Login anclado dentro del HUB

## Objetivo

Corregir el aviso de "Iniciando sesión en Supabase" para que no aparezca como ventana flotante separada.

## Cambios

- El aviso de login ahora es un overlay interno del HUB.
- Si se mueve la ventana principal, el aviso se mueve con ella.
- El overlay cubre el contenido del HUB mientras valida usuario, rol y dispositivo.
- Se mantiene el login en hilo separado para reducir el clásico "no responde" de Windows.
- Se mantiene el modo `supabase_guarded` activo en `.env`.

## Prueba recomendada

1. Abrir HUB.
2. Confirmar que no hay herramientas antes del login.
3. Pulsar Login Supabase.
4. Mientras aparece el aviso, mover la ventana del HUB.
5. Confirmar que el aviso permanece centrado dentro del HUB.
6. Login como worker y comprobar que no se ven herramientas maestras.
7. Login como admin y comprobar logs/snapshots.

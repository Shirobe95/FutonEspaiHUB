# FutonHUB · Casco de seguridad local v3

Esta versión descarta la ruta de carpeta compartida de Windows. El HUB queda preparado para trabajar de forma local protegida, con observabilidad y frenos antes de operaciones peligrosas.

## Cambios principales

- Nuevo modo `GESTORWOO_MODE=local_guarded` en `GestorWoo/.env`.
- Nombre de máquina configurable con `GESTORWOO_MACHINE_NAME`; si queda vacío, se usa el nombre del equipo.
- Nueva tabla `system_locks` para bloquear operaciones críticas dentro de la base local.
- Diagnóstico ampliado: modo, máquina, escritura de base, último backup y bloqueos activos.
- Botón/aviso visible en el HUB con estado de seguridad.
- Backup automático previo en:
  - `Actualizar desde WooCommerce`.
  - `Publicar cambios de precio en WooCommerce`.
- Logs automáticos de inicio, OK y ERROR para operaciones críticas.
- Restaurar backup ahora usa lock interno y registra logs.

## Comandos útiles

Desde `FutonEspaiHUB/GestorWoo`:

```powershell
python gestorwoo.py diagnostic
python gestorwoo.py safety-status
python gestorwoo.py clear-stale-locks
```

## Qué NO hace todavía

- No sincroniza automáticamente varias PCs.
- No usa carpeta compartida de Windows.
- No usa Turso/libSQL.
- No convierte el HUB en cliente-servidor.

La idea es dejar primero una base local segura. Luego podremos decidir si el siguiente salto es exportación/importación controlada entre PCs o un pequeño servidor local/API.

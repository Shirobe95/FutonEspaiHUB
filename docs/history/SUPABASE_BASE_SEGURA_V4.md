# FutonHUB · Supabase Base Segura v4

Esta versión prepara el HUB para trabajo online simultáneo con Supabase, sin migrar todavía los datos reales de SQLite.

## Objetivo de v4

- Mantener el modo local estable intacto.
- Añadir configuración Supabase en `.env`.
- Añadir scripts SQL para tablas de roles, permisos, logs, snapshots y bloqueos.
- Añadir diagnóstico cloud desde consola.
- Preparar la capa Python `gestorwoo.cloud`.

## Roles definidos

- `admin`: acceso total al HUB, seguridad, logs, backups, restauración y operaciones críticas.
- `worker`: acceso operativo sin ver seguridad/logs/backups/restauración.

Los workers no verán la caja negra, pero las acciones importantes quedan registradas con `audit_logs` y `operation_snapshots`.

## Pasos en Supabase

1. Abre tu proyecto en Supabase.
2. Ve a `SQL Editor`.
3. Ejecuta `docs/supabase/01_schema_roles_logs_backups.sql`.
4. Ve a `Authentication > Users` y crea tu usuario admin.
5. Copia el UUID del usuario.
6. Edita y ejecuta `docs/supabase/02_crear_admin_manual.sql`.
7. Crea los workers en Authentication y usa `03_crear_worker_manual.sql` para registrarlos como `worker`.

## Configuración local

En `GestorWoo/.env` rellena:

```env
GESTORWOO_MODE=supabase_guarded
GESTORWOO_SYNC_ROLE=admin
GESTORWOO_USER_EMAIL=tu-email@ejemplo.com
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=tu_anon_key
```

La `SUPABASE_SERVICE_ROLE_KEY` queda comentada. No debe estar en PCs worker. Si algún día se usa, solo en tu PC admin y con mucho cuidado.

## Comandos nuevos

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-diagnostic
python gestorwoo.py cloud-status
```

Si falta el paquete Python:

```powershell
pip install supabase
```

## Qué NO hace todavía v4

- No migra productos/inventario a Supabase.
- No hace login visual.
- No permite trabajo simultáneo real aún.
- No toca WooCommerce desde Supabase.

Esta v4 es el casco y la base de hormigón antes de levantar el edificio.

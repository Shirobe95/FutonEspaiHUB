# FutonHUB v8.1 - Fix RLS Worker Snapshots

Esta versión corrige el fallo:

```txt
new row violates row-level security policy for table "operation_snapshots"
```

## Causa probable

El login era correcto, pero algunas versiones de `supabase-py` no aplican automáticamente el token del usuario autenticado al subcliente PostgREST usado por `.table(...).insert(...)`.

Resultado: el HUB parecía logueado, pero el `insert` a `operation_snapshots` podía llegar como `anon`, y RLS lo bloqueaba.

## Cambios

- `cloud/auth.py` fuerza que el token de sesión se aplique a PostgREST tras login.
- Se añade SQL de limpieza RLS:

```txt
docs/supabase/07_fix_rls_worker_snapshots_v8_1.sql
```

## Pasos

1. Ejecuta el SQL `07_fix_rls_worker_snapshots_v8_1.sql` en Supabase.
2. Usa esta versión v8.1.
3. Ejecuta:

```powershell
python gestorwoo.py cloud-worker-feedback-test
```

Hazlo dos veces. La segunda debe generar snapshot.

4. Entra como admin y revisa:

```powershell
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
```

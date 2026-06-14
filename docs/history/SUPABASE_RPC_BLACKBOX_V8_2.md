# FutonHUB v8.2 - Caja negra por RPC

Esta versión corrige el fallo de RLS al escribir `operation_snapshots` desde un worker.

## Qué cambió

La escritura de `audit_logs` y `operation_snapshots` ahora usa funciones RPC de Supabase:

- `futonhub_write_audit_log`
- `futonhub_write_operation_snapshot`

Estas funciones son `security definer`, validan que el `user_id` exista en `profiles`, esté activo y tenga rol `admin` o `worker`, y escriben la caja negra sin dar al worker permiso de lectura sobre logs/snapshots.

## Paso obligatorio

Ejecutar en Supabase > SQL Editor:

```txt
/docs/supabase/08_rpc_blackbox_worker_v8_2.sql
```

## Prueba

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-worker-feedback-test
```

Ejecutarlo dos veces:

1. Primera vez: crea o actualiza `TEST_WORKER_FEEDBACK`.
2. Segunda vez: genera snapshot del valor anterior y log de la acción.

Luego entrar como admin y revisar:

```powershell
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
```

## Limpieza

```powershell
python gestorwoo.py cloud-clean-worker-feedback-test
```

La limpieza borra la constante de prueba, pero deja el rastro de auditoría.

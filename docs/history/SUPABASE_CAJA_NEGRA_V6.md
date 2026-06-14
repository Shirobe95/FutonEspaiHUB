# FutonHUB v6 · Caja Negra Supabase

Esta versión añade la primera capa operativa de auditoría online sobre Supabase, sin migrar todavía productos ni inventario.

## Objetivo

- Mantener el HUB en modo `supabase_guarded`.
- Usar login real de Supabase para que RLS permita leer/escribir según rol.
- Permitir que el admin vea logs y snapshots.
- Dejar preparadas funciones para que las operaciones futuras creen registros automáticos invisibles para workers.

## Comandos nuevos

Desde `FutonEspaiHUB/GestorWoo`:

```powershell
python gestorwoo.py cloud-test-log
python gestorwoo.py cloud-test-snapshot
python gestorwoo.py cloud-logs --limit 50
python gestorwoo.py cloud-snapshots --limit 50
```

Todos estos comandos piden la contraseña de Supabase en consola. La contraseña no se guarda en `.env` ni en archivos del HUB.

## Botones nuevos en el HUB para admin

Cuando el HUB está en `supabase_guarded` y el rol local es `admin`, aparecen botones privados en el pie:

- `Test log`
- `Test snapshot`
- `Logs cloud`
- `Snapshots cloud`

Si no hay sesión activa, al pulsarlos primero se abre el login Supabase.

## Qué se escribe en Supabase

### `audit_logs`

Registra quién hizo qué, desde qué máquina, en qué módulo, con qué resultado y con qué `operation_id`.

### `operation_snapshots`

Guarda una copia lógica del estado anterior de una entidad antes de una operación delicada. En v6 solo se crean snapshots de prueba.

## Estado de seguridad

- Workers no ven estos botones si su `.env` usa `GESTORWOO_SYNC_ROLE=worker`.
- RLS mantiene `audit_logs` y `operation_snapshots` visibles solo para admin.
- La v6 no toca WooCommerce ni migra inventario/productos.

## Siguiente fase sugerida

v7 debería conectar esta caja negra a una operación real y controlada, por ejemplo:

1. Crear propuesta de precio online.
2. Guardar `audit_log` automático.
3. Crear snapshot antes de editar/aprobar.
4. Mostrar al worker solo mensajes simples.
5. Mostrar al admin el historial completo.

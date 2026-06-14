# FutonEspaiHUB v8.3 - Worker UI segura

Objetivo: cerrar la interfaz por defecto hasta que exista login real de Supabase.

## Cambios

- En modo `supabase_guarded`, el HUB arranca bloqueado y no muestra herramientas operativas.
- Tras login Supabase, se reconstruye la interfaz según el rol cloud real (`profiles.role`).
- Worker no ve herramientas maestras: logs, snapshots, backups, restauración, seguridad, diagnóstico avanzado ni usuarios.
- Admin ve herramientas completas después del login.
- Login Supabase se ejecuta en un hilo separado para reducir el estado "no responde" de Tkinter.
- Lectura admin de logs/snapshots por RPC `security definer` para evitar falsos vacíos si el cliente REST pierde token.

## SQL requerido

Ejecutar en Supabase:

```txt
/docs/supabase/09_rpc_admin_read_blackbox_v8_3.sql
```

## Prueba recomendada

1. Abrir HUB.
2. Confirmar que no aparecen tarjetas operativas antes del login.
3. Login como worker.
4. Confirmar que aparecen herramientas operativas, pero no motor/admin.
5. Ejecutar `Test worker`.
6. Cerrar/reiniciar HUB.
7. Login como admin.
8. Abrir `Logs cloud` y `Snapshots cloud`.
9. Confirmar que aparecen los `WORKERTEST-*` del worker.

## Nota

WooCommerce sigue sin tocarse en esta fase.

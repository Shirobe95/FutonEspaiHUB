# Propuesta S_hardening_001 (Supabase) — NO aplicada en producción

Derivada de la auditoría 2026-10 (hallazgos S1–S10). Solo se ha probado en un Postgres de laboratorio
(`../lab/`) con el esquema vivo reconstruido a partir de consultas de solo lectura. **Nada de esto se ha
ejecutado en el proyecto Supabase real.** Aplicarla es una decisión del propietario, con una ventana de
revisión y la reversión lista (`S_hardening_001_rollback.sql`).

## Bloques (independientes)
| Bloque | Qué corrige | Riesgo de compatibilidad |
|---|---|---|
| A | RPC `futonhub_read_audit_logs`, `read_operation_snapshots`, `clean_*` y `review_*` ejecutables por `anon` y con `p_user_id` falsificable. Ahora exigen `auth.uid() = p_user_id`, admin activo y `EXECUTE` solo para `authenticated`. También corrige `v_role <> 'admin'` con `v_role` NULL (no lanzaba excepción). | Un cliente que llame a esas RPC **sin JWT de usuario** (sesión anon) dejará de funcionar. El ERP envía el JWT (`_apply_authenticated_token`), pero debe verificarse en un PC real. |
| B | `audit_logs` y `operation_snapshots` aceptaban `INSERT` con `WITH CHECK (true)` (cualquiera podía falsificar auditoría de otro usuario o inundarla). Ahora `user_id = auth.uid()` y worker/admin. | Ninguna para el ERP (escribe por RPC o, en el *fallback*, con su propio `user_id`). |
| C | `GRANT ALL` a `anon` y `TRUNCATE/TRIGGER/REFERENCES` a `authenticated` sobre todas las tablas: un worker podía `TRUNCATE audit_logs` (RLS no protege `TRUNCATE`). Se quitan. | Ninguna prevista: el ERP no usa `TRUNCATE` ni accede como `anon`. |
| D | Vistas `v_inventory_*` legibles por `anon` (cubierto por C). **No** se usa `security_invoker`: dejaría la búsqueda de componentes en 0 filas. | — |
| F | `futonhub_acquire_system_lock` no era atómico para claves nuevas (en la prueba, 284 de 300 carreras terminaron con **dos** locks adquiridos). Ahora `INSERT … ON CONFLICT DO NOTHING` primero. | Ninguna (misma firma y mismo contrato JSON). |
| E | **Requiere decisión de negocio.** Un worker podía poner `status='published'/'approved'/'publishing'` y rellenar `reviewed_by/published_by`. Un trigger lo limita a admin y congela el precio de propuestas ya aprobadas/publicadas. | Si los workers deben poder publicar precios, **no aplicar E** (o ajustar la lista de estados). Hoy el ERP publica con la sesión del usuario: un worker que publique empezaría a recibir error. |

## Evidencia en laboratorio
- 108 ataques de la auditoría, antes/después: `evidence_attacks_before.txt` / `evidence_attacks_after.txt`
  (`../lab/run_lab.sh ../proposals/S_hardening_001.sql` los regenera).
- Antes → después: `UPDATE status='published'` por worker (UPDATE 1 → error), RPC de logs por `anon` (devuelve filas → denegado),
  `TRUNCATE audit_logs` por worker (TRUNCATE → denegado), `INSERT` de auditoría falsa (insertado → violación de RLS),
  vistas como `anon` (legibles → denegado), `clean_*` por `anon` (borraba → denegado).
- Carreras de locks (300 × 3 escenarios): clave nueva **0/300 dobles** (antes 284/300) — `evidence_lock_race_after.txt`.
- Flujos legítimos comprobados tras aplicar: worker escribe su auditoría (fallback REST), edita/rechaza una propuesta
  pendiente, admin aprueba→publica→revierte, admin lee logs por RPC y limpia el inventario simulado, `service_role` sigue
  pudiendo mantener estados, y los workers siguen viendo la búsqueda de componentes.
- Reversión: aplicar + revertir en dos bases limpias deja el esquema y los ACL **idénticos** (diff de `pg_dump -s`).

## Limitaciones
- El laboratorio simula `auth.uid()` y los roles de Supabase; no es Supabase real (sin PostgREST ni Auth).
- El esquema vivo se reconstruyó por lectura; si el proyecto cambió desde entonces, regenerar `live_schema.sql`.
- Cubre S1–S4 y el bloqueo de TRUNCATE. **No** cubre aún: `script 19 elimina 'rolled_back' del CHECK tras 011`, ni que el SQL
  versionado del repo no reconstruya el esquema vivo (S10): `../lab/live_schema.sql` es un primer paso, no una migración.

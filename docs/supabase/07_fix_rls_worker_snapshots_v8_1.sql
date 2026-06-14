-- =====================================================
-- FutonHUB v8.1 - Fix RLS worker snapshots/logs
-- =====================================================
-- Objetivo:
-- - Workers/admin pueden ESCRIBIR audit_logs y operation_snapshots.
-- - Solo admin puede LEER audit_logs y operation_snapshots.
-- - Se limpian políticas duplicadas de versiones anteriores.

create or replace function public.current_user_role()
returns text
language sql
security definer
set search_path = public
as $$
  select p.role
  from public.profiles p
  where p.id = auth.uid()
    and p.active = true
  limit 1;
$$;

grant execute on function public.current_user_role() to authenticated;

-- -------------------------
-- operation_snapshots
-- -------------------------
drop policy if exists "snapshots_authenticated_insert" on public.operation_snapshots;
drop policy if exists "snapshots_admin_read" on public.operation_snapshots;
drop policy if exists "workers_and_admin_can_insert_operation_snapshots" on public.operation_snapshots;
drop policy if exists "only_admin_can_read_operation_snapshots" on public.operation_snapshots;
drop policy if exists "operation_snapshots_authenticated_insert" on public.operation_snapshots;
drop policy if exists "operation_snapshots_admin_select" on public.operation_snapshots;

create policy "operation_snapshots_authenticated_insert"
on public.operation_snapshots
for insert
to authenticated
with check (true);

create policy "operation_snapshots_admin_select"
on public.operation_snapshots
for select
to authenticated
using (public.current_user_role() = 'admin');

-- -------------------------
-- audit_logs
-- -------------------------
drop policy if exists "audit_authenticated_insert" on public.audit_logs;
drop policy if exists "audit_admin_read" on public.audit_logs;
drop policy if exists "workers_can_insert_audit_logs" on public.audit_logs;
drop policy if exists "workers_and_admin_can_insert_audit_logs" on public.audit_logs;
drop policy if exists "only_admin_can_read_audit_logs" on public.audit_logs;
drop policy if exists "admins_can_read_audit_logs" on public.audit_logs;
drop policy if exists "admin_read_audit_logs" on public.audit_logs;
drop policy if exists "audit_logs_authenticated_insert" on public.audit_logs;
drop policy if exists "audit_logs_admin_select" on public.audit_logs;

create policy "audit_logs_authenticated_insert"
on public.audit_logs
for insert
to authenticated
with check (true);

create policy "audit_logs_admin_select"
on public.audit_logs
for select
to authenticated
using (public.current_user_role() = 'admin');

-- Verificación esperada:
select tablename, policyname, cmd, roles, qual, with_check
from pg_policies
where schemaname = 'public'
  and tablename in ('operation_snapshots', 'audit_logs')
order by tablename, cmd, policyname;

-- FutonHUB v8.2 - Caja negra por RPC para workers
-- Ejecutar en Supabase > SQL Editor.
-- Objetivo:
--   - Worker/Admin pueden generar audit_logs y operation_snapshots invisibles.
--   - Worker NO necesita permiso directo sobre las tablas de caja negra.
--   - Admin sigue siendo el único que lee logs/snapshots por RLS.
--
-- Motivo del parche:
-- En algunos entornos, supabase-py inicia sesión correctamente pero el subcliente
-- PostgREST usado por .table(...).insert(...) puede seguir actuando como anon.
-- Estas RPC security definer validan el usuario contra profiles y escriben la caja negra
-- sin depender de políticas INSERT directas sobre audit_logs/operation_snapshots.

create or replace function public.futonhub_write_audit_log(
  p_operation_id text,
  p_user_id uuid,
  p_user_email text,
  p_role text,
  p_device_id uuid,
  p_machine_name text,
  p_module text,
  p_action text,
  p_status text,
  p_severity text default 'INFO',
  p_entity_type text default null,
  p_entity_id text default null,
  p_before_data jsonb default null,
  p_after_data jsonb default null,
  p_message text default null,
  p_error_detail text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_id uuid;
  v_severity text;
  v_status text;
begin
  select *
    into v_profile
    from public.profiles
   where id = p_user_id
     and lower(email) = lower(coalesce(p_user_email, email))
     and active = true
   limit 1;

  if v_profile.id is null then
    raise exception 'FutonHUB blackbox: usuario no válido o inactivo para audit_log';
  end if;

  if v_profile.role not in ('admin', 'worker') then
    raise exception 'FutonHUB blackbox: rol no autorizado para audit_log';
  end if;

  v_severity := upper(coalesce(nullif(p_severity, ''), 'INFO'));
  if v_severity not in ('INFO', 'WARNING', 'ERROR', 'CRITICAL') then
    v_severity := 'INFO';
  end if;

  v_status := upper(coalesce(nullif(p_status, ''), 'OK'));

  insert into public.audit_logs(
    operation_id,
    user_id,
    user_email,
    role,
    device_id,
    machine_name,
    module,
    action,
    entity_type,
    entity_id,
    severity,
    status,
    before_data,
    after_data,
    message,
    error_detail
  ) values (
    p_operation_id,
    v_profile.id,
    v_profile.email,
    v_profile.role,
    p_device_id,
    p_machine_name,
    p_module,
    p_action,
    p_entity_type,
    p_entity_id,
    v_severity,
    v_status,
    p_before_data,
    p_after_data,
    p_message,
    p_error_detail
  )
  returning id into v_id;

  return jsonb_build_object(
    'id', v_id,
    'operation_id', p_operation_id,
    'user_id', v_profile.id,
    'user_email', v_profile.email,
    'role', v_profile.role,
    'module', p_module,
    'action', p_action,
    'status', v_status,
    'severity', v_severity
  );
end;
$$;

create or replace function public.futonhub_write_operation_snapshot(
  p_operation_id text,
  p_user_id uuid,
  p_module text,
  p_action text,
  p_entity_type text,
  p_entity_id text,
  p_before_data jsonb,
  p_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_id uuid;
begin
  select *
    into v_profile
    from public.profiles
   where id = p_user_id
     and active = true
   limit 1;

  if v_profile.id is null then
    raise exception 'FutonHUB blackbox: usuario no válido o inactivo para operation_snapshot';
  end if;

  if v_profile.role not in ('admin', 'worker') then
    raise exception 'FutonHUB blackbox: rol no autorizado para operation_snapshot';
  end if;

  insert into public.operation_snapshots(
    operation_id,
    user_id,
    module,
    action,
    entity_type,
    entity_id,
    before_data,
    reason
  ) values (
    p_operation_id,
    v_profile.id,
    p_module,
    p_action,
    p_entity_type,
    p_entity_id,
    coalesce(p_before_data, '{}'::jsonb),
    p_reason
  )
  returning id into v_id;

  return jsonb_build_object(
    'id', v_id,
    'operation_id', p_operation_id,
    'user_id', v_profile.id,
    'role', v_profile.role,
    'module', p_module,
    'action', p_action,
    'entity_type', p_entity_type,
    'entity_id', p_entity_id
  );
end;
$$;

-- Permitir llamada desde la app con anon key o sesión autenticada.
-- La función NO escribe si el user_id no existe en profiles y no está activo.
revoke all on function public.futonhub_write_audit_log(text, uuid, text, text, uuid, text, text, text, text, text, text, text, jsonb, jsonb, text, text) from public;
revoke all on function public.futonhub_write_operation_snapshot(text, uuid, text, text, text, text, jsonb, text) from public;

grant execute on function public.futonhub_write_audit_log(text, uuid, text, text, uuid, text, text, text, text, text, text, text, jsonb, jsonb, text, text) to anon, authenticated;
grant execute on function public.futonhub_write_operation_snapshot(text, uuid, text, text, text, text, jsonb, text) to anon, authenticated;

-- Mantener lectura protegida por RLS: solo admin puede ver caja negra.
drop policy if exists "operation_snapshots_admin_select" on public.operation_snapshots;
drop policy if exists "only_admin_can_read_operation_snapshots" on public.operation_snapshots;
drop policy if exists "snapshots_admin_read" on public.operation_snapshots;

create policy "operation_snapshots_admin_select"
on public.operation_snapshots
for select
to authenticated
using (public.current_user_role() = 'admin');

drop policy if exists "audit_logs_admin_select" on public.audit_logs;
drop policy if exists "only_admin_can_read_audit_logs" on public.audit_logs;
drop policy if exists "audit_admin_read" on public.audit_logs;

create policy "audit_logs_admin_select"
on public.audit_logs
for select
to authenticated
using (public.current_user_role() = 'admin');

-- Las políticas INSERT directas pueden quedar, pero ya no son necesarias para la app v8.2.
-- Si quieres comprobar las RPC:
-- select public.futonhub_write_operation_snapshot('RPC-TEST', '<UUID_USUARIO>'::uuid, 'diagnostic', 'rpc_test', 'test', 'manual', '{"ok":true}'::jsonb, 'Prueba manual');

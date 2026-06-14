-- FutonHUB v8.3 - Lectura admin de Caja Negra por RPC
-- Ejecutar en Supabase > SQL Editor.
-- Objetivo:
--   - Evitar que la lectura admin dependa de que el subcliente REST conserve bien el token.
--   - Workers siguen sin poder leer logs/snapshots.
--   - Solo usuarios con profile.role='admin' y active=true pueden leer.

create or replace function public.futonhub_read_audit_logs(
  p_user_id uuid,
  p_limit integer default 50
)
returns table (
  id uuid,
  created_at timestamptz,
  operation_id text,
  user_email text,
  role text,
  machine_name text,
  module text,
  action text,
  severity text,
  status text,
  entity_type text,
  entity_id text,
  message text,
  error_detail text
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (
    select 1
      from public.profiles p
     where p.id = p_user_id
       and p.active = true
       and p.role = 'admin'
  ) then
    raise exception 'FutonHUB blackbox: solo admin puede leer audit_logs';
  end if;

  return query
  select
    a.id,
    a.created_at,
    a.operation_id,
    a.user_email,
    a.role,
    a.machine_name,
    a.module,
    a.action,
    a.severity,
    a.status,
    a.entity_type,
    a.entity_id,
    a.message,
    a.error_detail
  from public.audit_logs a
  order by a.created_at desc
  limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$$;

create or replace function public.futonhub_read_operation_snapshots(
  p_user_id uuid,
  p_limit integer default 50
)
returns table (
  id uuid,
  created_at timestamptz,
  operation_id text,
  user_id uuid,
  module text,
  action text,
  entity_type text,
  entity_id text,
  before_data jsonb,
  reason text
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (
    select 1
      from public.profiles p
     where p.id = p_user_id
       and p.active = true
       and p.role = 'admin'
  ) then
    raise exception 'FutonHUB blackbox: solo admin puede leer operation_snapshots';
  end if;

  return query
  select
    s.id,
    s.created_at,
    s.operation_id,
    s.user_id,
    s.module,
    s.action,
    s.entity_type,
    s.entity_id,
    s.before_data,
    s.reason
  from public.operation_snapshots s
  order by s.created_at desc
  limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$$;

revoke all on function public.futonhub_read_audit_logs(uuid, integer) from public;
revoke all on function public.futonhub_read_operation_snapshots(uuid, integer) from public;

grant execute on function public.futonhub_read_audit_logs(uuid, integer) to authenticated, anon;
grant execute on function public.futonhub_read_operation_snapshots(uuid, integer) to authenticated, anon;

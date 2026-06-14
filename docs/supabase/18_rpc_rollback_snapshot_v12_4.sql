-- FutonHUB v12.4 · RPC admin para leer un snapshot por operation_id
-- No concede permisos de rollback a workers. Solo permite lectura a usuarios con role='admin'.

create or replace function public.futonhub_read_snapshot_by_operation_id(
  p_user_id uuid,
  p_operation_id text
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
      and p.id = auth.uid()
      and p.active = true
      and p.role = 'admin'
  ) then
    raise exception 'Solo admin puede leer snapshots para rollback';
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
  where s.operation_id = p_operation_id
  order by s.created_at desc
  limit 1;
end;
$$;

grant execute on function public.futonhub_read_snapshot_by_operation_id(uuid, text) to authenticated;

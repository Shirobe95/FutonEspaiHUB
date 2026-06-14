-- FutonHUB v13.1 - Hardening seguridad + locks online
-- Ejecutar en Supabase > SQL Editor despues de los scripts 01-18.
--
-- Objetivos:
-- 1) Caja negra por RPC solo para usuarios autenticados y vinculados a auth.uid().
-- 2) Evitar que cualquier usuario authenticated pueda escribir datos operativos sin rol activo.
-- 3) Preparar locks atomicos para operaciones criticas como publicacion WooCommerce.

-- ---------------------------------------------------------------------------
-- 1) Caja negra: no aceptar user_id suplantado ni llamadas anon
-- ---------------------------------------------------------------------------

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
  if auth.uid() is null or p_user_id is null or p_user_id <> auth.uid() then
    raise exception 'FutonHUB blackbox: usuario autenticado no coincide con p_user_id';
  end if;

  select *
    into v_profile
    from public.profiles
   where id = auth.uid()
     and active = true
   limit 1;

  if v_profile.id is null then
    raise exception 'FutonHUB blackbox: usuario no valido o inactivo para audit_log';
  end if;

  if v_profile.role not in ('admin', 'worker') then
    raise exception 'FutonHUB blackbox: rol no autorizado para audit_log';
  end if;

  if p_user_email is not null and lower(p_user_email) <> lower(v_profile.email) then
    raise exception 'FutonHUB blackbox: email no coincide con el perfil autenticado';
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
  )
  values (
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
  if auth.uid() is null or p_user_id is null or p_user_id <> auth.uid() then
    raise exception 'FutonHUB blackbox: usuario autenticado no coincide con p_user_id';
  end if;

  select *
    into v_profile
    from public.profiles
   where id = auth.uid()
     and active = true
   limit 1;

  if v_profile.id is null then
    raise exception 'FutonHUB blackbox: usuario no valido o inactivo para operation_snapshot';
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
  )
  values (
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

revoke all on function public.futonhub_write_audit_log(text, uuid, text, text, uuid, text, text, text, text, text, text, text, jsonb, jsonb, text, text) from public;
revoke all on function public.futonhub_write_audit_log(text, uuid, text, text, uuid, text, text, text, text, text, text, text, jsonb, jsonb, text, text) from anon;
revoke all on function public.futonhub_write_operation_snapshot(text, uuid, text, text, text, text, jsonb, text) from public;
revoke all on function public.futonhub_write_operation_snapshot(text, uuid, text, text, text, text, jsonb, text) from anon;

grant execute on function public.futonhub_write_audit_log(text, uuid, text, text, uuid, text, text, text, text, text, text, text, jsonb, jsonb, text, text) to authenticated;
grant execute on function public.futonhub_write_operation_snapshot(text, uuid, text, text, text, text, jsonb, text) to authenticated;

-- ---------------------------------------------------------------------------
-- 2) RLS operativo: exigir perfil activo y rol adecuado
-- ---------------------------------------------------------------------------

create or replace function public.has_role(p_roles text[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles p
    where p.id = auth.uid()
      and p.active = true
      and p.role = any(p_roles)
  )
$$;

create or replace function public.is_worker_or_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_role(array['admin', 'worker'])
$$;

drop policy if exists "inventory_authenticated_insert" on public.inventory_items;
drop policy if exists "inventory_authenticated_update" on public.inventory_items;
drop policy if exists "supplier_prices_authenticated_insert" on public.supplier_prices;
drop policy if exists "supplier_prices_authenticated_update" on public.supplier_prices;
drop policy if exists "heca_stock_authenticated_insert" on public.heca_stock;
drop policy if exists "heca_stock_authenticated_update" on public.heca_stock;
drop policy if exists "price_proposals_authenticated_insert" on public.price_change_proposals;
drop policy if exists "price_proposals_authenticated_update" on public.price_change_proposals;
drop policy if exists "price_change_proposals_authenticated_insert" on public.price_change_proposals;
drop policy if exists "price_change_proposals_authenticated_update" on public.price_change_proposals;
drop policy if exists "supplier_orders_authenticated_insert" on public.supplier_orders;
drop policy if exists "supplier_orders_authenticated_update" on public.supplier_orders;
drop policy if exists "supplier_order_items_authenticated_insert" on public.supplier_order_items;
drop policy if exists "supplier_order_items_authenticated_update" on public.supplier_order_items;
drop policy if exists "business_constants_authenticated_insert" on public.business_constants;
drop policy if exists "business_constants_authenticated_update" on public.business_constants;

create policy "inventory_worker_admin_insert" on public.inventory_items
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "inventory_worker_admin_update" on public.inventory_items
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

create policy "supplier_prices_worker_admin_insert" on public.supplier_prices
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "supplier_prices_worker_admin_update" on public.supplier_prices
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

create policy "heca_stock_worker_admin_insert" on public.heca_stock
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "heca_stock_worker_admin_update" on public.heca_stock
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

create policy "price_proposals_worker_admin_insert" on public.price_change_proposals
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "price_proposals_worker_admin_update" on public.price_change_proposals
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

alter table public.price_change_proposals
  drop constraint if exists price_change_proposals_status_check;

alter table public.price_change_proposals
  add constraint price_change_proposals_status_check
  check (status in ('pending','approved','publishing','rejected','published','error','cancelled'));

create policy "supplier_orders_worker_admin_insert" on public.supplier_orders
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "supplier_orders_worker_admin_update" on public.supplier_orders
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

create policy "supplier_order_items_worker_admin_insert" on public.supplier_order_items
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "supplier_order_items_worker_admin_update" on public.supplier_order_items
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

create policy "business_constants_worker_admin_insert" on public.business_constants
for insert to authenticated
with check (public.is_worker_or_admin());

create policy "business_constants_worker_admin_update" on public.business_constants
for update to authenticated
using (public.is_worker_or_admin())
with check (public.is_worker_or_admin());

-- ---------------------------------------------------------------------------
-- 3) Locks atomicos para operaciones criticas
-- ---------------------------------------------------------------------------

create or replace function public.futonhub_acquire_system_lock(
  p_operation_key text,
  p_user_id uuid,
  p_machine_name text,
  p_details text default '',
  p_ttl_minutes integer default 15
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_now timestamptz := now();
  v_expires timestamptz;
  v_existing public.system_locks%rowtype;
begin
  if auth.uid() is null or p_user_id is null or p_user_id <> auth.uid() then
    raise exception 'FutonHUB lock: usuario autenticado no coincide con p_user_id';
  end if;

  select *
    into v_profile
    from public.profiles
   where id = auth.uid()
     and active = true
   limit 1;

  if v_profile.id is null or v_profile.role <> 'admin' then
    raise exception 'FutonHUB lock: solo admin activo puede bloquear operaciones criticas';
  end if;

  if coalesce(trim(p_operation_key), '') = '' then
    raise exception 'FutonHUB lock: operation_key vacio';
  end if;

  v_expires := v_now + make_interval(mins => greatest(1, least(coalesce(p_ttl_minutes, 15), 120)));

  select *
    into v_existing
    from public.system_locks
   where operation_key = p_operation_key
   for update;

  if found and v_existing.status = 'running' and v_existing.expires_at > v_now then
    return jsonb_build_object(
      'acquired', false,
      'operation_key', v_existing.operation_key,
      'locked_by', v_existing.locked_by,
      'locked_by_machine', v_existing.locked_by_machine,
      'expires_at', v_existing.expires_at,
      'details', v_existing.details
    );
  end if;

  insert into public.system_locks(
    operation_key,
    locked_by,
    locked_by_machine,
    locked_at,
    expires_at,
    status,
    details
  )
  values (
    p_operation_key,
    v_profile.id,
    p_machine_name,
    v_now,
    v_expires,
    'running',
    p_details
  )
  on conflict(operation_key) do update set
    locked_by = excluded.locked_by,
    locked_by_machine = excluded.locked_by_machine,
    locked_at = excluded.locked_at,
    expires_at = excluded.expires_at,
    status = 'running',
    details = excluded.details;

  return jsonb_build_object(
    'acquired', true,
    'operation_key', p_operation_key,
    'locked_by', v_profile.id,
    'locked_by_machine', p_machine_name,
    'expires_at', v_expires,
    'details', p_details
  );
end;
$$;

create or replace function public.futonhub_release_system_lock(
  p_operation_key text,
  p_user_id uuid,
  p_status text default 'released'
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status text;
begin
  if auth.uid() is null or p_user_id is null or p_user_id <> auth.uid() then
    raise exception 'FutonHUB lock: usuario autenticado no coincide con p_user_id';
  end if;

  if not public.has_role(array['admin']) then
    raise exception 'FutonHUB lock: solo admin puede liberar operaciones criticas';
  end if;

  v_status := lower(coalesce(nullif(p_status, ''), 'released'));
  if v_status not in ('released', 'failed', 'expired') then
    v_status := 'released';
  end if;

  update public.system_locks
     set status = v_status,
         expires_at = now()
   where operation_key = p_operation_key
     and locked_by = auth.uid();

  return jsonb_build_object(
    'released', found,
    'operation_key', p_operation_key,
    'status', v_status
  );
end;
$$;

revoke all on function public.futonhub_acquire_system_lock(text, uuid, text, text, integer) from public;
revoke all on function public.futonhub_acquire_system_lock(text, uuid, text, text, integer) from anon;
revoke all on function public.futonhub_release_system_lock(text, uuid, text) from public;
revoke all on function public.futonhub_release_system_lock(text, uuid, text) from anon;

grant execute on function public.futonhub_acquire_system_lock(text, uuid, text, text, integer) to authenticated;
grant execute on function public.futonhub_release_system_lock(text, uuid, text) to authenticated;

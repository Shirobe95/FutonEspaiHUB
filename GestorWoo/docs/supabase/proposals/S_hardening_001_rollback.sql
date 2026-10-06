-- =====================================================================================
-- REVERSION de S_hardening_001 (devuelve la definicion VIVA original; NO aplicada en produccion)
-- =====================================================================================
begin;
drop trigger if exists price_change_proposals_guard on public.price_change_proposals;
drop function if exists public.price_change_proposals_guard();

drop policy if exists audit_logs_authenticated_insert on public.audit_logs;
create policy audit_logs_authenticated_insert on public.audit_logs for insert to authenticated with check (true);
drop policy if exists operation_snapshots_authenticated_insert on public.operation_snapshots;
create policy operation_snapshots_authenticated_insert on public.operation_snapshots for insert to authenticated with check (true);

grant all on all tables in schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.futonhub_acquire_system_lock(p_operation_key text, p_user_id uuid, p_machine_name text, p_details text DEFAULT ''::text, p_ttl_minutes integer DEFAULT 15)
 RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
declare
  v_profile public.profiles%rowtype; v_now timestamptz := now(); v_expires timestamptz; v_existing public.system_locks%rowtype;
begin
  if auth.uid() is null or p_user_id is null or p_user_id <> auth.uid() then
    raise exception 'FutonHUB lock: usuario autenticado no coincide con p_user_id';
  end if;
  select * into v_profile from public.profiles where id = auth.uid() and active = true limit 1;
  if v_profile.id is null or v_profile.role <> 'admin' then
    raise exception 'FutonHUB lock: solo admin activo puede bloquear operaciones criticas';
  end if;
  if coalesce(trim(p_operation_key), '') = '' then
    raise exception 'FutonHUB lock: operation_key vacio';
  end if;
  v_expires := v_now + make_interval(mins => greatest(1, least(coalesce(p_ttl_minutes, 15), 120)));
  select * into v_existing from public.system_locks where operation_key = p_operation_key for update;
  if found and v_existing.status = 'running' and v_existing.expires_at > v_now then
    return jsonb_build_object('acquired', false,'operation_key', v_existing.operation_key,'locked_by', v_existing.locked_by,
      'locked_by_machine', v_existing.locked_by_machine,'expires_at', v_existing.expires_at,'details', v_existing.details);
  end if;
  insert into public.system_locks(operation_key, locked_by, locked_by_machine, locked_at, expires_at, status, details)
  values (p_operation_key, v_profile.id, p_machine_name, v_now, v_expires, 'running', p_details)
  on conflict(operation_key) do update set locked_by = excluded.locked_by, locked_by_machine = excluded.locked_by_machine,
    locked_at = excluded.locked_at, expires_at = excluded.expires_at, status = 'running', details = excluded.details;
  return jsonb_build_object('acquired', true,'operation_key', p_operation_key,'locked_by', v_profile.id,
    'locked_by_machine', p_machine_name,'expires_at', v_expires,'details', p_details);
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_read_audit_logs(p_user_id uuid, p_limit integer DEFAULT 50)
 RETURNS TABLE(id uuid, created_at timestamptz, operation_id text, user_email text, role text, machine_name text, module text, action text, severity text, status text, entity_type text, entity_id text, message text, error_detail text)
 LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
begin
  if not exists (select 1 from public.profiles p where p.id = p_user_id and p.active = true and p.role = 'admin') then
    raise exception 'FutonHUB blackbox: solo admin puede leer audit_logs';
  end if;
  return query select a.id, a.created_at, a.operation_id, a.user_email, a.role, a.machine_name, a.module, a.action, a.severity, a.status, a.entity_type, a.entity_id, a.message, a.error_detail
  from public.audit_logs a order by a.created_at desc limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_read_operation_snapshots(p_user_id uuid, p_limit integer DEFAULT 50)
 RETURNS TABLE(id uuid, created_at timestamptz, operation_id text, user_id uuid, module text, action text, entity_type text, entity_id text, before_data jsonb, reason text)
 LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
begin
  if not exists (select 1 from public.profiles p where p.id = p_user_id and p.active = true and p.role = 'admin') then
    raise exception 'FutonHUB blackbox: solo admin puede leer operation_snapshots';
  end if;
  return query select s.id, s.created_at, s.operation_id, s.user_id, s.module, s.action, s.entity_type, s.entity_id, s.before_data, s.reason
  from public.operation_snapshots s order by s.created_at desc limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_clean_worker_simulated_inventory(p_user_id uuid, p_item_id bigint DEFAULT '-900001'::integer)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
declare v_role text; v_exists bigint;
begin
    select role into v_role from public.profiles where id = p_user_id and active = true limit 1;
    if v_role is distinct from 'admin' then raise exception 'Solo admin puede limpiar inventario simulado worker.'; end if;
    if p_item_id is distinct from -900001 then raise exception 'Esta RPC solo puede limpiar TEST_WORKER_INVENTORY_ITEM.'; end if;
    select item_id into v_exists from public.inventory_items
    where item_id = p_item_id and name = 'TEST_WORKER_INVENTORY_ITEM' and coalesce(source_row->>'test', 'false') = 'true' limit 1;
    if v_exists is null then return false; end if;
    delete from public.inventory_items where item_id = p_item_id and name = 'TEST_WORKER_INVENTORY_ITEM' and coalesce(source_row->>'test', 'false') = 'true';
    return true;
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_clean_worker_simulated_order(p_user_id uuid, p_order_file text DEFAULT 'TEST_WORKER_ORDER'::text)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
declare v_role text; v_order_id uuid;
begin
    select role into v_role from public.profiles where id = p_user_id and active = true limit 1;
    if v_role is distinct from 'admin' then raise exception 'Solo admin puede limpiar pedido simulado worker.'; end if;
    if p_order_file is distinct from 'TEST_WORKER_ORDER' then raise exception 'Esta RPC solo puede limpiar TEST_WORKER_ORDER.'; end if;
    select order_id into v_order_id from public.supplier_orders where order_file = p_order_file and coalesce(source_row->>'test', 'false') = 'true' limit 1;
    if v_order_id is null then return false; end if;
    delete from public.supplier_order_items where order_id = v_order_id;
    delete from public.supplier_orders where order_id = v_order_id;
    return true;
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_clean_worker_simulated_price_proposal(p_user_id uuid, p_item_woo_id bigint DEFAULT '-990001'::integer)
 RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
declare v_role text; v_deleted integer := 0;
begin
  select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
  if v_role <> 'admin' then raise exception 'Solo admin puede limpiar la propuesta de precio simulada'; end if;
  delete from public.price_change_proposals where item_woo_id = p_item_woo_id and item_kind = 'product'
    and (name = 'TEST_WORKER_PRICE_PROPOSAL' or source_row->>'test_name' = 'worker_simulated_price_proposal');
  get diagnostics v_deleted = row_count;
  return v_deleted > 0;
end;
$function$;

CREATE OR REPLACE FUNCTION public.futonhub_review_worker_simulated_price_proposal(p_user_id uuid, p_item_woo_id bigint DEFAULT '-990001'::integer, p_decision text DEFAULT 'approved'::text, p_operation_id text DEFAULT NULL::text)
 RETURNS SETOF price_change_proposals LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public' AS $function$
declare v_role text; v_decision text;
begin
  select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
  if v_role <> 'admin' then raise exception 'Solo admin puede revisar propuestas simuladas'; end if;
  v_decision := lower(trim(coalesce(p_decision, '')));
  if v_decision not in ('approved', 'rejected') then raise exception 'Decision invalida: %, use approved o rejected', p_decision; end if;
  return query
  update public.price_change_proposals p set status = v_decision, reviewed_by = auth.uid(), reviewed_at = now(),
    notes = coalesce(p.notes, '') || E'\n[TEST] Revision admin: ' || v_decision || '. No publicar en WooCommerce.',
    source_row = coalesce(p.source_row, '{}'::jsonb) || jsonb_build_object('review_test', true,'review_operation_id', p_operation_id,'review_decision', v_decision,'reviewed_by', auth.uid(),'reviewed_at', now())
  where p.item_woo_id = p_item_woo_id and p.item_kind = 'product' and (p.name = 'TEST_WORKER_PRICE_PROPOSAL' or p.source_row->>'test_name' = 'worker_simulated_price_proposal')
  returning p.*;
end;
$function$;

-- Permisos EXECUTE originales
grant execute on function public.futonhub_read_audit_logs(uuid,integer), public.futonhub_read_operation_snapshots(uuid,integer) to anon, authenticated, service_role;
grant execute on function public.futonhub_read_snapshot_by_operation_id(uuid,text),
  public.futonhub_clean_worker_simulated_inventory(uuid,bigint), public.futonhub_clean_worker_simulated_order(uuid,text),
  public.futonhub_clean_worker_simulated_price_proposal(uuid,bigint), public.futonhub_review_worker_simulated_price_proposal(uuid,bigint,text,text)
  to public, anon, authenticated, service_role;
commit;

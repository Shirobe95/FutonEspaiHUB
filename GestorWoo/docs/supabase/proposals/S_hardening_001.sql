-- =====================================================================================
-- PROPUESTA (NO APLICADA EN PRODUCCION) · S_hardening_001 · rama test/upgrade-001
-- Endurecimiento de seguridad de Supabase derivado de la auditoria 2026-10 (S1-S10).
-- Probada SOLO en un Postgres de laboratorio con el esquema vivo reconstruido.
-- Bloques independientes (A..F); cada uno se puede aplicar por separado. El bloque E es la guarda de integridad
-- de propuestas de precio (NO restringe quien aprueba/publica: los workers publican).
-- =====================================================================================
begin;

-- ---------- A. RPC de lectura/limpieza: identidad real (auth.uid) y sin acceso anon ----------
create or replace function public.futonhub_read_audit_logs(p_user_id uuid, p_limit integer default 50)
 returns table(id uuid, created_at timestamptz, operation_id text, user_email text, role text, machine_name text, module text, action text, severity text, status text, entity_type text, entity_id text, message text, error_detail text)
 language plpgsql security definer set search_path to 'public' as $function$
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid() then
    raise exception 'FutonHUB blackbox: usuario autenticado no coincide con p_user_id';
  end if;
  if not exists (select 1 from public.profiles p where p.id = auth.uid() and p.active = true and p.role = 'admin') then
    raise exception 'FutonHUB blackbox: solo admin puede leer audit_logs';
  end if;
  return query select a.id, a.created_at, a.operation_id, a.user_email, a.role, a.machine_name, a.module, a.action, a.severity, a.status, a.entity_type, a.entity_id, a.message, a.error_detail
  from public.audit_logs a order by a.created_at desc limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$function$;

create or replace function public.futonhub_read_operation_snapshots(p_user_id uuid, p_limit integer default 50)
 returns table(id uuid, created_at timestamptz, operation_id text, user_id uuid, module text, action text, entity_type text, entity_id text, before_data jsonb, reason text)
 language plpgsql security definer set search_path to 'public' as $function$
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid() then
    raise exception 'FutonHUB blackbox: usuario autenticado no coincide con p_user_id';
  end if;
  if not exists (select 1 from public.profiles p where p.id = auth.uid() and p.active = true and p.role = 'admin') then
    raise exception 'FutonHUB blackbox: solo admin puede leer operation_snapshots';
  end if;
  return query select s.id, s.created_at, s.operation_id, s.user_id, s.module, s.action, s.entity_type, s.entity_id, s.before_data, s.reason
  from public.operation_snapshots s order by s.created_at desc limit greatest(1, least(coalesce(p_limit, 50), 500));
end;
$function$;

create or replace function public.futonhub_clean_worker_simulated_inventory(p_user_id uuid, p_item_id bigint default '-900001'::integer)
 returns boolean language plpgsql security definer set search_path to 'public' as $function$
declare v_role text; v_exists bigint;
begin
    if auth.uid() is null or p_user_id is distinct from auth.uid() then raise exception 'Usuario autenticado no coincide con p_user_id'; end if;
    select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
    if v_role is distinct from 'admin' then raise exception 'Solo admin puede limpiar inventario simulado worker.'; end if;
    if p_item_id is distinct from -900001 then raise exception 'Esta RPC solo puede limpiar TEST_WORKER_INVENTORY_ITEM.'; end if;
    select item_id into v_exists from public.inventory_items
    where item_id = p_item_id and name = 'TEST_WORKER_INVENTORY_ITEM' and coalesce(source_row->>'test', 'false') = 'true' limit 1;
    if v_exists is null then return false; end if;
    delete from public.inventory_items where item_id = p_item_id and name = 'TEST_WORKER_INVENTORY_ITEM' and coalesce(source_row->>'test', 'false') = 'true';
    return true;
end;
$function$;

create or replace function public.futonhub_clean_worker_simulated_order(p_user_id uuid, p_order_file text default 'TEST_WORKER_ORDER'::text)
 returns boolean language plpgsql security definer set search_path to 'public' as $function$
declare v_role text; v_order_id uuid;
begin
    if auth.uid() is null or p_user_id is distinct from auth.uid() then raise exception 'Usuario autenticado no coincide con p_user_id'; end if;
    select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
    if v_role is distinct from 'admin' then raise exception 'Solo admin puede limpiar pedido simulado worker.'; end if;
    if p_order_file is distinct from 'TEST_WORKER_ORDER' then raise exception 'Esta RPC solo puede limpiar TEST_WORKER_ORDER.'; end if;
    select order_id into v_order_id from public.supplier_orders where order_file = p_order_file and coalesce(source_row->>'test', 'false') = 'true' limit 1;
    if v_order_id is null then return false; end if;
    delete from public.supplier_order_items where order_id = v_order_id;
    delete from public.supplier_orders where order_id = v_order_id;
    return true;
end;
$function$;

-- Las dos de propuestas simuladas comparaban `v_role <> 'admin'`: con v_role NULL (anon) la condicion era NULL y no lanzaba.
create or replace function public.futonhub_clean_worker_simulated_price_proposal(p_user_id uuid, p_item_woo_id bigint default '-990001'::integer)
 returns boolean language plpgsql security definer set search_path to 'public' as $function$
declare v_role text; v_deleted integer := 0;
begin
  if auth.uid() is null then raise exception 'Se requiere usuario autenticado'; end if;
  select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
  if v_role is distinct from 'admin' then raise exception 'Solo admin puede limpiar la propuesta de precio simulada'; end if;
  delete from public.price_change_proposals where item_woo_id = p_item_woo_id and item_kind = 'product'
    and (name = 'TEST_WORKER_PRICE_PROPOSAL' or source_row->>'test_name' = 'worker_simulated_price_proposal');
  get diagnostics v_deleted = row_count;
  return v_deleted > 0;
end;
$function$;

create or replace function public.futonhub_review_worker_simulated_price_proposal(p_user_id uuid, p_item_woo_id bigint default '-990001'::integer, p_decision text default 'approved'::text, p_operation_id text default null::text)
 returns setof price_change_proposals language plpgsql security definer set search_path to 'public' as $function$
declare v_role text; v_decision text;
begin
  if auth.uid() is null then raise exception 'Se requiere usuario autenticado'; end if;
  select role into v_role from public.profiles where id = auth.uid() and active = true limit 1;
  if v_role is distinct from 'admin' then raise exception 'Solo admin puede revisar propuestas simuladas'; end if;
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

revoke execute on function
  public.futonhub_read_audit_logs(uuid,integer), public.futonhub_read_operation_snapshots(uuid,integer),
  public.futonhub_read_snapshot_by_operation_id(uuid,text),
  public.futonhub_clean_worker_simulated_inventory(uuid,bigint), public.futonhub_clean_worker_simulated_order(uuid,text),
  public.futonhub_clean_worker_simulated_price_proposal(uuid,bigint),
  public.futonhub_review_worker_simulated_price_proposal(uuid,bigint,text,text)
  from public, anon;
grant execute on function
  public.futonhub_read_audit_logs(uuid,integer), public.futonhub_read_operation_snapshots(uuid,integer),
  public.futonhub_read_snapshot_by_operation_id(uuid,text),
  public.futonhub_clean_worker_simulated_inventory(uuid,bigint), public.futonhub_clean_worker_simulated_order(uuid,text),
  public.futonhub_clean_worker_simulated_price_proposal(uuid,bigint),
  public.futonhub_review_worker_simulated_price_proposal(uuid,bigint,text,text)
  to authenticated, service_role;

-- ---------- B. Caja negra: no se puede falsificar auditoria de otros usuarios ----------
drop policy if exists audit_logs_authenticated_insert on public.audit_logs;
create policy audit_logs_authenticated_insert on public.audit_logs for insert to authenticated
  with check (user_id = auth.uid() and is_worker_or_admin());
drop policy if exists operation_snapshots_authenticated_insert on public.operation_snapshots;
create policy operation_snapshots_authenticated_insert on public.operation_snapshots for insert to authenticated
  with check (user_id = auth.uid() and is_worker_or_admin());

-- ---------- C. Privilegios de tabla: anon sin acceso; nadie puede TRUNCATE/TRIGGER/REFERENCES ----------
revoke all on all tables in schema public from anon;
revoke truncate, references, trigger on all tables in schema public from authenticated;
alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public revoke truncate, references, trigger on tables from authenticated;

-- ---------- D. Vistas definer: anon ya no puede leerlas (cubierto por el REVOKE de C) ----------
-- NO se usa security_invoker: las vistas v_inventory_* leen inventory_item_components, que tiene RLS sin politicas
-- de lectura, de modo que con security_invoker la busqueda de componentes devolveria 0 filas tambien a los admin.

-- ---------- F. acquire_system_lock atomico para claves nuevas ----------
create or replace function public.futonhub_acquire_system_lock(p_operation_key text, p_user_id uuid, p_machine_name text, p_details text default ''::text, p_ttl_minutes integer default 15)
 returns jsonb language plpgsql security definer set search_path to 'public' as $function$
declare
  v_profile public.profiles%rowtype; v_now timestamptz := now(); v_expires timestamptz;
  v_existing public.system_locks%rowtype; v_inserted boolean := false;
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
  -- 1) Intento atomico de crear la fila: solo UNA sesion gana la carrera para una clave nueva.
  insert into public.system_locks(operation_key, locked_by, locked_by_machine, locked_at, expires_at, status, details)
  values (p_operation_key, v_profile.id, p_machine_name, v_now, v_expires, 'running', p_details)
  on conflict (operation_key) do nothing
  returning true into v_inserted;
  if coalesce(v_inserted, false) then
    return jsonb_build_object('acquired', true,'operation_key', p_operation_key,'locked_by', v_profile.id,
      'locked_by_machine', p_machine_name,'expires_at', v_expires,'details', p_details);
  end if;
  -- 2) La fila existe: se bloquea y se decide (running vigente => no adquirido; si no, se toma).
  select * into v_existing from public.system_locks where operation_key = p_operation_key for update;
  if v_existing.status = 'running' and v_existing.expires_at > v_now then
    return jsonb_build_object('acquired', false,'operation_key', v_existing.operation_key,'locked_by', v_existing.locked_by,
      'locked_by_machine', v_existing.locked_by_machine,'expires_at', v_existing.expires_at,'details', v_existing.details);
  end if;
  update public.system_locks set locked_by = v_profile.id, locked_by_machine = p_machine_name, locked_at = v_now,
    expires_at = v_expires, status = 'running', details = p_details where operation_key = p_operation_key;
  return jsonb_build_object('acquired', true,'operation_key', p_operation_key,'locked_by', v_profile.id,
    'locked_by_machine', p_machine_name,'expires_at', v_expires,'details', p_details);
end;
$function$;

-- ---------- E. Integridad de propuestas de precio (los workers SI pueden aprobar/publicar) ----------
-- Decision de negocio 2026-10-06: los workers publican precios. Este trigger NO restringe el flujo de estados; solo evita
--  (1) que alguien se atribuya la revision/publicacion de OTRO usuario (reviewed_by/published_by solo pueden ser auth.uid()), y
--  (2) que se modifique el precio/destino de una propuesta ya aprobada, en publicacion o publicada (lo aprobado es lo que se publica).
create or replace function public.price_change_proposals_guard() returns trigger
 language plpgsql security definer set search_path to 'public' as $function$
begin
  if public.is_admin() or auth.uid() is null then
    return new;  -- admin, o service_role/mantenimiento sin JWT de usuario
  end if;
  if new.reviewed_by is distinct from old.reviewed_by and new.reviewed_by is not null and new.reviewed_by <> auth.uid() then
    raise exception 'reviewed_by solo puede ser el usuario autenticado';
  end if;
  if new.published_by is distinct from old.published_by and new.published_by is not null and new.published_by <> auth.uid() then
    raise exception 'published_by solo puede ser el usuario autenticado';
  end if;
  if old.status in ('approved','publishing','published') and
     (new.new_price is distinct from old.new_price or new.old_price is distinct from old.old_price or new.item_woo_id is distinct from old.item_woo_id) then
    raise exception 'No se puede modificar el precio o el destino de una propuesta ya %', old.status;
  end if;
  return new;
end;
$function$;
drop trigger if exists price_change_proposals_guard on public.price_change_proposals;
create trigger price_change_proposals_guard before update on public.price_change_proposals
  for each row execute function public.price_change_proposals_guard();

commit;

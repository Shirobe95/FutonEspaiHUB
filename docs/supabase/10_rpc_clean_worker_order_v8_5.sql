-- FutonHUB v8.5 - RPC para limpiar pedido simulado worker
-- Ejecutar en Supabase > SQL Editor.
-- No afecta pedidos reales: solo borra supplier_orders con order_file = TEST_WORKER_ORDER.

create or replace function public.futonhub_clean_worker_simulated_order(
    p_user_id uuid,
    p_order_file text default 'TEST_WORKER_ORDER'
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    v_role text;
    v_order_id uuid;
begin
    select role into v_role
    from public.profiles
    where id = p_user_id
      and active = true
    limit 1;

    if v_role is distinct from 'admin' then
        raise exception 'Solo admin puede limpiar pedido simulado worker.';
    end if;

    if p_order_file is distinct from 'TEST_WORKER_ORDER' then
        raise exception 'Esta RPC solo puede limpiar TEST_WORKER_ORDER.';
    end if;

    select order_id into v_order_id
    from public.supplier_orders
    where order_file = p_order_file
      and coalesce(source_row->>'test', 'false') = 'true'
    limit 1;

    if v_order_id is null then
        return false;
    end if;

    delete from public.supplier_order_items where order_id = v_order_id;
    delete from public.supplier_orders where order_id = v_order_id;
    return true;
end;
$$;

grant execute on function public.futonhub_clean_worker_simulated_order(uuid, text) to authenticated;

-- Ajuste v8.5: los usuarios autenticados pueden crear pedidos operativos.
-- El control fino se hará en la app + logs/snapshots; WooCommerce sigue fuera.
drop policy if exists "supplier_orders_authenticated_insert" on public.supplier_orders;
create policy "supplier_orders_authenticated_insert"
on public.supplier_orders
for insert to authenticated
with check (true);

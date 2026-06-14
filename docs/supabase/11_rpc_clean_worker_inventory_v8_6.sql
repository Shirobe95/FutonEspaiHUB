-- FutonHUB v8.6 - RPC para limpiar inventario simulado worker
-- Ejecutar en Supabase > SQL Editor.
-- No afecta inventario real: solo borra inventory_items.item_id = -900001
-- si además está marcado como test en source_row.

create or replace function public.futonhub_clean_worker_simulated_inventory(
    p_user_id uuid,
    p_item_id bigint default -900001
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    v_role text;
    v_exists bigint;
begin
    select role into v_role
    from public.profiles
    where id = p_user_id
      and active = true
    limit 1;

    if v_role is distinct from 'admin' then
        raise exception 'Solo admin puede limpiar inventario simulado worker.';
    end if;

    if p_item_id is distinct from -900001 then
        raise exception 'Esta RPC solo puede limpiar TEST_WORKER_INVENTORY_ITEM.';
    end if;

    select item_id into v_exists
    from public.inventory_items
    where item_id = p_item_id
      and name = 'TEST_WORKER_INVENTORY_ITEM'
      and coalesce(source_row->>'test', 'false') = 'true'
    limit 1;

    if v_exists is null then
        return false;
    end if;

    delete from public.inventory_items
    where item_id = p_item_id
      and name = 'TEST_WORKER_INVENTORY_ITEM'
      and coalesce(source_row->>'test', 'false') = 'true';

    return true;
end;
$$;

grant execute on function public.futonhub_clean_worker_simulated_inventory(uuid, bigint) to authenticated;

-- Asegura que usuarios autenticados puedan crear/actualizar inventario operativo.
-- WooCommerce sigue fuera de esta fase.
drop policy if exists "inventory_authenticated_insert" on public.inventory_items;
create policy "inventory_authenticated_insert"
on public.inventory_items
for insert to authenticated
with check (true);

drop policy if exists "inventory_authenticated_update" on public.inventory_items;
create policy "inventory_authenticated_update"
on public.inventory_items
for update to authenticated
using (true)
with check (true);

-- =====================================================
-- FutonHUB v8.7 · Limpieza admin de propuesta de precio simulada
-- =====================================================
-- Ejecutar en Supabase SQL Editor.
-- Permite limpiar TEST_WORKER_PRICE_PROPOSAL sin dar DELETE general a workers.

create or replace function public.futonhub_clean_worker_simulated_price_proposal(
  p_user_id uuid,
  p_item_woo_id bigint default -990001
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_role text;
  v_deleted integer := 0;
begin
  select role into v_role
  from public.profiles
  where id = auth.uid()
    and active = true
  limit 1;

  if v_role <> 'admin' then
    raise exception 'Solo admin puede limpiar la propuesta de precio simulada';
  end if;

  delete from public.price_change_proposals
  where item_woo_id = p_item_woo_id
    and item_kind = 'product'
    and (
      name = 'TEST_WORKER_PRICE_PROPOSAL'
      or source_row->>'test_name' = 'worker_simulated_price_proposal'
    );

  get diagnostics v_deleted = row_count;
  return v_deleted > 0;
end;
$$;

grant execute on function public.futonhub_clean_worker_simulated_price_proposal(uuid, bigint) to authenticated;

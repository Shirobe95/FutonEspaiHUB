-- =====================================================
-- FutonHUB v8.9 · Revisión admin de propuesta simulada worker
-- =====================================================
-- Ejecutar en Supabase SQL Editor.
-- Permite aprobar/rechazar TEST_WORKER_PRICE_PROPOSAL sin publicar en WooCommerce.

create or replace function public.futonhub_review_worker_simulated_price_proposal(
  p_user_id uuid,
  p_item_woo_id bigint default -990001,
  p_decision text default 'approved',
  p_operation_id text default null
)
returns setof public.price_change_proposals
language plpgsql
security definer
set search_path = public
as $$
declare
  v_role text;
  v_decision text;
begin
  select role into v_role
  from public.profiles
  where id = auth.uid()
    and active = true
  limit 1;

  if v_role <> 'admin' then
    raise exception 'Solo admin puede revisar propuestas simuladas';
  end if;

  v_decision := lower(trim(coalesce(p_decision, '')));
  if v_decision not in ('approved', 'rejected') then
    raise exception 'Decision invalida: %, use approved o rejected', p_decision;
  end if;

  return query
  update public.price_change_proposals p
  set
    status = v_decision,
    reviewed_by = auth.uid(),
    reviewed_at = now(),
    notes = coalesce(p.notes, '') || E'\n[TEST] Revision admin: ' || v_decision || '. No publicar en WooCommerce.',
    source_row = coalesce(p.source_row, '{}'::jsonb) || jsonb_build_object(
      'review_test', true,
      'review_operation_id', p_operation_id,
      'review_decision', v_decision,
      'reviewed_by', auth.uid(),
      'reviewed_at', now()
    )
  where p.item_woo_id = p_item_woo_id
    and p.item_kind = 'product'
    and (
      p.name = 'TEST_WORKER_PRICE_PROPOSAL'
      or p.source_row->>'test_name' = 'worker_simulated_price_proposal'
    )
  returning p.*;
end;
$$;

grant execute on function public.futonhub_review_worker_simulated_price_proposal(uuid, bigint, text, text) to authenticated;

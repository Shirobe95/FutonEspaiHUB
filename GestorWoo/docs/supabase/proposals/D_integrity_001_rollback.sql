begin;
drop policy if exists supplier_order_items_worker_admin_delete on public.supplier_order_items;
commit;

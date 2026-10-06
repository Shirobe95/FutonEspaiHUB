-- =====================================================================================
-- PROPUESTA (NO APLICADA EN PRODUCCION) · D_integrity_001 · rama test/upgrade-001
-- supplier_order_items no tiene politica DELETE: al editar un borrador de pedido el ERP borra las lineas
-- sobrantes, PostgREST devuelve 0 filas SIN error (RLS), y el codigo cree que borro. Resultado verificado
-- en la auditoria: lineas "fantasma" que reaparecen con datos viejos al reabrir el pedido.
-- Esta politica permite borrar lineas a worker/admin, igual que ya pueden insertarlas y actualizarlas.
-- (La atomicidad de receive_supplier_order y los duplicados historicos requieren cambios de aplicacion/RPC: aparte.)
-- =====================================================================================
begin;
drop policy if exists supplier_order_items_worker_admin_delete on public.supplier_order_items;
create policy supplier_order_items_worker_admin_delete on public.supplier_order_items
  for delete to authenticated using (is_worker_or_admin());
commit;

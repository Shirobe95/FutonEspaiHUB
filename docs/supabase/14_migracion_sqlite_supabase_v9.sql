-- FutonHUB v9 - Preparación migración SQLite → Supabase
-- Ejecutar antes de migrate-sqlite-to-supabase-execute.
-- No toca WooCommerce. Solo prepara columnas de trazabilidad para upsert seguro.

alter table public.price_change_proposals
  add column if not exists local_sqlite_id bigint;

-- PostgREST/Supabase necesita un índice único NO parcial para usar on_conflict=local_sqlite_id.
-- Los NULL no chocan entre sí en PostgreSQL, así que las propuestas de test sin id local siguen permitidas.
create unique index if not exists idx_price_change_proposals_local_sqlite_id
on public.price_change_proposals(local_sqlite_id);

alter table public.supplier_order_items
  add column if not exists local_item_id bigint;

-- Necesario para futuras migraciones de pedidos si existen filas locales.
create unique index if not exists idx_supplier_orders_local_order_id
on public.supplier_orders(local_order_id);


create unique index if not exists idx_supplier_order_items_local_item_id
on public.supplier_order_items(local_item_id);

-- Refuerzo de permisos de migración: solo admin escribe products/variations.
-- Las tablas operativas de tienda siguen con sus políticas v7.
insert into public.role_permissions(role, module, can_view, can_create, can_update, can_delete, can_execute) values
('admin','sqlite_migration',true,true,true,true,true),
('worker','sqlite_migration',false,false,false,false,false)
on conflict(role, module) do update set
  can_view = excluded.can_view,
  can_create = excluded.can_create,
  can_update = excluded.can_update,
  can_delete = excluded.can_delete,
  can_execute = excluded.can_execute;

-- FutonHUB v9.1 - Fix ON CONFLICT migración SQLite → Supabase
-- Ejecutar si la migración falló en price_change_proposals con:
-- there is no unique or exclusion constraint matching the ON CONFLICT specification
--
-- Motivo: el índice único v9 era parcial (WHERE local_sqlite_id IS NOT NULL)
-- y PostgREST no lo acepta para on_conflict. Este script crea índices únicos NO parciales.

alter table public.price_change_proposals
  add column if not exists local_sqlite_id bigint;

-- Si existe el índice parcial anterior, lo eliminamos y lo recreamos como índice único no parcial.
drop index if exists public.idx_price_change_proposals_local_sqlite_id;
create unique index idx_price_change_proposals_local_sqlite_id
on public.price_change_proposals(local_sqlite_id);

alter table public.supplier_orders
  add column if not exists local_order_id bigint;

drop index if exists public.idx_supplier_orders_local_order_id;
create unique index idx_supplier_orders_local_order_id
on public.supplier_orders(local_order_id);

alter table public.supplier_order_items
  add column if not exists local_item_id bigint;

drop index if exists public.idx_supplier_order_items_local_item_id;
create unique index idx_supplier_order_items_local_item_id
on public.supplier_order_items(local_item_id);

-- Comprobación rápida
select
  schemaname,
  tablename,
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and indexname in (
    'idx_price_change_proposals_local_sqlite_id',
    'idx_supplier_orders_local_order_id',
    'idx_supplier_order_items_local_item_id'
  )
order by tablename, indexname;

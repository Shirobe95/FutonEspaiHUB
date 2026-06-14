-- =====================================================
-- FutonHUB v11.5
-- Fix columnas publicación WooCommerce protegida
-- =====================================================
-- Motivo:
-- v11.4 intentaba marcar price_change_proposals.published_by,
-- pero algunos proyectos Supabase tenían la tabla creada sin esa columna.
-- Este script añade la columna y fuerza recarga del schema cache de PostgREST.

alter table public.price_change_proposals
  add column if not exists published_by uuid references public.profiles(id) on delete set null;

alter table public.price_change_proposals
  add column if not exists published_at timestamptz;

create index if not exists idx_price_change_proposals_published_by
  on public.price_change_proposals(published_by);

create index if not exists idx_price_change_proposals_status_published_at
  on public.price_change_proposals(status, published_at desc);

-- Forzar recarga del schema cache usado por la API REST de Supabase/PostgREST.
notify pgrst, 'reload schema';

-- Comprobación rápida:
select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'price_change_proposals'
  and column_name in ('published_by', 'published_at')
order by column_name;

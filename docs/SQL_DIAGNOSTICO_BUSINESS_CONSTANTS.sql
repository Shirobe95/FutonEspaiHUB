-- Diagnóstico Supabase para business_constants
-- Ejecutar en Supabase SQL Editor.

select
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'business_constants'
order by ordinal_position;

select
  con.conname as constraint_name,
  con.contype as constraint_type,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = con.connamespace
where nsp.nspname = 'public'
  and rel.relname = 'business_constants'
order by con.conname;

select *
from public.business_constants
order by key
limit 50;

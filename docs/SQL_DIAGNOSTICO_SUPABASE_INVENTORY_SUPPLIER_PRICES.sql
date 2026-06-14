-- Diagnóstico Supabase para inventory_items y precios proveedor
-- Ejecutar en Supabase SQL Editor.

-- 1) Columnas de inventory_items
select
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'inventory_items'
order by ordinal_position;

-- 2) Columnas de supplier_prices, si existe todavía
select
  column_name,
  data_type,
  is_nullable,
  column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'supplier_prices'
order by ordinal_position;

-- 3) Restricciones de inventory_items
select
  con.conname as constraint_name,
  con.contype as constraint_type,
  pg_get_constraintdef(con.oid) as definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = con.connamespace
where nsp.nspname = 'public'
  and rel.relname = 'inventory_items'
order by con.conname;

-- 4) Conteo de precios proveedor ya presentes
select
  count(*) as total_items,
  count(primary_supplier_price) as with_primary_supplier_price,
  count(pascal_price) as with_pascal_price
from public.inventory_items;

-- 5) Ejemplos con precio principal o Pascal
select
  item_id,
  name,
  primary_supplier_price,
  pascal_price,
  family,
  subgroup
from public.inventory_items
where primary_supplier_price is not null
   or pascal_price is not null
order by item_id
limit 50;

-- 6) Items concretos que suelen venir de doble proveedor en SQLite
select
  item_id,
  name,
  primary_supplier_price,
  pascal_price
from public.inventory_items
where item_id in (606001,606002,606003,606004,606005,402010,402012)
order by item_id;

-- 7) Ver si existen IDs concretos en inventory_items
select x.item_id, ii.item_id is not null as exists_in_inventory
from unnest(array[606001,606002,606003,402010,402012]::bigint[]) as x(item_id)
left join public.inventory_items ii on ii.item_id = x.item_id
order by x.item_id;

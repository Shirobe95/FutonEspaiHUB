-- FutonHUB v7 - Modelo operativo online
-- Ejecutar en Supabase > SQL Editor después de v4/v5/v6.
-- Objetivo: workers operativos completos de tienda + admin con sala de máquinas.
-- No toca WooCommerce. Prepara tablas online y prueba segura con constantes.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- 1) Permisos reales de trabajo
-- ---------------------------------------------------------------------------
-- Los workers pueden trabajar en tienda: inventario, pedidos, propuestas,
-- costes, productos y constantes operativas.
-- No ven sala de máquinas: logs, snapshots, backups, restore, usuarios,
-- settings, locks, migraciones, publicación crítica WooCommerce.

insert into public.role_permissions(role, module, can_view, can_create, can_update, can_delete, can_execute) values
('admin','products',true,true,true,true,true),
('admin','product_variations',true,true,true,true,true),
('admin','inventory',true,true,true,true,true),
('admin','supplier_prices',true,true,true,true,true),
('admin','heca_stock',true,true,true,true,true),
('admin','price_proposals',true,true,true,true,true),
('admin','orders',true,true,true,true,true),
('admin','orders_cost',true,true,true,true,true),
('admin','cost',true,true,true,true,true),
('admin','cost_pedido',true,true,true,true,true),
('admin','business_constants',true,true,true,true,true),
('admin','woocommerce',true,true,true,true,true),
('admin','woocommerce_publish',true,true,true,false,true),
('admin','logs',true,true,true,true,true),
('admin','snapshots',true,true,true,true,true),
('admin','backups',true,true,true,true,true),
('admin','restore',true,true,true,true,true),
('admin','security',true,true,true,true,true),
('admin','diagnostics',true,true,true,true,true),
('admin','settings',true,true,true,true,true),
('admin','users',true,true,true,true,true),
('admin','locks',true,true,true,true,true),
('admin','migrations',true,true,true,true,true),

('worker','products',true,false,false,false,true),
('worker','product_variations',true,false,false,false,true),
('worker','inventory',true,true,true,false,true),
('worker','supplier_prices',true,true,true,false,true),
('worker','heca_stock',true,true,true,false,true),
('worker','price_proposals',true,true,true,false,true),
('worker','orders',true,true,true,false,true),
('worker','orders_cost',true,true,true,false,true),
('worker','cost',true,true,true,false,true),
('worker','cost_pedido',true,true,true,false,true),
('worker','business_constants',true,true,true,false,true),
('worker','woocommerce',true,false,false,false,true),
('worker','woocommerce_publish',false,false,false,false,false),
('worker','logs',false,false,false,false,false),
('worker','snapshots',false,false,false,false,false),
('worker','backups',false,false,false,false,false),
('worker','restore',false,false,false,false,false),
('worker','security',false,false,false,false,false),
('worker','diagnostics',false,false,false,false,false),
('worker','settings',false,false,false,false,false),
('worker','users',false,false,false,false,false),
('worker','locks',false,false,false,false,false),
('worker','migrations',false,false,false,false,false)
on conflict(role, module) do update set
    can_view = excluded.can_view,
    can_create = excluded.can_create,
    can_update = excluded.can_update,
    can_delete = excluded.can_delete,
    can_execute = excluded.can_execute;

-- ---------------------------------------------------------------------------
-- 2) Tablas operativas cloud
-- ---------------------------------------------------------------------------

create table if not exists public.products (
    woo_id bigint primary key,
    name text not null,
    sku text,
    type text,
    status text,
    regular_price text,
    sale_price text,
    price text,
    stock_status text,
    stock_quantity numeric,
    categories_json jsonb not null default '[]'::jsonb,
    raw_json jsonb not null default '{}'::jsonb,
    synced_at timestamptz,
    updated_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null
);

create table if not exists public.product_variations (
    woo_id bigint primary key,
    parent_woo_id bigint not null,
    parent_name text not null,
    sku text,
    status text,
    regular_price text,
    sale_price text,
    price text,
    stock_status text,
    stock_quantity numeric,
    attributes_json jsonb not null default '[]'::jsonb,
    attributes_label text,
    raw_json jsonb not null default '{}'::jsonb,
    synced_at timestamptz,
    updated_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null
);

create table if not exists public.inventory_items (
    item_id bigint primary key,
    name text not null,
    cubic_meters numeric,
    rotation_c numeric,
    packages integer,
    primary_supplier_price text,
    pascal_price text,
    source text,
    family text,
    subgroup text,
    size text,
    materials text,
    commercial_status text default 'Normal',
    is_pack boolean not null default false,
    store_stock numeric,
    warehouse_stock numeric,
    heca_reference text,
    notes text,
    woo_item_kind text,
    woo_id bigint,
    woo_parent_id bigint,
    woo_sku text,
    woo_name text,
    woo_type text,
    woo_price text,
    woo_categories text,
    woo_link_status text default 'Sin enlazar',
    woo_link_notes text,
    woo_synced_at timestamptz,
    order_calculated_price numeric,
    supplier_order_qty numeric,
    supplier_order_provider text,
    supplier_order_file text,
    supplier_order_updated_at timestamptz,
    weighted_average_cost numeric,
    weighted_average_cost_updated_at timestamptz,
    source_row jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null
);

create table if not exists public.supplier_prices (
    item_id bigint not null,
    supplier text not null,
    price text,
    currency text default 'EUR',
    source text,
    updated_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null,
    primary key(item_id, supplier)
);

create table if not exists public.heca_stock (
    normalized_code text not null,
    warehouse_code integer not null,
    item_code text not null,
    quantity numeric default 0,
    quantity_requested numeric default 0,
    quantity_reserved numeric default 0,
    quantity_supplier_ordered numeric default 0,
    imported_at timestamptz not null default now(),
    updated_by uuid references public.profiles(id) on delete set null,
    primary key(normalized_code, warehouse_code)
);

create table if not exists public.price_change_proposals (
    id uuid primary key default gen_random_uuid(),
    local_id bigint,
    item_kind text not null,
    item_woo_id bigint not null,
    name text not null,
    old_price numeric,
    new_price numeric,
    delta numeric,
    notes text,
    status text not null default 'pending' check (status in ('pending','approved','rejected','published','error','cancelled')),
    created_by uuid references public.profiles(id) on delete set null,
    reviewed_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    published_at timestamptz,
    error_message text,
    source_row jsonb not null default '{}'::jsonb
);

create table if not exists public.supplier_orders (
    order_id uuid primary key default gen_random_uuid(),
    local_order_id bigint,
    provider text not null,
    order_file text,
    status text not null default 'Pendiente',
    total_items numeric default 0,
    total_cost numeric default 0,
    notes text,
    created_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    source_row jsonb not null default '{}'::jsonb
);

create table if not exists public.supplier_order_items (
    id uuid primary key default gen_random_uuid(),
    order_id uuid references public.supplier_orders(order_id) on delete cascade,
    local_id bigint,
    item_id bigint,
    item_code text,
    item_name text,
    quantity_ordered numeric default 0,
    quantity_received numeric default 0,
    unit_cost numeric default 0,
    line_cost numeric default 0,
    updated_at timestamptz not null default now(),
    source_row jsonb not null default '{}'::jsonb
);

create table if not exists public.business_constants (
    key text primary key,
    value jsonb not null,
    value_type text not null default 'number',
    module text not null default 'cost',
    description text,
    updated_by uuid references public.profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Semilla inicial de constantes. No pisa valores existentes.
insert into public.business_constants(key, value, value_type, module, description) values
('IMPORTE_DESCARGA_MT', '250'::jsonb, 'number', 'cost_pedido', 'Importe de descarga por metro.'),
('PC_GASTOS_MANIPULACION', '7'::jsonb, 'number', 'cost_pedido', 'Porcentaje de gastos de manipulación.'),
('PC_GASTOS_FINANCIACION', '7'::jsonb, 'number', 'cost_pedido', 'Porcentaje de gastos de financiación.'),
('IMPORTES_VARIOS', '100'::jsonb, 'number', 'cost_pedido', 'Importes varios de cálculo.'),
('COSTE_TOTAL_DESCARGA_FUTONES_IVA', '302.5'::jsonb, 'number', 'cost_pedido', 'Coste total de descarga de futones con IVA.'),
('COSTE_DESCARGA_FUTONES_UNIDAD', '1.69'::jsonb, 'number', 'cost_pedido', 'Coste de descarga por unidad de futón.'),
('IVA_RECARGO_EQUIVALENCIA', '0.262'::jsonb, 'number', 'cost_pedido', 'IVA + recargo equivalencia.'),
('COSTE_DIARIO_ALMACENAJE_M3', '0.3743'::jsonb, 'number', 'cost_pedido', 'Coste diario de almacenaje por m3.')
on conflict(key) do nothing;

-- ---------------------------------------------------------------------------
-- 3) RLS operativo
-- ---------------------------------------------------------------------------

alter table public.products enable row level security;
alter table public.product_variations enable row level security;
alter table public.inventory_items enable row level security;
alter table public.supplier_prices enable row level security;
alter table public.heca_stock enable row level security;
alter table public.price_change_proposals enable row level security;
alter table public.supplier_orders enable row level security;
alter table public.supplier_order_items enable row level security;
alter table public.business_constants enable row level security;

-- Re-ejecutable: limpiamos políticas v7 si existen.
drop policy if exists "products_authenticated_read" on public.products;
drop policy if exists "products_admin_write" on public.products;
drop policy if exists "variations_authenticated_read" on public.product_variations;
drop policy if exists "variations_admin_write" on public.product_variations;
drop policy if exists "inventory_authenticated_read" on public.inventory_items;
drop policy if exists "inventory_authenticated_write" on public.inventory_items;
drop policy if exists "supplier_prices_authenticated_read" on public.supplier_prices;
drop policy if exists "supplier_prices_authenticated_write" on public.supplier_prices;
drop policy if exists "heca_stock_authenticated_read" on public.heca_stock;
drop policy if exists "heca_stock_authenticated_write" on public.heca_stock;
drop policy if exists "price_proposals_authenticated_read" on public.price_change_proposals;
drop policy if exists "price_proposals_authenticated_write" on public.price_change_proposals;
drop policy if exists "supplier_orders_authenticated_read" on public.supplier_orders;
drop policy if exists "supplier_orders_authenticated_write" on public.supplier_orders;
drop policy if exists "supplier_order_items_authenticated_read" on public.supplier_order_items;
drop policy if exists "supplier_order_items_authenticated_write" on public.supplier_order_items;
drop policy if exists "business_constants_authenticated_read" on public.business_constants;
drop policy if exists "business_constants_authenticated_write" on public.business_constants;
drop policy if exists "business_constants_admin_delete" on public.business_constants;

drop policy if exists "inventory_authenticated_insert" on public.inventory_items;
drop policy if exists "inventory_authenticated_update" on public.inventory_items;
drop policy if exists "supplier_prices_authenticated_insert" on public.supplier_prices;
drop policy if exists "supplier_prices_authenticated_update" on public.supplier_prices;
drop policy if exists "heca_stock_authenticated_insert" on public.heca_stock;
drop policy if exists "heca_stock_authenticated_update" on public.heca_stock;
drop policy if exists "price_proposals_authenticated_insert" on public.price_change_proposals;
drop policy if exists "price_proposals_authenticated_update" on public.price_change_proposals;
drop policy if exists "supplier_orders_authenticated_insert" on public.supplier_orders;
drop policy if exists "supplier_orders_authenticated_update" on public.supplier_orders;
drop policy if exists "supplier_order_items_authenticated_insert" on public.supplier_order_items;
drop policy if exists "supplier_order_items_authenticated_update" on public.supplier_order_items;
drop policy if exists "business_constants_authenticated_insert" on public.business_constants;
drop policy if exists "business_constants_authenticated_update" on public.business_constants;

create policy "products_authenticated_read" on public.products
for select to authenticated
using (true);

create policy "products_admin_write" on public.products
for all to authenticated
using (public.is_admin())
with check (public.is_admin());

create policy "variations_authenticated_read" on public.product_variations
for select to authenticated
using (true);

create policy "variations_admin_write" on public.product_variations
for all to authenticated
using (public.is_admin())
with check (public.is_admin());

create policy "inventory_authenticated_read" on public.inventory_items
for select to authenticated
using (true);

create policy "inventory_authenticated_insert" on public.inventory_items
for insert to authenticated
with check (true);

create policy "inventory_authenticated_update" on public.inventory_items
for update to authenticated
using (true)
with check (true);

create policy "supplier_prices_authenticated_read" on public.supplier_prices
for select to authenticated
using (true);

create policy "supplier_prices_authenticated_insert" on public.supplier_prices
for insert to authenticated
with check (true);

create policy "supplier_prices_authenticated_update" on public.supplier_prices
for update to authenticated
using (true)
with check (true);

create policy "heca_stock_authenticated_read" on public.heca_stock
for select to authenticated
using (true);

create policy "heca_stock_authenticated_insert" on public.heca_stock
for insert to authenticated
with check (true);

create policy "heca_stock_authenticated_update" on public.heca_stock
for update to authenticated
using (true)
with check (true);

create policy "price_proposals_authenticated_read" on public.price_change_proposals
for select to authenticated
using (true);

create policy "price_proposals_authenticated_insert" on public.price_change_proposals
for insert to authenticated
with check (created_by = auth.uid() or public.is_admin());

create policy "price_proposals_authenticated_update" on public.price_change_proposals
for update to authenticated
using (true)
with check (true);

create policy "supplier_orders_authenticated_read" on public.supplier_orders
for select to authenticated
using (true);

create policy "supplier_orders_authenticated_insert" on public.supplier_orders
for insert to authenticated
with check (created_by = auth.uid() or public.is_admin());

create policy "supplier_orders_authenticated_update" on public.supplier_orders
for update to authenticated
using (true)
with check (true);

create policy "supplier_order_items_authenticated_read" on public.supplier_order_items
for select to authenticated
using (true);

create policy "supplier_order_items_authenticated_insert" on public.supplier_order_items
for insert to authenticated
with check (true);

create policy "supplier_order_items_authenticated_update" on public.supplier_order_items
for update to authenticated
using (true)
with check (true);

create policy "business_constants_authenticated_read" on public.business_constants
for select to authenticated
using (true);

create policy "business_constants_authenticated_insert" on public.business_constants
for insert to authenticated
with check (true);

create policy "business_constants_authenticated_update" on public.business_constants
for update to authenticated
using (true)
with check (true);

create policy "business_constants_admin_delete" on public.business_constants
for delete to authenticated
using (public.is_admin());

-- Índices útiles para el futuro migrador/sincronización.
create index if not exists idx_inventory_items_woo_id on public.inventory_items(woo_id);
create index if not exists idx_price_change_proposals_status on public.price_change_proposals(status);
create index if not exists idx_supplier_orders_provider_status on public.supplier_orders(provider, status);
create index if not exists idx_audit_logs_operation_id on public.audit_logs(operation_id);
create index if not exists idx_operation_snapshots_operation_id on public.operation_snapshots(operation_id);

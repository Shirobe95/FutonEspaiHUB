-- v12 - Permisos operativos para revisión de propuestas
-- Admin y worker pueden aprobar/rechazar propuestas internas.
-- Publicar en WooCommerce sigue protegido por la app: solo admin.

insert into public.role_permissions
(role, module, can_view, can_create, can_update, can_delete, can_execute)
values
('worker', 'price_proposals_review', true, true, true, false, true),
('admin', 'price_proposals_review', true, true, true, true, true),
('admin', 'woocommerce_publish', true, false, true, false, true),
('worker', 'woocommerce_publish', false, false, false, false, false)
on conflict do nothing;

-- Si la política RLS de price_change_proposals fue endurecida en alguna prueba,
-- deja lectura y actualización operativa para usuarios autenticados.
-- La app sigue bloqueando publicación WooCommerce solo para admin.
drop policy if exists "price_change_proposals_authenticated_select" on public.price_change_proposals;
drop policy if exists "price_change_proposals_authenticated_insert" on public.price_change_proposals;
drop policy if exists "price_change_proposals_authenticated_update" on public.price_change_proposals;

create policy "price_change_proposals_authenticated_select"
on public.price_change_proposals
for select
to authenticated
using (true);

create policy "price_change_proposals_authenticated_insert"
on public.price_change_proposals
for insert
to authenticated
with check (true);

create policy "price_change_proposals_authenticated_update"
on public.price_change_proposals
for update
to authenticated
using (true)
with check (true);

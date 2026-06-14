-- FutonHUB: registrar un worker después de crearlo en Supabase Auth.
-- Repite este bloque para cada worker. Máximo recomendado inicial: 3 workers.

insert into public.profiles(id, email, display_name, role, active)
values (
    'PEGA_AQUI_UUID_WORKER',
    'worker@futonespai.com',
    'Worker Tienda',
    'worker',
    true
)
on conflict(id) do update set
    email = excluded.email,
    display_name = excluded.display_name,
    role = 'worker',
    active = true,
    updated_at = now();

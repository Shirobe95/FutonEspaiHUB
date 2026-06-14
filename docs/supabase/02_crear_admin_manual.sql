-- FutonHUB: convertir tu usuario Supabase Auth en admin.
-- 1) En Supabase > Authentication > Users crea tu usuario con email/password.
-- 2) Copia el UUID del usuario.
-- 3) Sustituye los valores de abajo y ejecuta este SQL.

insert into public.profiles(id, email, display_name, role, active)
values (
    'PEGA_AQUI_TU_UUID_DE_AUTH_USERS',
    'tu-email@ejemplo.com',
    'Andy',
    'admin',
    true
)
on conflict(id) do update set
    email = excluded.email,
    display_name = excluded.display_name,
    role = 'admin',
    active = true,
    updated_at = now();

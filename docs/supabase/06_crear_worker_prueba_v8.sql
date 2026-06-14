-- FutonHUB v8 - Crear/actualizar perfil worker de prueba
-- 1) Crea primero el usuario en Supabase > Authentication > Users.
-- 2) Copia el UUID del usuario.
-- 3) Sustituye los valores marcados abajo y ejecuta este SQL.

insert into public.profiles (
  id,
  email,
  display_name,
  role,
  active
)
values (
  'PEGAR_UUID_AUTH_USER_AQUI',
  'worker.prueba@futonespai.com',
  'Worker Prueba',
  'worker',
  true
)
on conflict (id) do update set
  email = excluded.email,
  display_name = excluded.display_name,
  role = excluded.role,
  active = excluded.active;

-- Comprobación rápida:
select id, email, display_name, role, active
from public.profiles
where role = 'worker'
order by created_at desc;

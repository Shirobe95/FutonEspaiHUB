-- FutonHUB v5 opcional: evitar duplicar registro de dispositivo por usuario/máquina.
-- Ejecutar en Supabase SQL Editor si quieres que cada login actualice el mismo dispositivo.

create unique index if not exists devices_user_machine_unique
on public.devices(user_id, machine_name)
where user_id is not null;

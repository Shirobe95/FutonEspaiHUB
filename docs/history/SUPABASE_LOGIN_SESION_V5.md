# FutonHUB v5 - Login Supabase y lectura RLS autenticada

Esta versión mantiene el modo local estable y añade la primera capa real de sesión online.

## Por qué `cloud-diagnostic` veía 0 filas

Supabase tiene Row Level Security activado. Con `SUPABASE_ANON_KEY` pero sin login, el cliente puede conectar y confirmar que las tablas existen, pero las políticas RLS pueden ocultar las filas.

Eso significa que esto puede ser normal:

```txt
profiles: OK · filas visibles: 0
role_permissions: OK · filas visibles: 0
Auth local: sin sesión activa
```

Para lectura real hay que iniciar sesión con Supabase Auth.

## Nuevo comando recomendado

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-login-diagnostic
```

El comando pide la contraseña de Supabase por consola, no la guarda, inicia sesión y vuelve a leer las tablas con `auth.uid()` activo.

Resultado esperado para admin:

```txt
Estado conexión: cliente creado + login OK
Auth local: sesión activa · andyshb95@gmail.com · rol cloud: admin
profiles: OK · filas visibles: 1
role_permissions: OK · filas visibles: ...
PERFIL ACTUAL
role: admin
```

## Login visual en el HUB

El HUB ahora incluye botón:

```txt
Login Supabase
```

Al pulsarlo pide la contraseña del usuario configurado en `.env`:

```env
GESTORWOO_USER_EMAIL=andyshb95@gmail.com
```

No se guarda la contraseña. La sesión vive en memoria durante la ejecución actual.

## Seguridad

- Los workers no deben ver logs ni backups.
- Las políticas RLS siguen siendo la defensa principal.
- La `SUPABASE_SERVICE_ROLE_KEY` no es necesaria para esta fase y no debe compartirse.
- El `.env` funcional se conserva para comodidad, pero es privado.

## Nuevos archivos

```txt
GestorWoo/src/gestorwoo/cloud/auth.py
scripts/diagnostico_supabase_login.bat
SUPABASE_LOGIN_SESION_V5.md
```

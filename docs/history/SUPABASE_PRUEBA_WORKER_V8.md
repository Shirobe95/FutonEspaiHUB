# FutonHUB v8 - Prueba real con usuario Worker

Objetivo: comprobar que un worker puede hacer trabajo operativo y que el admin puede ver el rastro completo en Supabase.

La prueba usa solo `business_constants` con la clave `TEST_WORKER_FEEDBACK`. No toca inventario real, pedidos reales ni WooCommerce.

## 1. Crear usuario worker en Supabase

En Supabase:

1. Ve a **Authentication > Users**.
2. Crea un usuario de prueba, por ejemplo `worker.prueba@futonespai.com`.
3. Guarda la contraseña temporal.
4. Copia el **User UID**.

Luego ejecuta en SQL Editor:

```txt
/docs/supabase/06_crear_worker_prueba_v8.sql
```

Sustituye antes:

```txt
PEGAR_UUID_AUTH_USER_AQUI
worker.prueba@futonespai.com
Worker Prueba
```

## 2. Prueba desde consola como worker

Desde `GestorWoo`:

```powershell
python gestorwoo.py cloud-worker-feedback-test
```

Cuando pregunte email, escribe el email del worker. Si aparece el email admin como valor por defecto, escribe encima el del worker.

Resultado esperado:

```txt
Prueba worker real creada/actualizada correctamente.
operation_id: WORKERTEST-...
Tabla: business_constants
Clave: TEST_WORKER_FEEDBACK
```

## 3. Prueba desde el HUB visual

1. Abre el HUB.
2. Pulsa **Login Supabase**.
3. Escribe el email y contraseña del worker.
4. Pulsa **Test worker**.

El worker no necesita ver logs ni snapshots. Solo debe ver que la operación fue correcta.

## 4. Verificación admin

Cierra sesión reiniciando el HUB o vuelve a entrar con usuario admin.

Como admin, revisa:

```powershell
python gestorwoo.py cloud-logs --limit 20
python gestorwoo.py cloud-snapshots --limit 20
```

O desde el HUB:

- **Logs cloud**
- **Snapshots cloud**

Debe aparecer una operación parecida a:

```txt
module: business_constants
action: worker_feedback_create_constant / worker_feedback_update_constant
entity_id: TEST_WORKER_FEEDBACK
user_email: worker.prueba@futonespai.com
```

En Supabase también puedes comprobar:

```sql
select key, value, module, description, updated_by, updated_at
from public.business_constants
where key = 'TEST_WORKER_FEEDBACK';

select created_at, operation_id, user_email, role, machine_name, module, action, entity_id, message
from public.audit_logs
where entity_id = 'TEST_WORKER_FEEDBACK'
order by created_at desc;

select created_at, operation_id, module, action, entity_id, reason
from public.operation_snapshots
where entity_id = 'TEST_WORKER_FEEDBACK'
order by created_at desc;
```

La primera vez puede no haber snapshot si la constante no existía. La segunda vez sí debe generarse snapshot porque ya hay estado previo.

## 5. Limpiar prueba

Como admin:

```powershell
python gestorwoo.py cloud-clean-worker-feedback-test
```

O desde el HUB admin: **Limpiar test worker**.

Esto borra `TEST_WORKER_FEEDBACK` y deja audit_log + snapshot de limpieza.

## Reglas de seguridad validadas

- Worker puede escribir datos operativos de prueba.
- Worker no necesita ver logs/backups/snapshots.
- Admin ve quién hizo la operación, desde qué máquina, qué cambió y cuándo.
- Admin puede limpiar la prueba y conservar trazabilidad.

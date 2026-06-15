# FutonHUB - Diagnostico esquema inventory_change_history 004B.1

Fecha: 2026-06-15

## Motivo

El smoke test manual del SKU `0201014` confirma:

- publicacion Woo correcta;
- precio correcto en la web;
- `inventory_items.woo_price` actualizado correctamente;
- rollback Woo correcto;
- precio de Inventario restaurado correctamente;
- fallo solo al escribir historial con `PGRST205: Could not find the table 'public.inventory_change_history' in the schema cache`.

No se repitieron publicaciones reales y no se ejecuto ninguna migracion.

## Causa raiz

`inventory_change_history` existe en el modelo local SQLite legacy, pero no existe como tabla creada por las migraciones Supabase del repositorio.

El servicio cloud `fetch_inventory_item_history` intenta leer `public.inventory_change_history` y silencia cualquier excepcion de lectura. Por eso el detalle de Inventario muestra historial vacio si la tabla no esta disponible. En escritura, `record_woo_price_inventory_history` falla explicitamente al consultar/insertar contra la misma tabla, y Supabase devuelve `PGRST205`.

Conclusion: datos de Woo e Inventario se sincronizan, pero el historial completo no puede persistirse porque falta la tabla operativa expuesta a PostgREST o no esta en el schema cache. Con la evidencia del repositorio, no hay una tabla canonica Supabase equivalente ya definida.

## Busqueda en repositorio

Resultados relevantes:

- `GestorWoo/src/gestorwoo/inventory.py` crea la tabla local SQLite `inventory_change_history`.
- `GestorWoo/src/futonhub/cloud/services/inventory.py` lee y escribe `inventory_change_history` via cliente Supabase/PostgREST.
- `docs/UI_ERP_INVENTARIO_SUPABASE_EDIT_V2.md` dice que los historiales leen desde `inventory_change_history` "si existe".
- `docs/history/NOTAS_PARCHE_ESTRUCTURA_LOCAL.md` registra conteos locales de `inventory_change_history`.
- No aparece `CREATE TABLE public.inventory_change_history` en `docs/supabase/*.sql`.
- No se encontro una tabla alternativa canonica de historial de Inventario en las migraciones Supabase.

## Fuente real del historial visible

La vista `inventory_detail.py` llama:

```text
fetch_inventory_item_history(session, item_id, limit=120)
```

Ese servicio consulta, en este orden:

1. `inventory_change_history` por `item_id`.
2. `audit_logs` como caja negra, solo si `entity_id`, `before_data.item_id` o `after_data.item_id` coinciden con el item.

Las publicaciones Woo y rollbacks quedan en `audit_logs` como operaciones de propuesta/precio Woo, no como cambios directos de `inventory_item`. Por eso no alimentan los graficos de Inventario salvo que exista la fila normalizada en `inventory_change_history`.

## Lectura vacia

Si `inventory_change_history` no existe o no esta expuesta a PostgREST, la lectura actual captura la excepcion y continua:

```text
except Exception:
    pass
```

Impacto: el usuario ve historial vacio en lugar del error `PGRST205`. La escritura correctiva de 004B.1 no lo silencia y por eso el fallo aparece durante publicacion/rollback.

## SQL de diagnostico de solo lectura

Ejecutar en Supabase SQL Editor antes de cualquier migracion:

```sql
select to_regclass('public.inventory_change_history') as inventory_change_history_regclass;

select table_schema, table_name
from information_schema.tables
where table_name ilike '%history%'
   or table_name ilike '%historial%'
   or table_name in ('inventory_change_history', 'inventory_history')
order by table_schema, table_name;

select table_schema, table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_name ilike '%history%'
   or table_name ilike '%historial%'
   or table_name in ('inventory_change_history', 'inventory_history')
order by table_schema, table_name, ordinal_position;

select schemaname, tablename, rowsecurity
from pg_tables
where tablename ilike '%history%'
   or tablename ilike '%historial%'
   or tablename in ('inventory_change_history', 'inventory_history')
order by schemaname, tablename;

select schemaname, tablename, policyname, cmd, roles, qual, with_check
from pg_policies
where tablename ilike '%history%'
   or tablename ilike '%historial%'
   or tablename in ('inventory_change_history', 'inventory_history')
order by schemaname, tablename, policyname;

select grantee, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name = 'inventory_change_history'
order by grantee, privilege_type;
```

Interpretacion:

- `to_regclass` nulo: la tabla no existe en `public`.
- Tabla en otro esquema: no esta disponible como `public.inventory_change_history`.
- Tabla en `public` pero PGRST205: probable schema cache de PostgREST sin recargar o tabla no expuesta.
- Tabla en `public` sin grants/policies: el error esperado seria de permisos/RLS, no `PGRST205`.

## Migracion minima propuesta

Solo si el diagnostico confirma que no existe una tabla canonica equivalente:

```sql
create table if not exists public.inventory_change_history (
    id uuid primary key default gen_random_uuid(),
    item_id bigint not null references public.inventory_items(item_id) on delete cascade,
    item_name text,
    field text,
    field_name text,
    old_value text,
    new_value text,
    operation_id text,
    message text,
    notes text,
    source text,
    change_source text,
    action text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    created_by uuid references public.profiles(id) on delete set null
);

create index if not exists idx_inventory_change_history_item_created
on public.inventory_change_history(item_id, created_at desc);

create index if not exists idx_inventory_change_history_field
on public.inventory_change_history(coalesce(field, field_name));

create index if not exists idx_inventory_change_history_operation
on public.inventory_change_history(operation_id);

create unique index if not exists uq_inventory_change_history_operation_item_field
on public.inventory_change_history(operation_id, item_id, coalesce(field, field_name, ''))
where operation_id is not null;

alter table public.inventory_change_history enable row level security;

drop policy if exists "inventory_change_history_authenticated_read" on public.inventory_change_history;
drop policy if exists "inventory_change_history_admin_insert" on public.inventory_change_history;

create policy "inventory_change_history_authenticated_read"
on public.inventory_change_history
for select to authenticated
using (true);

create policy "inventory_change_history_admin_insert"
on public.inventory_change_history
for insert to authenticated
with check (public.is_admin());

grant select, insert on public.inventory_change_history to authenticated;

notify pgrst, 'reload schema';
```

Notas:

- No se propone `update` ni `delete`: la tabla debe ser append-only para no borrar eventos de publicacion/rollback.
- Se incluyen `field` y `field_name` para compatibilidad entre el servicio cloud actual y el esquema legacy local.
- La unicidad por `operation_id + item_id + field` refuerza la idempotencia de reintentos.

## RLS y policies requeridas

Minimo para el flujo actual:

- `SELECT` para usuarios autenticados, porque el detalle de Inventario lee historial.
- `INSERT` para admin, porque publicar y rollback son acciones administrativas.
- Sin `UPDATE` ni `DELETE`, para preservar trazabilidad.
- `grant select, insert` a `authenticated`.

Si el rol operativo real de publicacion no evalua `public.is_admin()`, la policy debera ampliarse explicitamente al rol usado por FutonHUB sin abrir escritura general innecesaria.

## Impacto sobre datos existentes

La migracion propuesta crea una tabla nueva vacia y no modifica:

- `inventory_items`;
- `price_change_proposals`;
- `audit_logs`;
- `operation_snapshots`;
- tablas Woo espejo.

No recupera automaticamente los eventos historicos ya ejecutados.

## Plan de backfill futuro

Cuando se autorice, el backfill deberia:

1. Leer `audit_logs` y `operation_snapshots` de publicaciones Woo y rollbacks.
2. Resolver `item_id` por snapshot/propuesta/source row antes que por SKU.
3. Insertar eventos `woo_price` faltantes en `inventory_change_history`.
4. Usar `operation_id + item_id + field` para no duplicar.
5. Reportar operaciones no resolubles sin inventar asociaciones.

No debe borrar ni sobrescribir logs, snapshots ni eventos existentes.

## Correccion documental 004B.1

El documento inicial de 004B.1 afirmaba que no habia cambios de esquema. Tras el smoke test, esa afirmacion queda corregida: el codigo dependia de una tabla operativa no creada por las migraciones Supabase del repositorio. La correccion funcional requiere una migracion minima autorizada o una confirmacion SQL de que la tabla existe y solo falta recargar/exponer el schema cache.

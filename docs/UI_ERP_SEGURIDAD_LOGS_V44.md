# UI ERP v44 - Seguridad / Logs v1 funcional

## Objetivo

Activar una sección real de auditoría para administradores.

```text
Sistema → Seguridad / Logs
```

## Permisos

- Admin: puede ver Seguridad / Logs.
- Worker: no ve el menú Seguridad / Logs.
- Si un worker intenta acceder internamente, recibe acceso denegado.

## Funcionalidad

### Tabla audit_logs

Lee desde Supabase:

```text
audit_logs
```

Muestra:

- Fecha / Hora
- Usuario
- Rol
- Módulo
- Acción
- Estado
- Severidad
- Entidad
- ID Entidad
- Operation ID
- Mensaje

### Filtros v1

- Texto
- Usuario
- Módulo
- Estado
- Severidad
- Fecha desde
- Fecha hasta

### KPIs

- Eventos hoy
- Errores hoy
- Críticos
- Última operación
- Último usuario activo

### Detalle de log

Doble click en una línea abre:

- resumen técnico
- before/after en tabla comparativa
- snapshot asociado por operation_id

### Snapshot

El snapshot aparece dentro del detalle.  
También se puede abrir el JSON completo del snapshot.

### Rollback

Botón visible:

```text
Restaurar estado anterior
```

pero desactivado funcionalmente para v1. Muestra aviso de que se preparará en v2.

## Exportación

Botón:

```text
Exportar visible
```

Exporta a Excel:

- Resumen
- Logs visibles
- Snapshots relacionados

## Archivos añadidos

```text
GestorWoo/src/futonhub/cloud/services/security_logs.py
```

## Archivo modificado

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

## Checklist de pruebas

1. Login admin.
2. Verificar que aparece Sistema → Seguridad / Logs.
3. Abrir Seguridad / Logs.
4. Pulsar Actualizar.
5. Crear artículo y volver a Seguridad / Logs.
6. Filtrar módulo Inventario.
7. Abrir detalle de log.
8. Ver before/after.
9. Ver snapshot asociado.
10. Exportar visible.
11. Login worker y confirmar que no ve Seguridad / Logs.

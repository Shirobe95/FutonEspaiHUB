# UI ERP v47 - Dashboard real v1

## Objetivo

Convertir el Dashboard en una cabina de mando útil, sin abarrotar la pantalla.

## Decisiones aplicadas

- No se muestra conteo de items de inventario.
- KPIs enfocados en atención diaria.
- Actividad reciente simplificada desde audit_logs.
- Bloques de atención reducidos.
- Estado de sistemas visible.

## KPIs superiores

```text
Pedidos abiertos
Pedidos en validación
Recepciones parciales
Propuestas pendientes
Errores hoy
```

## Actividad reciente

Lista simplificada de las últimas acciones auditadas:

```text
hora · usuario
módulo · acción
```

Con color por estado.

## Bloques de atención

```text
Pedidos que necesitan revisión
Propuestas pendientes
Últimos errores
```

Cada bloque muestra pocos elementos y acceso rápido al módulo correspondiente.

## Pedidos recientes

Bloque compacto con pedidos abiertos/recientes y estado.

## Estado de sistemas

```text
Supabase
WooCommerce
Seguridad
Próximo frente
```

## Archivos modificados

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

## Checklist de prueba

1. Abrir Dashboard con admin.
2. Confirmar KPIs superiores.
3. Confirmar que no aparece conteo de items de inventario.
4. Confirmar actividad reciente.
5. Confirmar bloque de atención de pedidos/propuestas/errores.
6. Probar click en KPI o botón Ver para navegar al módulo.
7. Abrir con worker y confirmar que no rompe aunque no pueda leer Seguridad/Logs.

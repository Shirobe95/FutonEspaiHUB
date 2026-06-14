# UI ERP v48 - Dashboard responsive

## Problema detectado

Con usuario admin, la tarjeta de `Actividad reciente` cargaba más líneas reales desde audit_logs y empujaba hacia abajo:

```text
Pedidos recientes
Estado de sistemas
```

En worker no se notaba porque no cargaba tanta actividad.

## Solución

El cuerpo del Dashboard ahora está dentro de un canvas con scroll vertical.

Además:

- Actividad reciente visible limitada a 8 líneas.
- Pedidos recientes visible limitado a 5 líneas.
- Bloques de atención muestran máximo 2 líneas por sección.
- Todos los bloques quedan accesibles aunque haya mucha actividad.
- Los KPIs superiores siguen fijos arriba.

## Objetivo visual

Mantener el Dashboard limpio:

```text
KPIs arriba
Actividad + atención en primera zona
Pedidos recientes + estado sistemas accesibles con scroll
```

## Checklist de prueba

1. Entrar como admin.
2. Confirmar que actividad reciente se carga.
3. Confirmar que se ven o se puede llegar con scroll a:
   - Pedidos recientes
   - Estado de sistemas
4. Probar rueda del mouse sobre Dashboard.
5. Entrar como worker y confirmar que sigue viéndose correcto.

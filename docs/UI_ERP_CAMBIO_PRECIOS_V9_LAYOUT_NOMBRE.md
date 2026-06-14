# UI ERP Cambio de Precios v9 - Layout, nombre de propuesta y preview visual

## Cambios

- El listado de propuestas mantiene proporciones entre lista y detalle.
- Los nombres largos de propuestas hacen salto de línea y no empujan el layout.
- El detalle de propuesta también permite nombres largos con wrap.
- En la edición de propuesta, los nombres largos de items ya no se comen los botones Modificar / Borrar.
- Los botones Modificar / Borrar quedan en una zona de acciones fija a la derecha del item.
- Se quitó el botón visible "Preview seguridad" del detalle de propuesta.
  - La validación sigue existiendo dentro del flujo protegido de aceptar.
  - El resultado operativo se verá en Seguridad / Logs.
- Al guardar propuestas nuevas desde el editor, se conserva el nombre escrito por el usuario en `source_row.ui_proposal_name` y en notas de la propuesta.
- Al listar propuestas, si existe `source_row.ui_proposal_name`, se usa como nombre visible de la propuesta.

## Nota técnica

El esquema actual de `price_change_proposals` trabaja principalmente por línea/propuesta individual.
Para respetar el nombre escrito en UI sin cambiar todavía el esquema, se almacena el nombre visual en `source_row.ui_proposal_name`.

Más adelante, si se quiere una propuesta con varias líneas como entidad agrupada, conviene crear tablas dedicadas:

- `price_proposal_groups`
- `price_proposal_group_items`

De momento esta v9 corrige el comportamiento visual y mantiene compatibilidad con la lógica actual.

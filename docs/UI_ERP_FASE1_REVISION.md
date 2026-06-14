# FutonHUB UI-ERP - Fase 1 Revision funcional

Ultima actualizacion: 2026-05-31

Objetivo de esta fase: revisar todos los disenos del pack v2 contra lo que FutonHUB ya tiene o necesita, antes de conectar logica real.

Referencia canonica:

```text
docs/ui_reference/FutonHUB_UI_pack_Codex_v2/
```

Reglas base:

- HTML como referencia visual.
- Markdown como contrato funcional.
- No tocar `Main` directamente.
- No convertir selects en entries.
- No conectar acciones reales sin validacion, confirmacion y logs.

## Resumen ejecutivo

La estructura general del ERP ya esta bien orientada:

- menu oficial v2 aplicado
- login previo al ERP implementado
- Dashboard, Inventario, Cambio de Precios, Pedidos, WooCommerce, Informes / Exportaciones y Configuracion tienen prototipo visual
- Proveedores ya no vive como modulo de menu, solo como acceso dentro de Pedidos

Antes de pasar a logica real conviene moldear cuatro puntos:

1. Completar `Seguridad / Logs` segun el mockup v2, porque aun esta como vista generica.
2. Decidir filtros cerrados en `Inventario` antes de conectar busqueda real.
3. Hacer explicito el flujo interno de `Cambio de Precios`: listado, detalle, modificar y guardar.
4. Marcar botones visuales/futuros para que no parezcan acciones reales.

## Menu lateral

Estado: aprobado con ajustes ya aplicados.

Menu oficial:

```text
Dashboard
Inventario
Cambio de Precios
Pedidos
WooCommerce
Informes / Exportaciones
Seguridad / Logs
Configuracion
```

Decision:

- no incluir `Proveedores` como modulo independiente
- `Calcular nuevo pedido` vive dentro de `Pedidos`
- los proveedores son accesos rapidos dentro de `Pedidos`

Pendiente:

- limpiar restos visuales/documentales antiguos que mencionen `Calcular Pedido` como modulo lateral cuando ya no aplique
- opcional: eliminar codigo muerto del prototipo para una vista independiente de Proveedores

## Dashboard

Estado: aprobado para Fase 1.

Lo que ya encaja:

- cuatro indicadores principales
- vista detallada al hacer click en cada indicador
- acciones rapidas a flujos reales
- topbar limpia con estado y rol

Moldeo recomendado:

- mantenerlo simple; no reintroducir cabeceras grandes ni botones superiores innecesarios
- cuando conectemos logica, las tarjetas deben venir de estados reales: logs, locks, Supabase, WooCommerce, inventario y propuestas

Decision:

- no tocar visualmente ahora salvo que aparezca una necesidad funcional concreta

## Inventario

Estado: bastante alineado.

Lo que ya encaja:

- busqueda superior
- tabla izquierda y detalle derecho
- detalle completo en modal grande
- agregar a propuesta abre popup con dos opciones
- item se transporta hacia Cambio de Precios

Moldeo recomendado antes de logica real:

- agregar filtros cerrados como ComboBox: familia, proveedor, estado
- mantener tabla esencial: ID, Nombre, Precio, Stock, Estado
- confirmar si `Exportacion de inventario` manda a `Informes / Exportaciones` o genera directamente un preview visual

Decision propuesta:

- `Exportacion de inventario` deberia abrir el popup de nueva exportacion con modulo Inventario preseleccionado cuando conectemos la logica
- `M3 calculo` debe venir de `inventory_items.cubic_meters`; `size` se muestra como `Medidas / dimensiones` y no se usa para calcular M3

## Cambio de Precios

Estado: funcionalmente bien orientado, necesita cierre de flujo.

Lo que ya encaja:

- listado de propuestas guardadas
- detalle lateral con acciones fijas
- workspace de modificar propuesta
- item recibido desde Inventario
- estados y cambios con colores

Moldeo recomendado antes de logica real:

- dejar claro que `Nueva propuesta` abre el workspace de modificar en modo nuevo
- `Modificar` abre el mismo workspace en modo edicion
- `Aceptar propuesta` y `Rechazar propuesta` deben quedar visuales hasta conectar servicio real
- `Guardar cambios` debe preparar validacion, no escribir directo

Decision propuesta:

- mantener un solo modulo `Cambio de Precios`
- dentro del modulo hay dos estados de pantalla: `Propuestas guardadas` y `Modificar propuesta`
- no publicar WooCommerce desde aqui sin preview final y lock

## Pedidos

Estado: aprobado con el ultimo ajuste.

Lo que ya encaja:

- proveedores como accesos rapidos compactos
- pedidos en marcha con mas espacio
- detalle lateral del pedido seleccionado
- calcular nuevo pedido se abre heredando proveedor
- no hay selector de proveedor dentro de calcular pedido
- cargar pedido compacto: boton, archivo y tipo
- recibido abre popup total/parcial
- detalle completo abre modal grande con tabla de calculos

Moldeo recomendado antes de logica real:

- confirmar columnas finales de `Pedidos en marcha`: ID Pedido, Proveedor, Fecha, Items, Total M3, Total, Estado
- `Borrar pedido` debe ser confirmacion futura, no accion directa
- `Exportar` debe abrir/generar registro en `Informes / Exportaciones`

Decision propuesta:

- `Pedidos` es el centro operativo completo: proveedor, calculo, pedido activo, recibido, detalle y exportacion

## WooCommerce

Estado: alineado con contrato funcional.

Lo que ya encaja:

- foco en actualizar base local desde WooCommerce
- tabla de diferencias local vs Woo
- detalle lateral
- auto-clasificacion y revision manual
- caso `Critical` bloquea accion visual

Moldeo recomendado antes de logica real:

- `Leer WooCommerce` debe ser lectura/preview, no escritura
- `Actualizar base de datos` debe actualizar local/Supabase, no publicar Woo
- casos dudosos deben quedar como `Revisar manual`

Decision propuesta:

- WooCommerce no es pantalla principal de publicacion
- la publicacion de precios sigue protegida por flujo de propuestas aprobadas, preview y lock

## Informes / Exportaciones

Estado: alineado visualmente.

Lo que ya encaja:

- registro de exportaciones
- detalle lateral de exportacion
- popup de nueva exportacion
- selects implementados como ComboBox cerrado
- opciones de registro/logs visibles

Moldeo recomendado antes de logica real:

- toda exportacion generada desde otro modulo deberia registrar aqui una entrada
- `Descargar`, `Regenerar` y `Eliminar registro` deben quedar protegidos por permisos/logs cuando sean reales

Decision propuesta:

- este modulo sera el centro de salida del ERP
- no duplicar exportaciones dentro de cada modulo; cada modulo puede lanzar la exportacion, pero el registro vive aqui

## Seguridad / Logs

Estado: pendiente de moldear.

Lo que falta frente al mockup v2:

- busqueda de logs
- filtros por modulo/nivel
- resumen de eventos
- tabla de eventos con columnas: Fecha / Hora, Nivel, Modulo, Accion, Usuario / Rol, Resultado, Referencia
- boton `Ver detalles`
- popup grande con resumen, cambios, payload tecnico, snapshot y exportacion

Decision propuesta:

- esta debe ser la proxima pantalla a ajustar visualmente antes de conectar logica real
- sera la caja negra del ERP y dara soporte a todas las acciones sensibles

## Configuracion

Estado: alineado.

Lo que ya encaja:

- tres pestanas: Generales, Calculos, Seguridad
- Modo y Tema son ComboBox cerrados
- constantes de negocio editables
- reglas de seguridad visibles como switches
- conexiones visibles

Moldeo recomendado antes de logica real:

- `Rol actual` debe venir de la sesion login y ser readonly
- constantes deben conectarse a business constants con preview/log
- cambios de seguridad deben dejar audit log

Decision propuesta:

- Configuracion es motor del ERP, pero no se conecta hasta tener logs/preview maduros

## Orden recomendado para moldear antes de logica real

1. Seguridad / Logs: completar visualmente segun mockup v2.
2. Inventario: agregar filtros cerrados y decidir flujo de exportacion.
3. Cambio de Precios: cerrar estados internos `listado` / `modificar`.
4. Informes / Exportaciones: preparar entrada desde otros modulos.
5. Configuracion: revisar copy y readonly/ComboBox.
6. Dashboard: solo ajustar si los estados reales lo exigen.

## Criterio de cierre de Fase 1

- todas las pantallas tienen estructura funcional aprobada
- cada boton tiene destino definido o etiqueta interna de accion futura
- no quedan modulos duplicados
- no quedan selects convertidos en entries
- las acciones sensibles quedan visuales hasta tener validacion, confirmacion y logs

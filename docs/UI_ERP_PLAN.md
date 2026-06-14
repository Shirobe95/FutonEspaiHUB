# FutonHUB UI-ERP Plan

Ultima actualizacion: 2026-05-31

## Decision actual

La UI-ERP v1 se construira de momento en Tkinter.

Objetivo:

- una sola ventana
- menu lateral
- topbar
- area central por modulo
- integracion gradual con la logica existente
- cero operaciones criticas sin preview, validacion, confirmacion y log

El pack `docs/ui_reference/FutonHUB_UI_pack_Codex_v2/` es la referencia canonica actual:

- los HTML son referencia visual
- los Markdown son contrato funcional
- los selects del HTML deben mantenerse como selectores/ComboBox, no como `Entry`
- no se toca `Main` directamente
- primero se integra visualmente; despues se conecta logica real con validaciones, confirmacion y logs

La plantilla anterior `futonhub_sistema_visual_v1_interactivo.html` queda sustituida por este pack para decisiones nuevas de UI.

Inventario funcional completo: `docs/FUNCTIONAL_INVENTORY.md`.
Revision funcional Fase 1: `docs/UI_ERP_FASE1_REVISION.md`.

## Estructura de navegacion

### Principal

```text
Dashboard
```

### Operaciones

```text
Inventario
Cambio de Precios
Pedidos
```

### Gestion

```text
WooCommerce
Informes / Exportaciones
```

### Sistema

```text
Seguridad / Logs
Configuracion
```

## Proveedores en Pedidos

La UI debe contemplar cuatro proveedores iniciales dentro del modulo `Pedidos`:

```text
Ekomat
Pascal
Heimei
Cipta
```

La plantilla anterior solo mostraba tres. FutonHUB debe incluir CIPTA dentro de las tarjetas de acceso a calculo de pedidos.

## Mapping de modulos reales

### Dashboard

Uso:

- estado general del sistema
- alertas
- warnings
- locks
- accesos rapidos
- ultima actividad

Origen actual:

- diagnosticos locales
- diagnosticos cloud
- audit logs
- operation snapshots
- locks locales y online

### Inventario

Uso:

- buscar productos e inventario interno
- revisar stock tienda/almacen
- ver relacion local/Woo
- preparar cambios internos con preview

Origen actual:

- `futonhub.cloud.services.inventory`
- `futonhub.ui.erp.cloud_inventory`
- modulo legacy de inventario local

Criterio de datos:

- `inventory_items.size` se trata como medidas/dimensiones del producto.
- `inventory_items.cubic_meters` se trata como M3 real para calculos.
- si `cubic_meters` viene vacio, la UI debe mostrar `Pendiente`; nunca debe usar `size` como M3.

Acciones reales futuras:

- preview cambio stock
- aplicar cambio interno Supabase
- ver historial
- exportar inventario

### Cambio de Precios

Uso:

- crear propuestas
- revisar diferencias
- validar riesgos
- aprobar/rechazar
- preview WooCommerce
- publicar precio en Woo con lock

Origen actual:

- `futonhub.cloud.services.price_proposals`
- `futonhub.cloud.services.prices`
- `futonhub.cloud.services.woocommerce_publish`
- `futonhub.ui.erp.cloud_prices`

Estado Fase 2:

- bandeja de propuestas reales en modo lectura desde `price_change_proposals`
- la columna `Estado` muestra el estado real: Pendiente, Aprobada, Rechazada, Publicando, Publicada o Fallida
- preview real de seguridad sobre propuesta guardada
- aprobar/rechazar usa modal protegido con preview, confirmacion escrita, snapshot y log
- WooCommerce no se toca desde esta fase

Regla:

- si hay `Critical`, se bloquea la publicacion.

### Pedidos / Calcular pedido

Uso:

- elegir proveedor dentro del modulo Pedidos
- cargar/calcular pedido
- validar M3 y datos faltantes
- exportar resultado

Origen actual:

- `CalculoCoste/`
- `futonhub.modules.cost.launcher`

Proveedores:

- Ekomat
- Pascal
- Heimei
- Cipta

### WooCommerce

Uso:

- gestion del estado de la web
- comparar local/Supabase/Woo
- detectar diferencias
- generar previews
- revisar sincronizaciones

No se mezcla con Cambio de Precios:

- Cambio de Precios prepara y publica precios.
- WooCommerce gestiona comparacion/sync/estado de la tienda online.

Estado Fase 2:

- `Preview publicacion` usa `preview_woocommerce_publish` sobre propuestas aprobadas.
- WooCommerce solo se lee; no hay publicacion, sincronizacion ni PUT desde esta vista.
- la publicacion real queda para una fase posterior con confirmacion escrita, lock, snapshot y log.

### Informes

Uso:

- exportaciones
- propuestas de precios
- coste de pedido
- incidencias WooCommerce
- auditoria/logs
- inventario

### Configuracion

Debe tener solo tres pestanas:

```text
Generales
Calculos
Seguridad
```

Incluye:

- entorno
- modo de trabajo
- conexiones
- constantes del negocio
- reglas de seguridad
- backups

### Seguridad / Logs

Uso:

- caja negra
- audit logs
- snapshots
- rollback
- locks
- diagnosticos

## Estados oficiales

```text
OK
Info
Warning
Error
Critical
```

Reglas:

- `OK`: todo correcto.
- `Info`: informacion util, no bloquea.
- `Warning`: requiere revision, normalmente no bloquea.
- `Error`: problema funcional, puede bloquear el paso actual.
- `Critical`: bloquea siempre la operacion completa.

## Flujo obligatorio para acciones sensibles

```text
Preparar datos
Validar
Preview
Confirmacion
Ejecucion protegida
Resultado
Log
```

Acciones sensibles:

- publicar precios en WooCommerce
- cambiar stock
- importar datos masivos
- sincronizar WooCommerce
- actualizar constantes que afectan calculos
- rollback
- migraciones

## Prototipo Tkinter

Entrada aislada:

```powershell
python GestorWoo\gestorwoo.py erp-prototype
```

Modulo:

```text
futonhub/ui/erp/prototype.py
```

El prototipo no sustituye al HUB estable. Sirve para validar navegacion, nomenclatura, layout y ubicacion de funciones antes de conectar flujos reales.

Login:

- el prototipo arranca con el ERP oculto
- muestra un popup de login antes de entrar a la UI
- usa login real Supabase en modo `supabase_guarded`
- construye y muestra el ERP solo tras autenticar
- actualiza la topbar con `Online` y rol (`Admin` o `Worker`)
- no muestra el correo del usuario en la topbar para mantener la zona limpia
- aun no filtra navegacion por permisos; eso se hara al conectar flujos reales

## Plan de trabajo en 3 fases

### Fase 1: Revision funcional de disenos

Objetivo:

- revisar todos los mockups del pack v2 contra lo que FutonHUB ya tiene implementado
- ajustar pantallas al flujo operativo real
- quitar o mover elementos que no aporten trabajo real
- confirmar ubicacion de cada accion dentro del modulo correcto
- dejar cerrada la nomenclatura visible

Modulos a revisar:

- Dashboard
- Inventario
- Cambio de Precios
- Pedidos
- WooCommerce
- Informes / Exportaciones
- Seguridad / Logs
- Configuracion

Criterio de salida:

- cada pantalla tiene estructura aprobada
- cada boton tiene destino o queda marcado como visual/futuro
- cada selector del HTML sigue siendo ComboBox cerrado
- no quedan modulos duplicados ni flujos partidos

### Fase 2: Logica real y pruebas por modulo

Objetivo:

- conectar servicios reales de forma gradual
- mantener el prototipo aislado hasta que el flujo sea estable
- probar modulo por modulo antes de mezclar comportamientos

Estado iniciado:

- `Seguridad / Logs` ya lee `audit_logs` y `operation_snapshots` reales con la sesion Supabase autenticada.
- Tambien muestra conteo de locks locales activos/caducados.
- La UI no escribe ni modifica datos desde esta pantalla.
- `Inventario` ya busca filas reales en `inventory_items` y genera preview real de cambio interno de stock.
- La UI de Inventario no aplica escrituras todavia; WooCommerce no se toca.

Orden recomendado:

1. Dashboard: estado real, locks, alertas y ultimos logs.
2. Inventario: busqueda real, detalle, preview de cambio interno.
3. Cambio de Precios: propuestas reales, aprobacion/rechazo, preview Woo.
4. Pedidos: calculo real desde `CalculoCoste` / `futonhub.modules.cost`.
5. WooCommerce: lectura Woo, comparacion local, clasificacion, incidencias.
6. Informes / Exportaciones: registro, generacion y trazabilidad.
7. Seguridad / Logs: audit logs, snapshots, rollback y detalles.
8. Configuracion: constantes, conexiones y reglas sensibles.

Criterio de salida:

- cada accion sensible tiene validacion, preview, confirmacion y log
- los tests de arquitectura y seguridad siguen en verde
- no se toca `Main` directamente
- los flujos legacy siguen funcionando

### Fase 3: Pulido visual final

Objetivo:

- mejorar acabado visual sin cambiar la logica
- unificar radios, sombras ligeras, espaciados y jerarquias
- mejorar legibilidad de tablas, estados, modales y botones
- revisar que no haya solapes ni textos cortados

Criterio de salida:

- UI consistente en todos los modulos
- botones y paneles tienen acabado profesional
- estados OK / Info / Warning / Error / Critical son claros
- acciones principales quedan visibles y comodas
- el ERP se siente como una sola aplicacion, no como pantallas pegadas

## Criterio para avanzar a integracion real

Antes de conectar acciones reales en la UI-ERP:

- navegacion aprobada
- nombres finales aprobados
- ubicacion de cada flujo validada
- estados visuales consistentes
- pruebas de import/arquitectura en verde
- flujos criticos conservan preview/log/confirmacion

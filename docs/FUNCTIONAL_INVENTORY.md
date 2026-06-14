# FutonHUB - Inventario funcional

Ultima actualizacion: 2026-05-27

Este documento lista las funcionalidades existentes o previstas inmediatas para ubicar cada elemento dentro de la futura UI-ERP.

## Autenticacion y permisos

Funcionalidad existente:

- login real contra Supabase con email/password
- registro de dispositivo visto
- lectura de rol cloud
- bloqueo de herramientas si no hay sesion en `supabase_guarded`
- distincion admin/worker mediante permisos
- visibilidad por modulo segun rol

Ubicacion UI-ERP:

- topbar: estado de sesion, usuario, rol
- Sistema > Configuracion > Seguridad: reglas y estado de permisos
- Sistema > Seguridad / Logs: trazabilidad de accesos y operaciones

Flujo:

```text
Abrir FutonHUB
Mostrar popup de login
Introducir usuario y contrasena
Validar usuario/rol/dispositivo
Construir y mostrar UI-ERP
Actualizar topbar con Online + rol
Mostrar modulos permitidos segun rol
```

## Dashboard

Funcionalidad existente/parcial:

- estado local del sistema
- estado Supabase
- diagnosticos
- locks locales
- locks online RPC
- ultimos logs/snapshots visibles
- avisos de seguridad

Ubicacion UI-ERP:

- Dashboard

Flujo:

```text
Entrar al ERP
Ver salud general
Ver alertas/warnings
Saltar a modulo afectado
```

## Inventario

Funcionalidad existente:

- gestion visual de inventario local legacy
- busqueda de inventario interno Supabase
- preview de cambio de stock interno
- aplicar cambio interno en Supabase
- snapshot antes de aplicar
- audit log tras aplicar
- no toca WooCommerce

Ubicacion UI-ERP:

- Operaciones > Inventario

Elementos:

- buscador
- tabla de items
- detalle lateral
- stock tienda
- stock almacen
- relacion Woo
- estado de link
- historial/logs

Flujo:

```text
Buscar item
Seleccionar item
Ver detalle
Preparar cambio stock
Preview
Confirmar
Aplicar Supabase
Guardar snapshot/log
Mostrar resultado
```

## Cambio de Precios

Funcionalidad existente:

- buscar productos/variaciones Supabase
- crear propuesta real interna
- preview antes de crear
- validacion de bajadas de precio
- bloqueo de precio 0 o padre variable
- listado de propuestas
- aprobar/rechazar propuesta
- preview WooCommerce antes de publicar
- publicacion WooCommerce protegida
- lock online por propuesta
- estado `publishing`
- rollback de estado si falla antes de Woo
- estado `error` si falla tras escribir Woo
- audit log y snapshot

Ubicacion UI-ERP:

- Operaciones > Cambio de Precios

Elementos:

- buscador producto/variacion
- bandeja de propuestas
- panel de detalle
- validacion de seguridad
- preview propuesta
- preview Woo
- aprobar/rechazar
- publicar Woo

Flujo:

```text
Buscar producto
Crear propuesta
Validar seguridad
Guardar propuesta pending
Revisar propuesta
Aprobar/Rechazar
Preview Woo
Confirmar PUBLICAR
Adquirir lock
Marcar publishing
Actualizar Woo
Actualizar Supabase
Guardar snapshot/log
Mostrar resultado
```

## Calcular Pedido

Funcionalidad existente:

- calculadora individual legacy
- calculadora de pedido por proveedor legacy
- proveedores disponibles: Ekomat, Pascal, Heimei/Hemei, Cipta
- constantes del negocio
- exportaciones Excel

Ubicacion UI-ERP:

- Operaciones > Calcular Pedido

Elementos:

- selector proveedor
- carga/lectura de Excel
- validacion de datos
- tabla de lineas
- errores M3/datos faltantes
- resultado calculado
- exportacion

Flujo objetivo:

```text
Elegir proveedor
Cargar pedido
Validar datos
Editar o marcar errores
Calcular
Revisar resultado
Exportar
Guardar log si afecta datos
```

## WooCommerce

Funcionalidad existente:

- sincronizar productos desde WooCommerce
- importar producto Woo concreto a Supabase
- leer Woo para preview de publicacion
- comparar precio actual Woo vs propuesta
- actualizar precio de producto o variacion
- detectar sale_price activo
- detectar diferencias entre Woo y propuesta

Ubicacion UI-ERP:

- Gestion > WooCommerce

No confundir:

- Cambio de Precios prepara/aprueba/publica precios.
- WooCommerce gestiona estado, comparacion y sincronizacion de tienda.

Flujo objetivo:

```text
Leer Woo
Comparar con Supabase/local
Detectar diferencias
Generar preview
Validar riesgos
Confirmar si aplica
Ejecutar cambio real
Guardar log
```

## Proveedores

Funcionalidad existente/parcial:

- uso operativo de proveedores en CalculoCoste
- proveedores reales iniciales: Ekomat, Pascal, Heimei, Cipta
- logica especifica por proveedor

Ubicacion UI-ERP:

- Gestion > Proveedores

Elementos:

- ficha proveedor
- especialidad
- notas operativas
- ultimo pedido
- acceso directo a Calcular Pedido
- futuras condiciones/contactos/documentos

## Informes

Funcionalidad existente/parcial:

- exportacion desde herramientas legacy
- informes de propuesta de precios previstos
- coste de pedido
- inventario
- logs/auditoria
- incidencias WooCommerce

Ubicacion UI-ERP:

- Gestion > Informes

Flujo objetivo:

```text
Elegir tipo informe
Configurar filtros
Preview
Exportar Excel/PDF
Registrar exportacion si corresponde
```

## Configuracion

Funcionalidad existente:

- `.env` de configuracion
- modo `supabase_guarded`
- rol local fallback
- machine name
- rutas de base local
- constantes del negocio
- umbrales de bajada de precio
- conexiones Supabase/WooCommerce

Ubicacion UI-ERP:

- Sistema > Configuracion

Pestanas:

```text
Generales
Calculos
Seguridad
```

Flujo objetivo:

```text
Abrir configuracion
Editar valor
Validar
Preview si afecta calculos/seguridad
Guardar
Registrar log si es sensible
```

## Seguridad / Logs

Funcionalidad existente:

- audit logs locales
- audit logs cloud
- operation snapshots
- rollback interno desde snapshot
- test audit log
- test snapshot
- locks locales
- locks online RPC
- diagnosticos cloud
- diagnosticos con login
- estado operativo Supabase
- limpieza de datos TEST

Ubicacion UI-ERP:

- Sistema > Seguridad / Logs

Elementos:

- tabla logs
- tabla snapshots
- visor JSON/detalle
- rollback preview
- estado locks
- diagnosticos
- herramientas admin

Flujo rollback:

```text
Listar snapshots
Elegir operation_id
Generar preview
Confirmar REVERTIR
Aplicar Supabase
Guardar snapshot/log de rollback
Mostrar resultado
```

## Backups

Funcionalidad existente:

- app legacy de backups/restauracion
- backup local fechado
- restauracion con seguridad

Ubicacion UI-ERP:

- Sistema > Seguridad / Logs
- o Sistema > Configuracion > Seguridad

Decision pendiente:

- si Backups aparece como subseccion visible de Seguridad / Logs o como bloque dentro de Configuracion.

## Pruebas operativas / herramientas admin

Funcionalidad existente:

- crear constante test cloud
- crear/modificar TEST_WORKER_FEEDBACK
- pedido simulado worker
- inventario simulado worker
- propuesta precio simulada worker
- limpiar/cancelar datos test
- aprobar/rechazar propuesta test

Ubicacion UI-ERP:

- Sistema > Seguridad / Logs > Herramientas admin

Regla:

- no deben aparecer como flujo principal de usuario final.

## Estados oficiales

```text
OK
Info
Warning
Error
Critical
```

Uso:

- tablas
- chips
- dashboard
- previews
- logs
- validaciones

## Acciones criticas

Siempre requieren:

```text
validacion
preview
confirmacion
ejecucion protegida
snapshot/log
resultado visible
```

Acciones:

- publicar precio WooCommerce
- rollback
- cambio stock interno
- migracion SQLite -> Supabase
- importaciones/sincronizaciones masivas
- cambios de constantes sensibles
- restaurar backup

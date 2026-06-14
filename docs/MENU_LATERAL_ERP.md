# FutonHUB - Menu lateral UI-ERP

Fecha de trabajo: 2026-05-27

Objetivo: ordenar todas las funciones y partes del mini ERP antes de conectar funcionalidad real en la UI. Este documento se puede imprimir o revisar en PDF para marcar decisiones a mano.

## Criterios de organizacion

- El ERP debe abrir con login antes de mostrar la ventana principal.
- La ventana principal tendra un menu lateral, topbar y area central por modulo.
- La topbar debe mostrar estado Online y rol: Admin o Worker.
- Las funciones visibles dependen del rol y de los permisos cloud.
- Las acciones criticas siempre requieren validacion, preview, confirmacion, ejecucion protegida, resultado visible y log.
- WooCommerce real no se toca sin preview, confirmacion y caja negra.
- El menu debe permitir crecer con nuevos modulos sin rehacer la estructura.

## Mapa propuesto de menu lateral

### Principal

- [ ] Dashboard

### Operaciones

- [ ] Inventario
- [ ] Cambio de Precios
- [ ] Calcular Pedido

### Gestion

- [ ] WooCommerce
- [ ] Proveedores
- [ ] Informes

### Sistema

- [ ] Configuracion
- [ ] Seguridad / Logs

## Dashboard

Ubicacion propuesta: Principal > Dashboard

Debe contener:

- [ ] Alertas Criticas
- [ ] Warnings Activos
- [ ] Pendiente a Sincronizar
- [ ] Sistema
- [ ] Vista detallada dinamica segun tarjeta seleccionada
- [ ] Acciones rapidas
- [ ] Ultima actividad
- [ ] Estado de Supabase
- [ ] Estado de WooCommerce
- [ ] Estado de locks locales y online

Acciones rapidas iniciales:

- [ ] Calcular Pedido
- [ ] Crear propuesta de precio
- [ ] WooCommerce

Pendiente de decidir:

- [ ] Incluir acceso rapido a Inventario
- [ ] Incluir acceso rapido a Logs criticos
- [ ] Mostrar indicadores por rol

## Inventario

Ubicacion propuesta: Operaciones > Inventario

Debe contener:

- [ ] Buscador de items
- [ ] Tabla de inventario interno
- [ ] Detalle lateral del item
- [ ] Stock tienda
- [ ] Stock almacen
- [ ] Relacion con WooCommerce
- [ ] Estado de link local / Supabase / Woo
- [ ] Preview de cambio interno
- [ ] Aplicar cambio interno Supabase
- [ ] Historial del item
- [ ] Logs y snapshots relacionados
- [ ] Exportar inventario

Flujo base:

- [ ] Buscar item
- [ ] Seleccionar item
- [ ] Ver detalle
- [ ] Preparar cambio
- [ ] Validar
- [ ] Preview
- [ ] Confirmar
- [ ] Aplicar Supabase
- [ ] Guardar snapshot/log
- [ ] Mostrar resultado

Roles:

- [ ] Admin: puede aplicar cambios y ver trazabilidad completa
- [ ] Worker: puede consultar y proponer/ejecutar solo lo permitido

## Cambio de Precios

Ubicacion propuesta: Operaciones > Cambio de Precios

Debe contener:

- [ ] Buscador de producto/variacion
- [ ] Crear propuesta de precio
- [ ] Preview de propuesta
- [ ] Validaciones de seguridad
- [ ] Bandeja de propuestas
- [ ] Estados: pending, approved, rejected, publishing, published, error
- [ ] Detalle de propuesta
- [ ] Aprobar propuesta
- [ ] Rechazar propuesta
- [ ] Preview WooCommerce
- [ ] Publicar en WooCommerce
- [ ] Lock online por propuesta
- [ ] Rollback de estado si falla antes de Woo
- [ ] Estado error si falla despues de escribir Woo
- [ ] Audit log y snapshot

Reglas criticas:

- [ ] Bloquear precio cero o negativo
- [ ] Bloquear publicacion de padre variable
- [ ] Alertar bajadas fuertes
- [ ] Bloquear si hay Critical
- [ ] Detectar sale_price activo
- [ ] Comparar Woo actual contra propuesta

Roles:

- [ ] Admin: aprobar, rechazar, publicar y revisar errores
- [ ] Worker: crear propuestas y ver estado segun permisos

## Calcular Pedido

Ubicacion propuesta: Operaciones > Calcular Pedido

Debe contener:

- [ ] Selector de proveedor
- [ ] Proveedor Ekomat
- [ ] Proveedor Pascal
- [ ] Proveedor Heimei
- [ ] Proveedor Cipta
- [ ] Carga o lectura de Excel
- [ ] Validacion de datos
- [ ] Tabla de lineas
- [ ] Errores M3
- [ ] Datos faltantes
- [ ] Resultado calculado
- [ ] Exportacion Excel
- [ ] Historico de calculos
- [ ] Acceso a constantes del negocio

Flujo base:

- [ ] Elegir proveedor
- [ ] Cargar pedido
- [ ] Validar datos
- [ ] Corregir o marcar errores
- [ ] Calcular
- [ ] Revisar resultado
- [ ] Exportar
- [ ] Registrar log si afecta datos

Pendiente de decidir:

- [ ] Guardar historico completo de pedidos calculados
- [ ] Asociar calculos a proveedor y fecha
- [ ] Permitir plantillas por proveedor

## WooCommerce

Ubicacion propuesta: Gestion > WooCommerce

Debe contener:

- [ ] Estado de conexion WooCommerce
- [ ] Sincronizar productos desde WooCommerce
- [ ] Importar producto Woo concreto a Supabase
- [ ] Comparar local / Supabase / Woo
- [ ] Detectar diferencias
- [ ] Preview de sincronizacion
- [ ] Ver precio actual Woo
- [ ] Ver sale_price activo
- [ ] Revisar variaciones
- [ ] Incidencias de sincronizacion
- [ ] Logs de operaciones Woo

Regla de separacion:

- [ ] Cambio de Precios prepara, aprueba y publica precios.
- [ ] WooCommerce gestiona estado, comparacion, importacion y sincronizacion de tienda.

## Proveedores

Ubicacion propuesta: Gestion > Proveedores

Debe contener:

- [ ] Ficha de proveedor
- [ ] Ekomat
- [ ] Pascal
- [ ] Heimei
- [ ] Cipta
- [ ] Especialidad
- [ ] Notas operativas
- [ ] Ultimo pedido
- [ ] Acceso directo a Calcular Pedido
- [ ] Futuras condiciones comerciales
- [ ] Contactos
- [ ] Documentos o plantillas

Pendiente de decidir:

- [ ] Que datos son configuracion y que datos son informacion operativa
- [ ] Si los proveedores se editan desde UI o quedan fijos en v1

## Informes

Ubicacion propuesta: Gestion > Informes

Debe contener:

- [ ] Informe de propuesta de precios
- [ ] Informe de coste de pedido
- [ ] Informe de inventario
- [ ] Informe de incidencias WooCommerce
- [ ] Informe de auditoria/logs
- [ ] Filtros por fecha
- [ ] Filtros por modulo
- [ ] Preview
- [ ] Exportar Excel
- [ ] Exportar PDF
- [ ] Historico de exportaciones

Pendiente de decidir:

- [ ] Que informes son obligatorios para v1
- [ ] Que exportaciones deben dejar log

## Configuracion

Ubicacion propuesta: Sistema > Configuracion

Pestanas propuestas:

- [ ] Generales
- [ ] Calculos
- [ ] Seguridad

Debe contener:

- [ ] Entorno activo
- [ ] Modo supabase_guarded
- [ ] Rol local fallback
- [ ] Machine name
- [ ] Rutas de base local
- [ ] Conexiones Supabase
- [ ] Conexiones WooCommerce
- [ ] Constantes del negocio
- [ ] Umbrales de bajada de precio
- [ ] Backups
- [ ] Reglas de permisos

Reglas:

- [ ] Cambios sensibles requieren preview
- [ ] Cambios sensibles dejan audit log
- [ ] Cambios que afecten calculos deben ser trazables

## Seguridad / Logs

Ubicacion propuesta: Sistema > Seguridad / Logs

Debe contener:

- [ ] Audit logs locales
- [ ] Audit logs cloud
- [ ] Operation snapshots
- [ ] Rollback desde snapshot
- [ ] Preview de rollback
- [ ] Locks locales
- [ ] Locks online RPC
- [ ] Diagnostico local
- [ ] Diagnostico cloud sin login
- [ ] Diagnostico cloud con login
- [ ] Estado operativo Supabase
- [ ] Herramientas admin
- [ ] Limpieza de datos TEST
- [ ] Backups y restauracion si se decide ubicar aqui

Flujo rollback:

- [ ] Listar snapshots
- [ ] Elegir operation_id
- [ ] Generar preview
- [ ] Confirmar REVERTIR
- [ ] Aplicar Supabase
- [ ] Guardar snapshot/log de rollback
- [ ] Mostrar resultado

Roles:

- [ ] Admin: acceso completo
- [ ] Worker: acceso limitado o solo trazabilidad propia

## Login y permisos

No es una opcion del menu, pero condiciona toda la UI.

Debe contener:

- [ ] Popup antes de mostrar ERP
- [ ] Usuario
- [ ] Contrasena
- [ ] Boton Aceptar
- [ ] Boton Cancelar
- [ ] Enter para aceptar
- [ ] Escape para cancelar
- [ ] Popup de validando usuario
- [ ] Lectura de rol cloud
- [ ] Registro de dispositivo visto
- [ ] Topbar con Online + rol
- [ ] Ocultar modulos no permitidos
- [ ] Bloquear herramientas si no hay sesion

## Estados oficiales

- [ ] OK
- [ ] Info
- [ ] Warning
- [ ] Error
- [ ] Critical

Uso:

- [ ] Dashboard
- [ ] Tablas
- [ ] Chips
- [ ] Previews
- [ ] Logs
- [ ] Validaciones

Regla:

- [ ] Critical bloquea siempre la operacion completa.

## Acciones criticas

Checklist obligatorio:

- [ ] Preparar datos
- [ ] Validar
- [ ] Preview
- [ ] Confirmacion
- [ ] Ejecucion protegida
- [ ] Resultado visible
- [ ] Audit log
- [ ] Snapshot cuando aplique

Acciones criticas identificadas:

- [ ] Publicar precio WooCommerce
- [ ] Rollback
- [ ] Cambio stock interno
- [ ] Migracion SQLite a Supabase
- [ ] Importacion masiva
- [ ] Sincronizacion masiva WooCommerce
- [ ] Cambios de constantes sensibles
- [ ] Restaurar backup

## Modulos futuros a reservar

Ideas para no cerrar la arquitectura:

- [ ] Pedidos
- [ ] Clientes
- [ ] Compras
- [ ] Ventas
- [ ] Facturacion
- [ ] Tareas internas
- [ ] Documentos
- [ ] Incidencias
- [ ] Analitica
- [ ] Integraciones externas

## Tabla de decision manual

Usar esta tabla para marcar a mano en el PDF.

Modulo / funcion:

Ubicacion final:

Rol Admin:

Rol Worker:

Prioridad: Alta / Media / Baja

Estado: Implementado / Parcial / Pendiente / Futuro

Accion critica: Si / No

Necesita preview: Si / No

Necesita audit log: Si / No

Notas:

## Orden recomendado para implementar UI real

- [ ] Cerrar estructura del menu lateral
- [ ] Definir permisos por modulo
- [ ] Conectar Dashboard a diagnosticos reales
- [ ] Conectar Inventario en modo lectura
- [ ] Conectar Cambio de Precios en modo lectura/propuesta
- [ ] Conectar Seguridad / Logs en modo lectura
- [ ] Activar acciones con preview y confirmacion
- [ ] Migrar Calcular Pedido a modulo ERP
- [ ] Refinar Informes y Proveedores
- [ ] Preparar modulos futuros

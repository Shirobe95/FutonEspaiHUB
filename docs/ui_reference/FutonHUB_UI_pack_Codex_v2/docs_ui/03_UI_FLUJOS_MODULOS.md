# FutonHUB UI - Flujos por módulo para Codex / Super Codi

## 1. Dashboard

Vista de entrada del ERP.

Objetivo:

- estado general
- alertas
- accesos rápidos
- visión de lo que no está bien

Debe ser limpio y directo.

## 2. Inventario

Pantalla principal:

- barra de búsqueda superior
- botón Exportación de Inventario
- tabla de inventario a la izquierda
- panel de detalles a la derecha

Tabla:

- ID
- Nombre
- Precio
- Stock
- Estado

Panel de detalle:

- información con scroll
- botones fijos abajo:
  - Abrir detalle completo
  - Agregar a Propuesta de precios

Detalle completo:

- modal grande
- datos completos a la izquierda
- gráficos a la derecha:
  - historial de precios
  - historial de stock

Agregar a propuesta:

- abre popup
- opciones:
  - Añadir a Nueva Propuesta
  - Añadir a Propuesta Existente

## 3. Cambio de Precios / Propuestas guardadas

Pantalla:

- búsqueda arriba
- listado de propuestas guardadas a la izquierda
- detalle de propuesta a la derecha

Listado:

- columnas alineadas:
  - Propuesta
  - Items
  - Suben
  - Bajan
  - Cambio
  - Estado

Detalle:

- info con scroll
- botones fijos abajo:
  - Modificar
  - Aceptar propuesta
  - Rechazar propuesta

Items del detalle:

- ID
- Nombre
- precio anterior
- precio nuevo
- indicador:
  - verde si sube
  - rojo si baja
  - azul si se mantiene

## 4. Modificar propuesta

Misma plantilla para:

- nueva propuesta
- modificar propuesta existente

Panel izquierdo:

- búsqueda de items
- tabla de items:
  - ID
  - Nombre
  - Precio
- pie de tabla:
  - subida %
  - subida exacta
  - Añadir

Variaciones:

- tabla de variaciones
- pie:
  - subida %
  - subida exacta
  - Añadir
  - Añadir Todas Variaciones

Panel derecho:

- nombre de propuesta
- items incluidos
- cada item:
  - ID + nombre arriba
  - precio antiguo, precio nuevo e indicador abajo
  - botones arriba derecha:
    - Modificar
    - Borrar

Acciones abajo:

- Cancelar
- Guardar cambios

Regla:

- usar subida en % o subida exacta, no ambas a la vez.

## 5. Pedidos

Pantalla principal:

- izquierda:
  - proveedores usados como acceso rápido
  - pedidos en marcha
- derecha:
  - detalle del pedido seleccionado

Importante:

- Esto no significa que Proveedores sea un módulo independiente.
- Proveedores queda fuera del menú.
- Las tarjetas de proveedor en Pedidos sirven solo para iniciar cálculo de pedido.

Proveedores usados:

- Ekomat
- Pascal
- Heimei
- Otros / Cipta si aplica

Cada proveedor tiene:

- Calcular nuevo pedido

Detalle rápido:

- ID pedido
- proveedor
- fecha
- resumen
- items:
  - ID
  - nombre
  - cantidad
  - coste final

Botones:

- Detalles
- Recibido
- Borrar pedido
- Exportar

Recibido:

- popup
- recibido completo
- recibido parcial
- tabla con:
  - recibido
  - ID
  - nombre
  - cantidad pedida
  - cantidad recibida

Detalle completo:

- popup grande
- nombre de pedido
- proveedor
- tabla completa de cálculos por item
- indicadores del pedido:
  - Precio en Euros
  - Precio en Dólares
  - Aranceles
  - Factura transporte
  - Manipulación
  - Financiación
  - Varios
  - Coste total pedido

## 6. Calcular nuevo pedido

Esta ventana se abre desde un proveedor ya seleccionado.

No mostrar selector de proveedor dentro de la ventana.

Carga:

- botón Cargar pedido
- nombre de archivo
- tipo de archivo

Entradas:

- dependen del proveedor
- Heimei / tatamis usa:
  - Precio en Dólares
  - Precio pagado en Euros
  - Factura transporte
  - Derechos aranceles
  - % Transporte
  - % Descarga
  - % Varios
  - % Manipulación
  - % Financiación
  - Tipo cálculo

Derecha:

- tabla grande con valores calculados
- resumen inferior

Acciones:

- Calcular pedido
- Recalcular
- Guardar pedido
- Exportar
- Cancelar

## 7. WooCommerce

Objetivo:

WooCommerce es una pantalla de mantenimiento y actualización de base de datos local desde WooCommerce.

No es principalmente una pantalla para publicar cambios en la web.

Funciones:

- Leer WooCommerce
- Detectar cambios respecto a base local
- Actualizar base de datos local
- Auto-clasificar
- Revisar incidencias

Tabla:

- ID local
- ID Woo
- Nombre
- Campo
- Base local
- WooCommerce
- Diferencia
- Clasificación
- Acción
- Estado

Detalle lateral:

- base local
- WooCommerce
- clasificación
- acción
- estado

Acciones:

- Actualizar base de datos
- Auto-clasificar
- Revisar manual

## 8. Informes / Exportaciones

Objetivo:

Centro de salida del ERP.

Debe mostrar:

- qué se exportó
- cuándo
- desde qué módulo
- por quién
- en qué formato
- con qué filtros
- si salió bien o falló

Pantalla:

- búsqueda arriba
- botón Nueva exportación
- tabla de registro a la izquierda
- detalle de exportación a la derecha

Registro:

- Fecha / Hora
- Tipo
- Módulo
- Formato
- Usuario / Rol
- Estado
- Archivo

Detalle:

- archivo
- módulo
- tipo
- formato
- usuario
- fecha
- estado
- filas
- referencia
- filtros usados
- columnas incluidas
- ruta interna

Nueva exportación:

- popup
- módulo
- tipo de informe
- formato
- nombre de archivo
- opciones:
  - incluir filtros aplicados
  - registrar en logs
  - incluir incidencias
  - abrir al generar

## 9. Seguridad / Logs

Objetivo:

Caja negra del ERP.

Pantalla:

- búsqueda de logs
- filtros por módulo/nivel
- resumen de eventos
- tabla de eventos
- botón Ver detalles

Tabla:

- Fecha / Hora
- Nivel
- Módulo
- Acción
- Usuario / Rol
- Resultado
- Referencia

Detalle de evento:

- popup grande
- resumen del evento
- lista de cambios:
  - item/referencia
  - campo
  - estado anterior
  - estado cambiado
  - resultado
  - nivel
- payload técnico
- botones:
  - Ver snapshot
  - Exportar detalle
  - Cerrar

## 10. Configuración

Configuración es el motor del ERP.

Solo tres pestañas:

- Generales
- Cálculos
- Seguridad

Generales:

- Entorno
- Modo
- Rol actual
- Tema
- Ruta base local
- Estado conexiones:
  - SQLite local
  - Supabase
  - WooCommerce
  - Backups

Cálculos:

- constantes del negocio:
  - IMPORTE_DESCARGA_MT
  - PC_GASTOS_MANIPULACION
  - PC_GASTOS_FINANCIACION
  - IMPORTES_VARIOS
  - COSTE_TOTAL_DESCARGA_FUTONES_IVA
  - COSTE_DESCARGA_FUTONES_UNIDAD
  - IVA_RECARGO_EQUIVALENCIA
  - COSTE_DIARIO_ALMACENAJE_M3

Seguridad:

- preview interno obligatorio
- bloquear precios en 0
- confirmación por palabra
- cancelar operación ante Critical
- backups automáticos
- registro de operaciones

Cambios sensibles deben dejar log.

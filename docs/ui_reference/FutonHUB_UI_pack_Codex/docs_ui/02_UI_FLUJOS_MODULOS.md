# FutonHUB UI - Flujos por módulo para Codex / Super Codi

## 1. Inventario

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

---

## 2. Propuestas guardadas

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

---

## 3. Modificar propuesta

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

---

## 4. Pedidos

Pantalla principal:

- izquierda:
  - proveedores
  - pedidos en marcha
- derecha:
  - detalle del pedido seleccionado

Proveedores:

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

---

## 5. Calcular nuevo pedido

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

---

## 6. WooCommerce

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

---

## 7. Configuración

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

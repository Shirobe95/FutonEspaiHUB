# FutonHUB UI v1 - Definiciones para Codex

## Objetivo

Este documento define la base visual, funcional y de navegación de la futura UI de **FutonHUB**.

Codex debe usarlo junto al HTML maestro interactivo ya entregado:

```text
futonhub_sistema_visual_v1_interactivo.html
```

Ese HTML es una referencia visual y de interacción. No debe copiarse como código final sin criterio. La prioridad es respetar estructura, flujos, nomenclatura, seguridad y patrones.

---

## Regla principal

**No tocar Main directamente para rediseñar.**

El diseño debe trabajarse en una rama, copia o espacio aislado.

```text
Main = fuente funcional estable
UI v1 = capa visual y patrones
Integración = gradual y protegida
```

---

## Objetivo de la UI

FutonHUB debe sentirse como un **mini ERP privado, limpio, seguro y operativo**.

Debe transmitir:

- orden
- control
- seguridad
- trazabilidad
- claridad visual
- facilidad de revisión
- confianza antes de ejecutar operaciones críticas

---

## Estilo visual general

### Look & feel

- ERP moderno.
- Fondo gris muy claro.
- Tarjetas blancas.
- Bordes suaves.
- Sombras ligeras.
- Mucho espacio respirable.
- Colores suaves.
- Color fuerte solo para estados, foco o acciones principales.

### Paleta conceptual

```text
Fondo principal: gris claro / slate suave
Cards: blanco
Texto principal: gris oscuro
Texto secundario: gris medio
Color principal: índigo / azul suave
OK: verde suave
Info: azul suave
Warning: ámbar suave
Error: naranja suave
Critical: rojo suave pero claro
```

### Evitar

- Saturar con colores.
- Botones rojos salvo acciones peligrosas o bloqueadas.
- Gráficas decorativas sin utilidad.
- Tablas con demasiadas columnas visibles.
- Aspecto de web comercial. Esto es una herramienta interna tipo ERP.

---

## Layout global

### Escritorio

```text
Sidebar lateral izquierda fija
Topbar superior
Área principal de contenido
```

### Móvil

```text
Botón hamburguesa
Sidebar lateral deslizante
Contenido principal con scroll
```

La arquitectura sigue siendo lateral aunque el menú se oculte en móvil.

---

## Menú lateral definitivo

Usar esta nomenclatura visible para el usuario final.

### Principal

```text
Dashboard
```

### Operaciones

```text
Inventario
Cambio de Precios
Calcular Pedido
```

### Gestión

```text
WooCommerce
Proveedores
Informes
```

### Sistema

```text
Configuración
Seguridad / Logs
```

---

## Razón de la organización

### Operaciones

Procesos operativos directos:

- revisar productos
- cambiar precios
- calcular pedidos

### Gestión

Administración de entidades o sistemas:

- WooCommerce como gestión de lo que está en la web
- proveedores
- informes/exportaciones

### Sistema

Configuración, trazabilidad y seguridad:

- ajustes
- reglas
- logs
- backups
- validaciones

---

## Estados oficiales

La UI debe usar estos 5 estados:

| Estado | Significado | Bloquea |
|---|---|---|
| OK | Todo correcto | No |
| Info | Información útil | No |
| Warning | Requiere atención | No, salvo regla específica |
| Error | Problema funcional que impide completar parte del flujo | Puede bloquear el paso actual |
| Critical | Riesgo crítico | Sí, siempre |

### Reglas

- **Warning** informa y pide revisión.
- **Error** indica que algo funcional falta o está mal.
- **Critical** bloquea la operación completa.
- Si hay Critical, no se debe permitir aplicar cambios reales.
- Las operaciones críticas deben dejar log.

---

## Principio de seguridad visual

Ninguna operación crítica debe ejecutarse con un clic accidental.

### Flujo obligatorio

```text
Preparar datos
Validar
Preview
Confirmación
Ejecución protegida
Resultado
Log
```

### Operaciones sensibles

- aplicar precios en WooCommerce
- cambiar stock
- importar datos masivos
- sincronizar cambios con WooCommerce
- recalcular pedidos con efectos sobre datos locales
- actualizar M3 local
- migraciones o cambios de base de datos

### Confirmación fuerte

Para operaciones críticas considerar confirmación explícita:

```text
Escribir CONFIRMAR
```

Si existe Critical, ni siquiera la confirmación debe permitir continuar.

---

## Patrón base de pantalla

Siempre que sea posible:

```text
Título del módulo
Subtítulo claro
Acciones principales arriba a la derecha
Bloques de resumen
Tabla o contenido principal
Panel lateral o bloque secundario de detalle
Acciones protegidas
Estados visibles
```

---

## Componentes reutilizables sugeridos

```text
Sidebar
Topbar
PageHeader
SummaryCard
StatusChip
DataTable
DetailPanel
FilterBar
ActionPanel
FlowSteps
Tabs
ConfirmModal
LoadingOverlay
EmptyState
ErrorState
ExportPanel
```

---

## Botones

### Tipos

```text
Primario
Secundario
Peligroso
Bloqueado
Fantasma / ligero
```

### Reglas

- Primario: índigo o color principal.
- Secundario: blanco con borde.
- Peligroso: rojo, escaso y separado.
- Bloqueado: visualmente claro como no ejecutable.
- No mezclar acciones normales y críticas sin separación visual.

---

## Chips de estado

Los estados deben verse como píldoras consistentes:

```text
OK
Info
Warning
Error
Critical
```

---

# Módulos

## Dashboard

### Objetivo

Portada de control del HUB.

No debe ser una pantalla pesada de trabajo. Debe mostrar rápidamente:

- qué está bien
- qué requiere revisión
- qué está bloqueado
- qué acciones rápidas existen

### Debe mostrar

```text
Alertas críticas
Warnings activos
Pendiente de sincronizar
Sistema listo
Estado del sistema
Acciones rápidas
Salud general del HUB
Última actividad
```

### Acciones rápidas

```text
Calcular pedido
Crear propuesta
Preview Woo
Exportar informe
```

---

## Inventario

### Objetivo

Revisar productos, stock, precios y datos internos.

### Patrón

```text
Filtros superiores
Tabla principal
Panel derecho de detalle
Acciones seguras
```

### Columnas principales

```text
Código
Nombre
Stock
Precio
Estado
```

### Datos secundarios

Deben ir al detalle lateral:

```text
Familia
Proveedor
M3
Variaciones
Historial
Estado de sincronización
Notas
```

### Acciones

```text
Abrir detalle completo
Añadir a propuesta
Ver historial
Exportar inventario
Sincronizar preview
```

Nada crítico debe ejecutarse directamente desde Inventario.

---

## Cambio de Precios

### Objetivo

Crear, validar, exportar, aprobar y aplicar propuestas de precios con seguridad.

### Flujo

```text
Buscar producto
Añadir a propuesta
Ver propuesta
Validar
Exportar Excel
Revisar / aprobar externamente
Importar aprobado
Generar preview final
Confirmar
Aplicar en WooCommerce
Guardar log
```

### Tabla de propuesta

```text
Código
Producto
Precio actual
Precio propuesto
Diferencia
Notas
Estado
```

### Reglas críticas

- Precio actual en 0 = Critical.
- Precio propuesto en 0 = Critical.
- Precio por debajo de margen mínimo = Warning o Error según regla.
- Si hay Critical, se bloquea toda la operación.
- El botón “Aplicar en WooCommerce” debe estar bloqueado si hay Critical.

---

## Calcular Pedido

### Nombre oficial en UI

```text
Calcular Pedido
```

No mezclar en el menú con “Cálculo de Costes”, aunque internamente pueda llamarse así.

### Objetivo

Calcular pedidos por proveedor desde Excel, validando datos antes de calcular.

### Flujo

```text
Elegir proveedor
Cargar Excel
Validar datos
Editar errores
Calcular
Revisar resultado
Exportar Excel
Actualizar datos locales si corresponde
```

### Proveedores iniciales

```text
Ekomat
Pascal
Heimei
```

### Particularidades

- Heimei puede usar precio_1 desde data.
- Algunos códigos especiales deben contar aunque parezcan excluibles.
- Fundas, toppers, almohadas u otros complementos pueden no contar en ciertas fórmulas.
- Los pedidos “a medida” deben marcarse claramente si no tienen datos suficientes.

### Tabla de pedido

```text
Código
Producto
Unidades
M3
Coste calculado
Estado
```

### Estados

- Falta M3 = Error.
- Producto no reconocido = Error o Warning según caso.
- Datos listos = OK.
- Producto no cuenta para fórmula = Info.

---

## WooCommerce

### Ubicación

WooCommerce pertenece a **Gestión**, no a Operaciones.

### Objetivo

Gestionar lo que está en la página de WooCommerce:

- sincronización
- comparación
- preview
- diferencias
- relación local/Woo

### No confundir

- **Cambio de Precios** prepara cambios de precio.
- **WooCommerce** gestiona el estado de la página, compara y sincroniza.

### Flujo

```text
Leer WooCommerce
Comparar con datos locales
Detectar diferencias
Generar preview
Validar riesgos
Confirmar
Aplicar cambios reales
Guardar log
```

### Tabla comparativa

```text
ID local
Producto
Campo
Valor local
Valor Woo
Acción sugerida
Estado
```

### Reglas

- No aplicar cambios sin preview.
- Mostrar claramente diferencias local/Woo.
- Exportar incidencias cuando sea necesario.
- Bloquear si hay Critical.

---

## Proveedores

### Objetivo

Gestionar información operativa de proveedores.

### Proveedores iniciales

```text
Ekomat
Pascal
Heimei
```

### Debe mostrar

```text
Nombre
Especialidad
Productos vinculados
Último pedido
Notas operativas
Estado
Acceso a calcular pedido
```

### Futuro crecimiento

Preparar para ampliar:

```text
contacto
condiciones de compra
histórico de pedidos
documentos
incidencias
lógica de precios
tiempos de entrega
```

---

## Informes

### Nombre oficial

```text
Informes
```

Puede incluir internamente exportaciones.

### Objetivo

Generar exportaciones limpias, trazables y útiles para revisión.

### Informes iniciales

```text
Propuesta de precios
Coste de pedido
Incidencias WooCommerce
Auditoría / logs
Inventario
```

### Debe mostrar

```text
tipos de informe
formatos disponibles
histórico de exportaciones
quién generó el archivo
cuándo se generó
destino o propósito
estado de exportación
```

### Formatos

```text
Excel
PDF
```

### Regla

Las exportaciones deben ser limpias, centradas, legibles y fáciles de compartir.

---

## Configuración

### Organización obligatoria

Configuración debe tener solo 3 pestañas principales:

```text
Generales
Cálculos
Seguridad
```

La idea es evitar mil pestañas. Si crecen más opciones, deben agruparse dentro de estas tres.

### Generales

```text
Nombre del entorno
Modo de trabajo
Rol por defecto
Tema visual
Conexiones visibles
Estado de Supabase
Estado de WooCommerce
Estado de SQLite local
```

### Cálculos

Debe incluir constantes del negocio:

```text
IMPORTE_DESCARGA_MT
PC_GASTOS_MANIPULACION
PC_GASTOS_FINANCIACION
IMPORTES_VARIOS
COSTE_TOTAL_DESCARGA_FUTONES_IVA
COSTE_DESCARGA_FUTONES_UNIDAD
IVA_RECARGO_EQUIVALENCIA
COSTE_DIARIO_ALMACENAJE_M3
```

Reglas:

- Debe poder editarse de forma clara.
- Debe haber Aceptar/Guardar y Cancelar.
- Cambios sensibles deben dejar log.
- El usuario debe entender que estos valores afectan cálculos.

### Seguridad

```text
Preview obligatorio
Bloqueo de precios 0
Confirmación por palabra
Cancelación de operación completa ante Critical
Margen mínimo de seguridad
Backups automáticos
Registro de operaciones
Exportación de auditoría
```

---

## Seguridad / Logs

### Objetivo

Ser la caja negra del HUB.

Debe permitir revisar:

```text
operaciones realizadas
errores
warnings
bloqueos
previews generados
exportaciones
sincronizaciones
backups
usuario responsable
fecha/hora
resultado
```

### Tabla de logs

```text
Fecha
Módulo
Operación
Resultado
Usuario
Detalle
Nivel
```

### Niveles

```text
OK
Info
Warning
Error
Critical
```

---

## Loading / estado de trabajo

Para operaciones pesadas o sensibles, la UI debe mostrar un estado claro.

### Debe hacer

```text
bloquear o proteger la interfaz
mostrar mensaje claro
evitar clics repetidos
indicar qué está haciendo
mostrar resultado al terminar
```

### Ejemplos

```text
Generando preview de WooCommerce...
Validando propuesta de precios...
Calculando pedido Heimei...
Exportando informe...
Guardando configuración...
```

---

## Reglas de integración futura con Main

### Fase 1

Crear componentes UI aislados o en rama separada.

### Fase 2

Mapear pantallas existentes de Main a módulos del diseño.

### Fase 3

Integrar visualmente sin cambiar lógica crítica.

### Fase 4

Conectar acciones reales una por una, con preview y logs.

### Fase 5

Probar flujos críticos con datos controlados.

---

## Prioridad técnica para Codex

### Primero

```text
Crear estructura:
Sidebar
Topbar
Content Area
Navegación interna
```

### Segundo

```text
Crear componentes reutilizables:
Cards
Tables
StatusChips
Buttons
Panels
Tabs
```

### Tercero

```text
Montar pantallas mockup:
Dashboard
Inventario
Cambio de Precios
Calcular Pedido
WooCommerce
Proveedores
Informes
Configuración
Seguridad / Logs
```

### Cuarto

```text
Sustituir datos mock por datos reales poco a poco
```

### Quinto

```text
Conectar acciones reales solo cuando estén protegidas
```

---

## Criterio de aceptación UI v1

La UI v1 se considera bien encaminada si:

```text
La navegación es clara
El menú está ordenado
Los nombres son consistentes
Las tablas son legibles
Los estados se entienden
Las acciones críticas están separadas
Hay preview antes de aplicar
Configuración usa solo 3 pestañas
WooCommerce está en Gestión
Cambio de Precios no se confunde con WooCommerce
Seguridad / Logs permite auditar el sistema
```

---

## Nota final para Codex

Este diseño debe tratarse como una **guía de producto**, no solo como HTML bonito.

El objetivo no es copiar píxel por píxel, sino respetar:

```text
estructura
nomenclatura
patrones
seguridad
flujo
claridad
modularidad
```

Super Codi debe priorizar estabilidad, limpieza e integración gradual.

```text
No romper Main.
No conectar operaciones críticas sin preview.
No ejecutar cambios reales sin validación.
No esconder errores.
No mezclar nombres internos con nombres visibles para usuario.
```

Plus ultra, pero con casco y cinturón.

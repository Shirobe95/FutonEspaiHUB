# FutonHUB · Auditoría funcional con lupa

**Versión auditada:** v61.2 `blackbox_verified`  
**Fecha:** 2026-06-14  
**Objetivo:** distinguir código operativo real, implementación parcial, interfaz visual, simulaciones y funciones no implementadas.  
**Regla de esta auditoría:** una pantalla, botón, mensaje o documento no demuestra que una función exista. Una función se considera completa únicamente cuando existe lógica conectada, persistencia verificable y una prueba de extremo a extremo.

---

## Estado de consolidacion Codex - 2026-06-15

Baseline funcional:

```text
v61.2 blackbox_verified
```

Checkpoint de partida en Git:

```text
v62.1 Codex Handoff
main: 6946d4e9091208b61a3f43d28721fe7cb57c2a14
```

Estado estructural actual:

```text
Corte 004B completado localmente
Corte funcional 004B: 6a1aa15b3e5ef5f984b49547b03919dac2433877
Rama: refactor/modularizacion-v1
Estado push: sincronizado con origin/refactor/modularizacion-v1
```

Suite automatizada actual:

```text
python -m unittest discover -s GestorWoo\tests -v
Ran 53 tests in 0.095s
OK
```

Evolucion de modulos extraidos:

| Corte | Archivo | Responsabilidad |
|---|---|---|
| 001 | `shared_ui.py` | constantes visuales, dataclasses UI temporales, helpers UI compartidos y overlay |
| 002 | `shell.py` | `NAV_ITEMS`, shell, sidebar, topbar, cabecera, cambio de vista y resaltado |
| 003 | `dashboard.py` | vista Dashboard, KPIs, tarjetas, recoleccion y transformacion de datos del Dashboard |
| 004A | `inventory_list.py` | listado de Inventario, busqueda, refresco, seleccion y carga de filas |
| 004B | `inventory_detail.py` | panel de detalle de Inventario e historial de precio/stock |

`prototype.py` sigue siendo el adaptador principal y conserva los modulos funcionales no extraidos. No se han modificado servicios, esquemas, reglas comerciales ni entrypoint oficial durante estos cortes.

---

## 1. Escala de estado

| Estado | Significado |
|---|---|
| **IMPLEMENTADO Y PROBADO E2E** | Código conectado y prueba real completada contra Supabase/Woo/archivo según corresponda. |
| **IMPLEMENTADO, FALTA PRUEBA E2E** | Existe lógica real, pero no hay evidencia suficiente de una prueba completa reciente. |
| **IMPLEMENTADO PARCIALMENTE** | Parte del flujo funciona, pero faltan ramas, verificaciones, rollback, permisos o persistencia. |
| **SOLO INTERFAZ / MOCK** | La UI existe, pero usa datos estáticos, botones sin `command` o mensajes de “acción visual”. |
| **LEGACY / PARALELO** | Existe lógica antigua fuera del flujo ERP principal. Puede funcionar, pero no garantiza integración con la UI actual. |
| **SIMULACIÓN / TEST** | Diseñado para pruebas, no para operación real del negocio. |
| **NO IMPLEMENTADO / ROTO** | Falta lógica o existe un fallo conocido que impide usar la función. |

---

## 2. Resultado ejecutivo

### Confirmado como funcional

- Login Supabase y sesión con rol.
- Lectura de inventario desde Supabase.
- Sincronización y autoclasificación WooCommerce.
- Enlace de productos, variaciones, alias, packs y componentes Woo con Inventario.
- Búsqueda de packs por componentes y visualización de sus contenidos.
- Flujo de propuestas de precio.
- Publicación del **precio efectivo** en WooCommerce.
- Lectura posterior de Woo para comprobar el precio publicado.
- Persistencia verificada de audit log y snapshot antes de declarar éxito.
- Rollback real del precio Woo desde snapshot.
- Edición de campos internos de Inventario sin escritura automática en Woo.
- Baseline v61.2: tests automatizados existentes **11/11 pasan**.
- Rama actual tras Corte 004B: **53 tests pasan**.

### Módulos que no deben declararse completos todavía

- Dashboard: mezcla datos reales con presentación que aún requiere pruebas de consistencia.
- Pedidos: tiene mucha lógica real, pero necesita una campaña E2E completa por proveedor, importación, cálculo, guardado, recepción, stock y coste ponderado.
- Precio Proveedores: lógica conectada, sin prueba E2E documentada en esta auditoría.
- Informes / Exportaciones: la pantalla principal es mayoritariamente **mock**.
- Configuración / Generales: **solo interfaz**.
- Configuración / Seguridad: interruptores visuales sin persistencia.
- Backups y restauración general: existe lógica legacy/local, pero no está integrada y validada como módulo ERP moderno.
- Usuarios, permisos y administración de dispositivos: backend/tablas existen, pero no hay módulo ERP completo de gestión.
- Escritura general Inventario → Woo: no existe como sincronización automática universal. Solo están confirmados flujos explícitos y protegidos, especialmente precios.

---

# 3. Auditoría por módulo

## 3.1 Arranque y estructura del proyecto

### Qué partes tiene

- `Abrir ERP.bat`
- `abrir_futon_espai.py`
- `GestorWoo/gestorwoo.py`
- `GestorWoo/FutonEspaiLauncher.py`
- Paquete principal bajo `GestorWoo/src/`
- Herramientas legacy en `CalculoCoste/`

### Qué debería hacer

- Arrancar siempre la versión oficial del ERP.
- Resolver rutas correctamente sin depender del directorio actual.
- Cargar entorno, dependencias y configuración.
- Mostrar errores de arranque comprensibles.
- Evitar que el usuario ejecute módulos sueltos y termine en una versión paralela.

### Qué hace realmente

- El flujo operativo acordado es abrir mediante `Abrir ERP.bat`.
- Existe más de un lanzador histórico y más de una aplicación/UI en el repositorio.
- La aplicación ERP actual se concentra en `futonhub/ui/erp/prototype.py`, aunque el nombre interno todavía diga “prototype”.
- Permanecen módulos legacy y lanzadores antiguos que pueden confundir a Codex o a un mantenedor.

### Estado

**IMPLEMENTADO, CON DEUDA ESTRUCTURAL.**

### Riesgos / trabajo para Codex

1. Definir un único entrypoint canónico.
2. Renombrar `prototype.py` cuando deje de ser prototipo.
3. Marcar o mover a `legacy/` los lanzadores y UIs antiguas.
4. Añadir comprobación de versión visible en la ventana y logs.
5. Añadir smoke test del arranque mediante el `.bat` oficial.

---

## 3.2 Autenticación, roles y sesión

### Qué partes tiene

- Login Supabase desde la UI ERP.
- `profiles`, roles `admin` y `worker`.
- Restricción visual de Seguridad / Logs para admin.
- Servicios de autenticación y cliente Supabase.
- RLS/RPC en scripts SQL.

### Qué debería hacer

- Autenticar al usuario.
- Leer perfil, rol y estado activo.
- Bloquear módulos y operaciones no autorizadas.
- Evitar que ocultar un botón sea la única barrera.
- Registrar identidad, rol y máquina en operaciones sensibles.

### Qué hace realmente

- El login y la sesión online funcionan.
- Seguridad / Logs comprueba rol admin en la UI.
- Los servicios sensibles aplican comprobaciones adicionales en varios puntos.
- Las operaciones dejan usuario, email, rol y máquina en caja negra.
- No existe una pantalla ERP completa para administrar usuarios, roles, dispositivos y permisos.

### Estado

**IMPLEMENTADO OPERATIVAMENTE; ADMINISTRACIÓN INCOMPLETA.**

### Pruebas necesarias

- Worker intenta publicar en Woo y debe ser bloqueado en backend.
- Worker intenta leer logs/snapshots y debe ser rechazado por RLS/RPC.
- Usuario inactivo intenta iniciar sesión.
- Sesión expirada durante una operación.

---

## 3.3 Dashboard

### Qué partes tiene

- Actividad reciente.
- Pedidos pendientes.
- Propuestas pendientes.
- Estado de sistemas.
- Accesos a módulos.

### Qué debería hacer

- Resumir datos reales y actuales.
- Mostrar pendientes accionables, no ruido informativo.
- Indicar claramente errores de carga.
- No mostrar números decorativos o estados inventados.

### Qué hace realmente

- Consulta pedidos, propuestas y logs reales mediante servicios cloud.
- Construye tarjetas de atención y permite navegar al módulo relacionado.
- Parte del estado de sistemas y presentación necesita verificación para asegurar que todos los indicadores provienen de comprobaciones reales y no de etiquetas fijas.

### Estado

**IMPLEMENTADO, FALTA PRUEBA E2E DE CONSISTENCIA.**

### Prueba propuesta

Crear un pedido pendiente, una propuesta pendiente y un error de operación; recargar Dashboard y comprobar que los tres aparecen y desaparecen al resolverlos.

---

## 3.4 Inventario

### Qué partes tiene

- Lectura y búsqueda desde Supabase.
- Tabla de inventario.
- Diagnóstico de estados.
- Creación manual de artículo.
- Detalle completo.
- Edición de campos internos.
- Stock tienda y almacén.
- Historial.
- Packs y componentes.
- Exportación del inventario visible.
- Envío de un item hacia Cambio de Precios.

### Qué debería hacer

- Ser el centro operativo interno.
- Separar campos internos de campos Woo.
- Validar y previsualizar cambios sensibles.
- Registrar log y snapshot.
- Mostrar packs y relaciones sin recursión ni nombres vacíos.
- Permitir trabajar con stock sin modificar Woo accidentalmente.

### Qué hace realmente

- Lee, busca y lista datos reales desde Supabase.
- Crea artículos reales en `inventory_items` con preview y `operation_id`.
- Edita campos internos mediante servicios reales.
- Gestiona stock interno con preview, log y snapshot.
- Muestra contenidos de packs desde `inventory_item_components` y vistas de búsqueda.
- Los 1.116 componentes existentes quedaron resueltos en la campaña Woo.
- Puede llevar un item a una propuesta de precio.
- La exportación visible genera un archivo real.
- **Editar un item no implica publicar automáticamente esos campos en Woo.** La UI incluso indica en logs que Woo no fue tocado.

### Estado

**IMPLEMENTADO Y PARCIALMENTE PROBADO E2E.**

### Límites reales

- No hay sincronización universal Inventario → Woo para nombre, SKU, atributos, stock, familia o materiales.
- Los campos de clasificación interna no equivalen necesariamente a atributos públicos de Woo.
- Debe definirse una matriz explícita de campos publicables, dirección de sincronización y permisos.

### Pruebas pendientes

1. Crear artículo manual y comprobar búsqueda, detalle, log y snapshot.
2. Editar cada campo permitido y verificar persistencia.
3. Cambiar stock tienda/almacén y restaurarlo desde snapshot.
4. Exportar con filtros y comparar filas/columnas.
5. Probar concurrencia de dos usuarios sobre el mismo item.

---

## 3.5 WooCommerce: sincronización, autoclasificación y enlaces

### Qué partes tiene

- Lectura de productos y variaciones Woo.
- Autoclasificador.
- Comparativa Woo ↔ Supabase.
- Enlace por `woo_id`, SKU y alias.
- Enlace manual.
- Edición manual de clasificación.
- Packs y relaciones de componentes.
- Exportación JSON preview.
- Exclusión de padres variables informativos y productos test.

### Qué debería hacer

- Leer Woo sin escribir durante la sincronización.
- Clasificar sin inventar datos peligrosos.
- Encontrar o crear una identidad interna estable.
- Separar casos operativos de padres variables informativos.
- No generar conflictos falsos cuando el SKU operativo pertenece a una variación.

### Qué hace realmente

- La sincronización final analizó 778 elementos Woo.
- Resultado validado: 646 enlazados operativos, 0 sin enlace operativo y 0 críticos.
- Los productos de prueba quedan excluidos del seguimiento operativo.
- Los padres variables sin SKU quedan informativos.
- Los SKU compartidos padre/variación se asignan operativamente a la variación.
- Los packs y componentes están relacionados en Supabase.
- El preview y JSON son de solo lectura.

### Estado

**IMPLEMENTADO Y PROBADO E2E PARA LECTURA/ENLACE.**

### Deuda pendiente

- Quedan warnings de calidad de clasificación, no de enlace.
- Debe existir una cola de revisión manejable para familia, materiales, medida y packs.
- Deben documentarse formalmente las reglas de autoclasificación y sus prioridades.

---

## 3.6 Cambio de Precios

### Qué partes tiene

- Nueva propuesta.
- Selección de items/variaciones reales.
- Edición de líneas.
- Validación y preview.
- Aprobación/rechazo.
- Preview Woo.
- Publicación protegida.
- Confirmación por palabra.
- Lectura posterior de Woo.
- Actualización de Supabase.
- Log y snapshot.
- Rollback real.

### Qué debería hacer

- Trabajar con el precio efectivo visible al cliente.
- Bloquear precios inválidos y bajadas críticas.
- Diferenciar aprobar de publicar.
- No declarar éxito hasta verificar Woo.
- No tocar Supabase como publicado si Woo falla.
- Crear caja negra verificable.
- Restaurar el precio anterior desde snapshot.

### Qué hace realmente

- La propuesta se crea y se valida contra items reales.
- La publicación distingue `regular_price` y `sale_price`.
- Con rebaja activa, modifica el precio rebajado para alcanzar el precio efectivo propuesto.
- Después de escribir, vuelve a leer Woo y compara el precio efectivo.
- Snapshot y audit log deben existir antes de declarar éxito; v61.2 verifica persistencia.
- El rollback restaura `regular_price` y `sale_price`, verifica Woo y marca la propuesta `rolled_back`.
- Flujo validado manualmente con la variación SKU `0201014`: 128 → 138 → rollback a 128.

### Estado

**IMPLEMENTADO Y PROBADO E2E.**

### Riesgos aún recomendados para pruebas

- Precio nuevo superior al `regular_price` existente.
- Eliminar una rebaja y pasar a precio normal.
- Woo devuelve 200 pero un plugin reescribe el precio después.
- Variación sin precio previo.
- Producto simple.
- Publicación interrumpida entre Woo y Supabase.
- Dos admins publicando la misma propuesta.

---

## 3.7 Pedidos a proveedor

### Qué partes tiene

- Listado de pedidos Supabase.
- Creación y actualización de borradores.
- Importación Excel.
- Importación PDF.
- Editor de líneas.
- Resolución de precios proveedor.
- Cálculos de coste, M3, descarga, manipulación, financiación, IVA y almacenaje.
- Indicadores y tabla de fórmulas.
- Guardado del cálculo.
- Exportación Excel de auditoría.
- Cancelación/borrado lógico.
- Recepción de pedido.
- Actualización de inventario y coste ponderado.

### Qué debería hacer

- Importar un pedido sin perder líneas.
- Detectar duplicados y campos faltantes.
- Resolver precios correctos por proveedor.
- Aplicar constantes reales desde Supabase.
- Reproducir las fórmulas legacy de negocio.
- Guardar una fotografía calculable y auditable.
- Recibir el pedido una sola vez.
- Actualizar stock y coste ponderado de forma transaccional.

### Qué hace realmente

- Existe una cantidad importante de lógica real en UI y servicios cloud.
- Los servicios implementan crear, actualizar, recalcular, cancelar, previsualizar recepción y recibir.
- La UI importa Excel/PDF, calcula en memoria, guarda y exporta Excel.
- Existen reglas específicas para artículos que cuentan como descarga.
- El proyecto contiene documentación de muchas iteraciones y correcciones.
- Sin embargo, no hay en esta auditoría evidencia de una campaña E2E reciente que cubra todo el circuito con datos reales y comprobación de inventario/coste después de recibir.

### Estado

**IMPLEMENTADO, FALTA AUDITORÍA E2E COMPLETA.**

### Prueba obligatoria antes de cerrar

1. Crear pedido desde Excel conocido.
2. Revisar cada línea importada.
3. Confirmar precios proveedor y constantes.
4. Comparar cálculos contra cálculo manual/Excel histórico.
5. Guardar borrador y reabrirlo.
6. Modificar una línea y recalcular.
7. Exportar y comprobar fórmulas/formatos.
8. Recibir parcialmente si se soporta; si no, documentar que solo admite recepción total.
9. Verificar stock y coste ponderado antes/después.
10. Intentar recibir dos veces y comprobar bloqueo.
11. Verificar log, snapshot y rollback soportado.

---

## 3.8 Precio Proveedores

### Qué partes tiene

- Lista de items de inventario.
- Precio proveedor principal.
- Precio Pascal.
- Búsqueda y estados visuales.
- Edición con motivo.
- Guardado Supabase.
- Log y snapshot.
- Herramientas de migración y diagnóstico.

### Qué debería hacer

- Mantener precios de compra separados del precio de venta.
- Resolver correctamente proveedor y moneda.
- Alimentar el cálculo de pedidos.
- Registrar cambios y permitir recuperación.

### Qué hace realmente

- La pantalla usa servicios reales y carga items de Supabase.
- `update_supplier_price_inventory_item` guarda cambios con motivo.
- La UI declara y solicita confirmación de log + snapshot.
- Existen diagnósticos y migración desde precios locales.
- No consta prueba E2E reciente en esta auditoría que demuestre que el precio editado es usado después por un pedido calculado.

### Estado

**IMPLEMENTADO, FALTA PRUEBA E2E.**

### Prueba propuesta

Editar precio principal y Pascal, calcular un pedido con cada proveedor, comprobar selección, log, snapshot y restauración.

---

## 3.9 Seguridad / Logs / Snapshots

### Qué partes tiene

- Listado real de audit logs.
- KPIs.
- Filtros.
- Detalle de evento.
- Diff before/after.
- Vista JSON larga.
- Snapshot asociado.
- Exportación Excel.
- Restauración desde snapshot.
- Restricción admin.

### Qué debería hacer

- Mostrar una caja negra confiable.
- No confundir severidad de impacto con resultado.
- Asociar log y snapshot por `operation_id`.
- Verificar persistencia.
- Restaurar solo entidades soportadas.
- Registrar la restauración como una nueva operación.

### Qué hace realmente

- Lista logs/snapshots reales desde Supabase.
- La publicación de precios genera log y snapshot persistidos y verificados.
- El rollback Woo real está validado.
- El módulo construye diferencias before/after y permite inspeccionar JSON.
- Exporta logs visibles a Excel.
- La restauración decide soporte según entidad/snapshot.
- Existen dos motores de rollback: el servicio ERP moderno y un servicio legacy. Deben consolidarse.

### Estado

**IMPLEMENTADO Y PROBADO E2E PARA PRECIOS; PARCIAL PARA EL RESTO DE ENTIDADES.**

### Trabajo pendiente

- Crear matriz de entidades restaurables.
- Probar rollback de inventario, constantes, precio proveedor y pedidos.
- Evitar que un botón de restauración aparezca si la entidad no es realmente soportada.
- Añadir prueba de idempotencia del rollback.

---

## 3.10 Informes / Exportaciones

### Qué partes tiene

- Registro visual de exportaciones.
- Tarjetas de resumen.
- Detalle.
- Nueva exportación.
- Descargar, regenerar y eliminar registro.

### Qué debería hacer

- Leer un registro real de exportaciones.
- Generar XLSX/PDF/CSV según módulo.
- Guardar archivo, filtros, usuario, fecha y resultado.
- Permitir descargar/regenerar/eliminar con permisos y logs.

### Qué hace realmente

- La tabla usa `EXPORT_RECORDS`, datos definidos en memoria.
- Los KPIs muestran valores fijos como `128`, `21`, `2` y `Hoy`.
- El botón “Actualizar registro” no tiene comando conectado.
- “Generar exportación” no tiene comando conectado.
- Descargar/regenerar/eliminar muestran literalmente: **“Acción visual. La lógica real se conectará con validación y log.”**
- Existen exportaciones reales dispersas en Inventario, Pedidos y Seguridad, pero no están centralizadas en este módulo.

### Estado

**SOLO INTERFAZ / MOCK.**

### Prioridad Codex

Alta, porque la pantalla aparenta un módulo terminado. Debe conectarse a un registro real o esconderse hasta estar implementada.

---

## 3.11 Configuración

### 3.11.1 Generales

#### Qué debería hacer

Guardar entorno, modo, tema, ruta local y conexiones de forma persistente y segura.

#### Qué hace realmente

- Campos con valores visuales fijos.
- Botones “Guardar generales” y “Cancelar” sin comandos.
- Estados de conexión fijos: SQLite OK, Supabase Online, Woo Conectado, Backups Activo.

#### Estado

**SOLO INTERFAZ / MOCK.**

### 3.11.2 Cálculos

#### Qué debería hacer

Leer y guardar constantes de negocio con validación, log y snapshot; usar esas constantes en Pedidos y Costes.

#### Qué hace realmente

- Lee `business_constants` desde Supabase.
- Guarda valores mediante servicio real.
- Genera `operation_id`.
- La conexión de todas las constantes con todas las fórmulas debe probarse.

#### Estado

**IMPLEMENTADO, FALTA PRUEBA DE IMPACTO E2E.**

### 3.11.3 Seguridad

#### Qué debería hacer

Persistir reglas configurables y aplicarlas en backend.

#### Qué hace realmente

- Muestra switches visuales.
- “Guardar seguridad” y “Cancelar” no tienen comandos.
- Las reglas reales están codificadas en servicios, `.env`, RLS y SQL, no controladas desde estos switches.

#### Estado

**SOLO INTERFAZ / MOCK.**

---

## 3.12 Cálculo de Coste individual

### Qué partes tiene

- `CalculoCoste/coste_1.py`
- `CalculoCoste/coste.py`
- Constantes locales JSON.
- Exportación Excel.

### Qué debería hacer

Calcular coste individual con las fórmulas de negocio y compartir fuentes de datos/constantes con el ERP moderno.

### Qué hace realmente

- Existe una herramienta legacy extensa y aparentemente funcional.
- No está demostrado que utilice siempre la misma fuente de constantes Supabase que la UI ERP.
- Coexisten `coste.py` y `coste_1.py`, señal de duplicidad histórica.
- No está integrada como módulo nativo dentro de la UI ERP actual.

### Estado

**LEGACY / PARALELO, REQUIERE CONSOLIDACIÓN.**

---

## 3.13 Backups, restauración general y modo local

### Qué partes tiene

- `gestorwoo/backup.py`
- SQLite local.
- Scripts y documentación de backups.
- Snapshots Supabase.

### Qué debería hacer

- Diferenciar backup completo de snapshot operativo.
- Crear backups verificables.
- Probar restauración en entorno aislado.
- Documentar RPO/RTO y qué datos cubre cada copia.

### Qué hace realmente

- Existe lógica local de backup para SQLite.
- Existe caja negra Supabase por operación.
- No existe una pantalla ERP completa y probada de backup/restauración de toda la base cloud.
- “Backups activo” en Configuración General es un estado visual fijo.

### Estado

**IMPLEMENTACIÓN PARCIAL / LEGACY.**

---

# 4. Hallazgos transversales

## 4.1 Una UI enorme concentra demasiadas responsabilidades

`GestorWoo/src/futonhub/ui/erp/prototype.py` empezo esta fase con aproximadamente 9.260 lineas. Tras Corte 004B mide 7.495 lineas y conserva Precios, Pedidos, Woo, Proveedores, Informes, Configuracion, Seguridad y partes de Inventario todavia no extraidas.

**Consecuencia:** alto riesgo de regresiones, difícil test unitario, conflictos Git y refactors peligrosos.

**Acción:** dividir por vistas/controladores y mantener servicios cloud separados.

## 4.2 Código moderno y legacy conviven

Existen servicios bajo `futonhub/cloud/services/` y lógica paralela bajo `gestorwoo/cloud/operational_legacy.py`, además de UI antigua en `gestorwoo/ui.py`.

**Acción:** crear un mapa “canónico / legacy / test” y evitar que Codex reutilice accidentalmente el flujo equivocado.

## 4.3 Documentación histórica puede parecer contrato vigente

La carpeta `docs/` contiene decenas de notas de versiones. Son valiosas, pero no prueban el estado actual.

**Acción:** usar esta auditoría como índice vigente y mover notas antiguas a `docs/history/` progresivamente.

## 4.4 Tests actuales son insuficientes para el tamaño del sistema

El baseline v61.2 tenia 11 tests automatizados. La rama actual tras Corte 004B tiene 53 tests, pero la cobertura sigue siendo insuficiente para todo el ERP: no cubre toda la UI ni los flujos E2E.

**Acción:** añadir tests de servicios con dobles de Supabase/Woo y una suite manual reproducible.

## 4.5 Mensajes de éxito deben depender de evidencia

La incidencia del precio demostró que un mensaje “publicado” no basta. v61.2 ya aplica verificación de caja negra en el flujo Woo.

**Acción:** extender el patrón `escribir → releer → verificar → persistencia de log/snapshot → éxito` a operaciones críticas de Pedidos, Inventario y Proveedores.

---

# 5. Matriz de prioridad para Codex

| Prioridad | Trabajo | Motivo |
|---|---|---|
| P0 | Mantener verde el flujo Precio Woo + rollback | Es el primer flujo crítico validado E2E. No debe romperse. |
| P0 | Auditoría E2E de Pedidos | Puede alterar stock y costes; alto impacto de negocio. |
| P0 | Etiquetar/ocultar Informes y Configuración mock | Evitar armaduras huecas y falsas expectativas. |
| P1 | Dividir `prototype.py` por módulos | Reduce regresiones y facilita trabajo paralelo. |
| P1 | Consolidar rollback moderno vs legacy | Evita dos verdades y comportamientos distintos. |
| P1 | Matriz Inventario ↔ Woo por campo | Define qué se sincroniza, dirección, preview y permisos. |
| P1 | Prueba E2E Precio Proveedores → Pedido | Demuestra que la fuente de coste es real. |
| P2 | Centralizar exportaciones reales | Unificar Inventario, Pedidos y Logs en registro real. |
| P2 | Configuración general persistente | Sustituir valores decorativos por estado real. |
| P2 | Administración de usuarios/dispositivos | Completar operación multiusuario. |
| P3 | Consolidar CalculoCoste legacy | Reducir duplicidad y fuentes divergentes. |

---

# 6. Plan de auditoría dinámica

Cada módulo debe pasar una ficha con esta estructura:

```text
Caso:
Precondición:
Acción del usuario:
Dato esperado en UI:
Dato esperado en Supabase:
Dato esperado en Woo/archivo:
Log esperado:
Snapshot esperado:
Rollback esperado:
Resultado real:
Evidencia:
Estado final:
```

## Orden recomendado

1. Pedidos.
2. Inventario y stock.
3. Precio Proveedores.
4. Constantes y repercusión en cálculos.
5. Seguridad y rollback por entidad.
6. Dashboard.
7. Exportaciones.
8. Configuración.
9. Usuarios/permisos.
10. Legacy y limpieza estructural.

---

# 7. Contrato de honestidad funcional

A partir de este checkpoint:

- No se marcará una función como terminada porque exista un botón.
- No se aceptará un mensaje de éxito sin comprobar el dato destino.
- No se considerará rollback a un snapshot que solo se pueda visualizar.
- No se considerará exportación a una ventana que no genere archivo.
- No se considerará configuración a un formulario que no persista.
- No se considerará seguridad a un interruptor visual sin enforcement backend.
- Cada función crítica deberá dejar log, snapshot y evidencia verificable cuando aplique.

---

# 8. Evidencia revisada

- Código fuente de la versión v61.2.
- Servicios cloud de Inventario, Pedidos, Propuestas, Woo, Proveedores, Constantes, Seguridad y Rollback.
- UI ERP actual.
- Scripts SQL Supabase incluidos.
- Documentación histórica del proyecto.
- Suite automatizada baseline v61.2: `11 passed`.
- Suite automatizada rama actual tras Corte 004B: `53 passed`.
- Pruebas manuales confirmadas durante el desarrollo:
  - sincronización Woo y cierre de enlaces;
  - 1.116 relaciones de componentes resueltas;
  - publicación de precio efectivo;
  - persistencia de log/snapshot;
  - rollback Woo real.

---

## Conclusión

FutonHUB ya contiene varios motores reales y uno de sus flujos más sensibles, cambio de precios Woo, está validado extremo a extremo. Sin embargo, el proyecto también contiene pantallas visuales sin lógica, módulos legacy paralelos y grandes áreas que aún necesitan pruebas integrales. Esta auditoría pasa a ser el mapa vigente para que Codex trabaje sobre evidencia y no sobre apariencia.

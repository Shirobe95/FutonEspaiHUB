# FutonHUB UI - Componentes y reglas para Codex / Super Codi

## Uso de este paquete

Los HTML incluidos son **mockups visuales y funcionales**. Codex debe respetar:

- estructura general
- jerarquía visual
- distribución de columnas
- nombres visibles
- comportamiento de botones, pestañas, modales y scroll
- limpieza visual y estilo ERP

No debe copiar estilos de forma ciega si el framework final necesita adaptación, pero sí debe mantener el resultado visual y funcional.

---

## Regla principal

**No tocar Main directamente.**

Trabajar en rama, copia o espacio aislado de UI. La integración con Main debe ser gradual.

---

## Principios visuales

- Interfaz limpia.
- Poco texto explicativo.
- Títulos claros.
- Cards blancas sobre fondo gris claro.
- Bordes suaves.
- Sombras ligeras.
- Colores solo para estados y acciones.
- Evitar saturación.
- Mantener elementos repetidos alineados.
- Priorizar lectura rápida sobre decoración.

---

## Nomenclatura visible

Usar estos nombres visibles:

- Dashboard
- Inventario
- Cambio de Precios
- Pedidos
- WooCommerce
- Informes
- Configuración
- Seguridad / Logs

De momento, **Proveedores queda fuera** como módulo independiente.

---

## Componentes obligatorios

### Select / ComboBox

Cuando el mockup tenga un `<select>`, debe implementarse como **selector cerrado**, no como campo de texto.

No convertir en Entry.

Usos típicos:

- Modo
- Tema
- Rentabilidad
- Tipo cálculo
- Estado
- Filtros cerrados

### Input / Entry

Usar Entry solo para valores editables:

- importes
- porcentajes
- nombres
- fechas
- rutas
- valores numéricos

### Botones

Mantener jerarquía:

- Primario: acción principal del bloque.
- Secundario: acción normal.
- Danger: acción destructiva o crítica.
- No abusar de botones rojos.

### Botones fijos abajo

Cuando una vista tenga botones fijos abajo, deben quedar visibles mientras el contenido interno hace scroll.

Ejemplos:

- Detalles de item en Inventario.
- Detalle de propuesta.
- Detalle de pedido.
- Panel lateral WooCommerce.

### Tablas

Mantener:

- cabecera clara
- columnas alineadas
- scroll horizontal si hay muchas columnas
- valores numéricos alineados y legibles
- no convertir tablas grandes en listas si no se pidió

### Modales / Popups

Usar para decisiones o vistas ampliadas:

- Agregar a propuesta
- Recibido total/parcial
- Detalle completo de item
- Detalle completo de pedido
- Confirmaciones sensibles

Los modales grandes deben ocupar gran parte del workspace, con botón de cerrar claro.

### Estados

Estados oficiales:

- OK
- Info
- Warning
- Error
- Critical

Reglas:

- Warning informa.
- Error bloquea paso actual.
- Critical bloquea la operación completa.
- Critical nunca debe poder saltarse con un clic.

---

## Scroll interno

Donde haya panel de detalle con mucha información:

- contenido con scroll
- acciones fijas abajo

No hacer que el usuario tenga que bajar hasta el final para encontrar botones importantes.

---

## Responsive

En escritorio:

- usar columnas en paralelo cuando el mockup lo indique.

En móvil:

- apilar secciones
- mantener lectura clara
- mantener acciones visibles
- no romper tablas críticas, usar scroll horizontal.

---

## Seguridad operativa

Acciones críticas no deben conectarse directamente sin protección:

- aplicar cambios Woo reales
- borrar pedidos
- confirmar recibido
- actualizar stock real
- cambiar precios reales
- guardar constantes críticas
- sincronizaciones masivas

Deben tener validación, confirmación y logs.

---

## Regla anti-ruido

No añadir textos de ayuda innecesarios si el título ya explica la sección.

Mantener textos solo cuando aclaran una decisión, por ejemplo:

- Añadir a nueva propuesta
- Añadir a propuesta existente
- Recibido completo
- Recibido parcial

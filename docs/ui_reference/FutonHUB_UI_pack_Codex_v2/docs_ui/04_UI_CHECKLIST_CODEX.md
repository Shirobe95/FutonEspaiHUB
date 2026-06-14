# FutonHUB UI - Checklist de aceptación para Codex / Super Codi

## General

- [ ] No se toca Main directamente.
- [ ] Se trabaja en rama/copia UI.
- [ ] Se mantiene nomenclatura visible.
- [ ] No se añaden textos innecesarios.
- [ ] Se respeta estilo limpio tipo ERP.
- [ ] Estados usan OK / Info / Warning / Error / Critical.
- [ ] Critical bloquea operación completa.
- [ ] Proveedores no aparece como módulo independiente del menú.

## Menú

- [ ] Dashboard
- [ ] Inventario
- [ ] Cambio de Precios
- [ ] Pedidos
- [ ] WooCommerce
- [ ] Informes / Exportaciones
- [ ] Seguridad / Logs
- [ ] Configuración
- [ ] No incluir Proveedores de momento.

## Componentes

- [ ] Select sigue siendo Select/ComboBox, no Entry.
- [ ] Inputs solo se usan para valores editables.
- [ ] Tablas mantienen columnas y scroll horizontal si hace falta.
- [ ] Botones fijos abajo se mantienen visibles.
- [ ] Paneles de información tienen scroll interno cuando corresponde.
- [ ] Modales tienen botón de cerrar claro.

## Inventario

- [ ] Tabla y detalle están en paralelo en escritorio.
- [ ] Detalle rápido tiene botones fijos abajo.
- [ ] Detalle completo abre modal grande.
- [ ] Agregar a propuesta abre popup con dos opciones.

## Propuestas

- [ ] Listado de propuestas tiene columnas alineadas.
- [ ] Estado va al final.
- [ ] Detalle de propuesta tiene botones fijos abajo.
- [ ] Modificar propuesta permite añadir items y variaciones.
- [ ] Cada item de propuesta permite Modificar y Borrar.
- [ ] No permitir usar subida % y exacta a la vez.

## Pedidos

- [ ] Proveedor viene heredado en calcular pedido.
- [ ] No se muestra selector de proveedor dentro de calcular pedido.
- [ ] Cargar pedido es compacto: botón + nombre archivo + tipo.
- [ ] Recibido abre popup total/parcial.
- [ ] Detalle completo abre popup grande con tabla de cálculos.

## WooCommerce

- [ ] Enfoque principal: actualizar base local desde Woo.
- [ ] Incluye auto-clasificación.
- [ ] No tratar WooCommerce como pantalla principal de publicación.
- [ ] Casos dudosos pasan a revisión manual.

## Informes / Exportaciones

- [ ] Muestra registro de exportaciones realizadas.
- [ ] Muestra detalle de exportación seleccionada.
- [ ] Nueva exportación abre popup.
- [ ] Exportaciones quedan registradas en logs.

## Seguridad / Logs

- [ ] Muestra tabla de eventos.
- [ ] Ver detalles abre popup grande.
- [ ] Popup muestra cambios con estado anterior y estado cambiado.
- [ ] Permite ver snapshot y exportar detalle.

## Configuración

- [ ] Solo tres pestañas: Generales, Cálculos, Seguridad.
- [ ] Constantes del negocio editables.
- [ ] Selects no son Entries.
- [ ] Cambios sensibles deben dejar log.

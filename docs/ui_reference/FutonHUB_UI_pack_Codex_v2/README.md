# FutonHUB UI Pack para Codex / Super Codi v2

Este ZIP contiene los mockups HTML y documentos de reglas para empezar o continuar la integración visual del ERP.

## Estructura

```text
ux_mockups/
  00_dashboard_sistema_visual.html
  01_inventario_workspace.html
  02_propuestas_guardadas.html
  03_modificar_propuesta.html
  04_pedidos_workspace.html
  05_pedidos_detalle_completo.html
  06_calcular_nuevo_pedido.html
  07_woocommerce.html
  08_configuracion.html
  09_seguridad_logs.html
  10_informes_exportaciones.html

docs_ui/
  00_FutonHUB_UI_v1_definiciones_para_Codex.md
  01_MENU_Y_MODULOS.md
  02_UI_COMPONENTES_Y_REGLAS_CODEX.md
  03_UI_FLUJOS_MODULOS.md
  04_UI_CHECKLIST_CODEX.md
```

## Menú final incluido

- Dashboard
- Inventario
- Cambio de Precios
- Pedidos
- WooCommerce
- Informes / Exportaciones
- Seguridad / Logs
- Configuración

## Proveedores

Proveedores queda fuera de momento como módulo independiente.

No añadirlo al menú principal.

En Pedidos sí pueden existir tarjetas de proveedor para iniciar el cálculo de un pedido.

## Instrucción para Codex

El HTML es referencia visual.  
Los Markdown son contrato funcional.

Si hay conflicto, respetar primero:

1. Seguridad
2. Nomenclatura visible
3. Comportamiento funcional descrito en Markdown
4. Distribución visual del HTML

## Importante

No conectar acciones críticas reales sin validaciones, confirmación y logs.

No tocar Main directamente.

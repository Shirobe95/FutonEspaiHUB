# FutonHUB UI Reference

Ultima actualizacion: 2026-05-31

Este directorio guarda las referencias visuales y funcionales aprobadas para construir la UI-ERP en el prototipo Tkinter.

## Pack canonico

```text
docs/ui_reference/FutonHUB_UI_pack_Codex_v2/
```

Contenido principal:

```text
ux_mockups/   HTML de referencia visual por pantalla
docs_ui/      Contrato funcional, reglas, flujos y checklist
```

## Reglas de uso

- El HTML define la referencia visual.
- Los Markdown definen el contrato funcional.
- Si hay conflicto, priorizar seguridad, nomenclatura visible, comportamiento funcional y despues distribucion visual.
- No tocar `Main` directamente.
- No convertir selects en entries: un `<select>` del mockup debe ser un selector cerrado/ComboBox.
- Integrar primero visualmente en el prototipo aislado.
- Conectar logica real despues, siempre con validaciones, confirmacion y logs.

## Modulos cubiertos

- Dashboard
- Inventario
- Cambio de Precios
- Pedidos
- Calcular nuevo pedido
- WooCommerce
- Informes / Exportaciones
- Seguridad / Logs
- Configuracion

## Menu oficial v2

```text
Dashboard
Inventario
Cambio de Precios
Pedidos
WooCommerce
Informes / Exportaciones
Seguridad / Logs
Configuracion
```

`Proveedores` queda fuera del menu principal. Las tarjetas de proveedor viven dentro de `Pedidos`.

## Entrada de trabajo

```powershell
python GestorWoo\gestorwoo.py erp-prototype
```

El prototipo sirve para validar navegacion, nomenclatura, distribucion visual y flujo operativo antes de conectar acciones reales.

# UI ERP Pedidos v56.1 - Cuenta para descarga visible en Pedidos

## Objetivo
Corregir la pantalla diaria de Operaciones > Pedidos para que la regla `Cuenta para descarga` sea visible y editable correctamente al entrar pedidos.

## Cambios

- En la tabla del cálculo, la columna de la lógica de descarga se muestra como `Cuenta para descarga` también en pedidos tipo Tatamis/Ekomat.
- En pedidos tipo Tatamis/Ekomat ya no se fuerza visualmente `Cuenta pedido` ni `Sí` fijo.
- El valor visible usa la regla centralizada:
  - `No` para fundas, cover, topper, pillow/pillows y almohadas.
  - `Sí` para las excepciones definidas como producto grande.
- La ventana de doble click se amplía para que los botones `Aceptar` y `Cancelar` no queden escondidos.
- El selector `Cuenta para descarga` se hace más visible con combobox ancho y marcador desplegable.
- El resumen indica unidades excluidas del reparto cuando existan.
- La exportación de pedidos tipo Tatamis incluye `Cuenta para reparto descarga`.

## Regla centralizada

No cuentan para reparto de descarga si contienen:

- funda
- cover
- topper
- pillow / pillows
- almohada / almohadas

Sí cuentan aunque tengan nombres conflictivos estas referencias:

- 0727007
- 0730009
- 1242001
- 1242002
- 1243001
- 1244001
- 1245001
- 1249001

## Validación

- `python -m compileall -q .`
- `pytest -q`
- Resultado: `11 passed`

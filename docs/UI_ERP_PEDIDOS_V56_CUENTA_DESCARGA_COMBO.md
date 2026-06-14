# UI ERP Pedidos v56 - Cuenta para descarga con selector

## Objetivo

Activar correctamente la decisión **Cuenta para descarga** al entrar pedidos, porque influye directamente en el reparto de coste de descarga y por tanto en el precio calculado.

## Cambios

- En el editor de línea del pedido, el campo **Cuenta para descarga** queda como `Combobox` con opciones cerradas:
  - `Sí`
  - `No`
- Se añade una explicación de la regla automática aplicada.
- Se añade botón **Regla auto** para restaurar la decisión automática si el usuario la cambia manualmente.
- El cálculo del reparto usa siempre `cuenta_reparto_descarga`.
- La regla se aplica tanto a Excel como a PDF.

## Regla automática

No cuentan para descarga si el texto contiene:

- `funda`
- `cover`
- `topper`
- `pillow`
- `pillows`
- `almohada`
- `almohadas`

Sí cuentan aunque contengan palabras conflictivas las referencias definidas como excepción:

- `0727007`
- `0730009`
- `1242001`
- `1242002`
- `1243001`
- `1244001`
- `1245001`
- `1249001`

## Nota operativa

Si se cambia el selector en una línea, hay que guardar el editor y volver a calcular el pedido para que el reparto de descarga se actualice.

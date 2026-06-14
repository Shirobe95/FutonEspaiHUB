# UI ERP v45 - Seguridad / Logs filtro de módulo con Combobox

## Cambio

En Seguridad / Logs, el filtro `Módulo` deja de ser una entrada libre y pasa a ser un desplegable.

## Motivo

Evitar errores de escritura al filtrar:

- acentos
- mayúsculas/minúsculas
- espacios
- nombres internos vs visuales

## Valores

```text
Todos
Inventario
Pedidos
Precio Proveedores
Cambio de Precios
WooCommerce
Configuración
Seguridad
Sistema
```

## Compatibilidad interna

El servicio traduce nombres visuales a nombres internos probables.

Ejemplo:

```text
Inventario → inventory_items / Inventario
Pedidos → supplier_orders / Pedidos
Configuración → business_constants / Configuración / configuracion
```

## Estado

El resto de Seguridad / Logs v1 queda aprobado.

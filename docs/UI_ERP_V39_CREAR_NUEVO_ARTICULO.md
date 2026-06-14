# UI ERP v39 - Crear nuevo artículo desde Inventario

## Objetivo

Añadir un flujo visual para crear artículos nuevos directamente en Supabase desde:

```text
Inventario → Crear nuevo artículo
```

## Campos del formulario

- ID / Referencia
- HECA reference
- Nombre
- Estado comercial
- Familia
- Subgrupo
- Medida
- Materiales
- M3 unidad
- Rotación C
- Bultos
- Precio proveedor
- Precio Pascal
- Woo SKU
- Stock tienda
- Stock almacén
- Notas

## Validaciones

- ID obligatorio y numérico.
- Nombre obligatorio.
- Bultos mayor que 0.
- Precios y stocks no pueden ser negativos.
- Si el item_id ya existe, no crea duplicado.

## Guardado

Inserta en:

```text
public.inventory_items
```

Genera:

- operation_snapshot
- audit_log

## Seguridad

No toca WooCommerce.  
No toca stock externo.  
No sincroniza nada automáticamente.  
Solo crea la ficha base del artículo para poder usarlo en inventario, pedidos y precios proveedor.

## Cambio de arranque

`Abrir ERP.bat` vuelve a modo simple:

```text
python gestorwoo.py erp-prototype
```

No exige `.venv_erp`. La instalación/empaquetado se abordará más adelante.

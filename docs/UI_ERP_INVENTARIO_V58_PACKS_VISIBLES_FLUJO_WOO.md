# FutonHUB v58 - Inventario: packs visibles y búsqueda calibrada

## Objetivo

Cerrar la parte diaria de Inventario para que los packs/compuestos Woo no aparezcan como cajas negras.

La búsqueda por componente ya devolvía packs relacionados. En v58 se mejora la visualización para que el operador vea:

- ID del componente.
- Nombre del componente.
- Cantidad usada en el pack.

Ejemplo:

```text
WOO-PACK-3720
- 0201001 x2 · Tatami, 80 x 200 x 5,5 cm.
- 0728003 x1 · Futón ...
```

## Cambios UI

### Operaciones > Inventario

La tabla diaria añade columnas:

- `Tipo`: Simple, Pack Woo, Alias, Pack manual.
- `Contenido pack`: resumen corto de ingredientes del pack.

### Panel derecho de detalles

El contenido del pack se muestra directamente dentro de los detalles, sin abrir otra ventana.

Fuente principal:

```text
inventory_item_components
```

Fallback:

```text
woo_sku con separador |
```

### Detalle completo

También muestra el bloque `Contenido del pack` dentro de la ventana de detalle completo.

## Búsqueda calibrada

Para búsquedas con forma de código/SKU, por ejemplo:

```text
0201001
0616001A
WOO-PACK-3720
```

se usa la búsqueda exacta/rankeada desde:

```text
v_inventory_hub_search_ranked
```

No se mezcla con búsqueda amplia por contiene sobre todo el inventario. Esto evita resultados arrastrados accidentalmente.

Para búsquedas de texto normal, por ejemplo:

```text
Tatami
Funda
Coco Plus
```

se mantiene búsqueda amplia, acento-insensible, combinada con Supabase.

## Flujo de precios con WooCommerce

Flujo operativo definido:

1. Se trabaja desde Inventario.
2. El usuario añade items a propuestas de precios.
3. Si se acepta la propuesta, el HUB busca el item enlazado en WooCommerce.
4. Se sube el precio en WooCommerce.
5. Se actualiza la información de precio del item en Inventario.
6. Se comprueba que WooCommerce e Inventario coinciden.

Los packs/alias deben estar enlazados para que este flujo sea trazable.

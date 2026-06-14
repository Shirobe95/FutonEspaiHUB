# UI ERP v51 - WooCommerce classifier v3 + base enlace manual

## Base

```text
v50_working_overlay_woo_preview_v2
```

## Objetivos

1. Arreglar auto-refresh del módulo WooCommerce al terminar `Sincronizar + Autoclasificar`.
2. Mejorar autoclasificador por capas.
3. Preparar indicador/base visual para enlace manual Supabase ↔ Woo.

## Auto-refresh

Al terminar la sincronización:

```text
cerrar overlay
actualizar preview en memoria
limpiar contenido actual del módulo
redibujar WooCommerce automáticamente
```

Ya no debería ser necesario salir del módulo y volver a entrar.

## Autoclasificador por capas

Nueva prioridad:

```text
1. Nombre del producto manda.
2. Categorías ayudan.
3. Atributos solo completan material/medida/opciones.
4. Atributos no pueden secuestrar familia principal.
```

## Casos corregidos

### Futón con atributos de cojines/fundas

Antes podía caer como:

```text
Complementos / Cojines
```

Ahora:

```text
Futones / Futón
```

y añade nota:

```text
Atributos contienen complementos; no se usaron para cambiar la familia principal.
```

### Sofá cama con atributos de funda/futón

Antes podía caer como:

```text
Complementos / Funda futón
```

Ahora:

```text
Sofás Cama / Sofá cama
```

### Mesitas

Antes podían caer como sofá por etiquetas de medidas.

Ahora:

```text
Complementos / Mesita
```

### Cojines pack de 2 unidades

Antes podía caer como Ofertas/Packs por la palabra `pack`.

Ahora:

```text
Complementos / Cojines
```

### Futón + Funda + Cojines

Se mantiene como:

```text
Ofertas / Packs / Pack futón + funda + cojines
```

## Enlace manual Supabase ↔ Woo

En la tabla Woo se añade columna:

```text
Enlace manual
```

Valores:

```text
Disponible
No
```

En el panel derecho se muestra una sección:

```text
Enlace manual Supabase ↔ Woo
```

Por ahora es preparatoria para v52. No aplica cambios todavía.

Regla diseñada:

```text
Solo se podrá enlazar un Woo no enlazado con un item Supabase sin Woo.
Si el Woo ya está enlazado con otro item, se bloquea.
Preview obligatorio.
Log + snapshot.
```

## JSON

Se mantiene exportación JSON y se añade:

```text
manual_link_candidate
```

## Checklist

1. Abrir WooCommerce.
2. Pulsar Sincronizar + Autoclasificar.
3. Confirmar que al terminar se refresca la tabla automáticamente.
4. Exportar JSON.
5. Revisar casos raros:
   - Futón con atributos de cojines
   - Sofá cama Zúrich
   - Mesita Okinawa
   - Cojines pack 2 unidades
   - Futón + Funda + Cojines
6. Confirmar columna `Enlace manual`.
7. Confirmar sección de enlace manual en panel derecho.

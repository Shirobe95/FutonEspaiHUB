# UI ERP v50 - Working overlay + Woo preview v2

## Objetivo

Mejorar la experiencia de operaciones lentas y reducir ruido/errores falsos en WooCommerce Sync.

## 1. Indicador de trabajo

Se añade overlay bloqueante con progreso indeterminado para operaciones lentas.

### WooCommerce

Al pulsar:

```text
Sincronizar + Autoclasificar
```

aparece:

```text
Sincronizando WooCommerce
Leyendo productos y variaciones, autoclasificando y comparando contra Supabase.
No cierres esta ventana.
```

### Cálculo de pedidos

Al pulsar:

```text
Calcular pedido
```

aparece:

```text
Calculando pedido
Aplicando constantes, precios de proveedor, costes, ponderado y validaciones.
No cierres esta ventana.
```

## 2. WooCommerce preview v2

### Padres variables sin SKU

Antes se marcaban como Error por `missing_sku`.

Ahora:

```text
Producto padre variable sin SKU
→ Info
→ no se considera error automáticamente
```

Porque normalmente las variaciones son las que deben enlazar.

### Padres variables sin precio

Antes podían generar error por precio vacío.

Ahora:

```text
Producto padre variable sin precio directo
→ Info
→ revisar precios en variaciones
```

### Fundas / cojines / topper

Prioridad de clasificación corregida:

```text
Funda para futón
→ Complementos / Funda futón

Cojines
→ Complementos / Cojines

Topper
→ Complementos / Topper
```

Esto evita que `funda para futón` caiga como Futones.

### Packs/composiciones

Se detectan casos problemáticos:

```text
Futón + Funda
Futón + Cojines
Futón + Funda + Cojines
Tatami + Futón
Combinación / composición / pack
```

Clasificación:

```text
Ofertas / Packs
```

Subgrupos:

```text
Pack futón + funda
Pack futón + cojines
Pack futón + funda + cojines
Pack tatami + futón
```

Estos quedan con nota:

```text
Composición/pack detectado; revisar antes de aplicar.
```

### Padres variables con múltiples medidas

Si el producto padre variable tiene varias medidas en atributos:

```text
size = ""
classification_reason = "Producto padre variable con múltiples medidas; la medida debe venir de la variación."
```

Las medidas se dejan para variaciones.

## 3. JSON exportado

Se mantiene el JSON preview y se añaden datos:

```text
multiple_sizes_detected
classification_kind
```

Valores posibles:

```text
single_item
pack_or_composition
```

## Checklist de prueba

1. Abrir WooCommerce.
2. Pulsar Sincronizar + Autoclasificar.
3. Confirmar que aparece overlay de trabajo.
4. Confirmar que el overlay desaparece al terminar.
5. Exportar JSON.
6. Revisar que padres variables sin SKU bajen de Error a Info cuando corresponda.
7. Revisar que `Funda para futón` sea Complementos / Funda futón.
8. Revisar que `Futón + Funda + Cojines` sea Ofertas / Packs.
9. Calcular un pedido y confirmar overlay.

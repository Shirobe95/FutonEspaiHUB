# UI ERP v52 - Woo review/edit preview

## Base

```text
v51_woo_classifier_linking
```

## Objetivos

- Mejorar autoclasificador con casos raros detectados en JSON v51.
- Añadir columna `Revisión`.
- Permitir editar parámetros de clasificación en el preview.
- Mantener export JSON con ajustes manuales.
- Seguir sin escribir en Supabase.

## Correcciones de clasificación

### Negaciones

```text
sin cojines
sin cojin
sin almohadas
sin fundas
```

No cuentan como componente.

Ejemplo:

```text
Futón ..., sin cojines
→ Futones / Futón
```

### Packs reales

```text
Tatamis + Futón + Funda/Cojín
→ Ofertas / Packs / Pack tatami + futón
```

### Funda con fundas de cojines

```text
Funda para futón + 2 fundas de cojín
→ Complementos / Funda futón
```

No se marca como pack futón.

### Materiales en sofás/camas

Sofás cama y camas japonesas no absorben materiales de `Tipo de futón`.

```text
Sofá cama Zúrich
→ Sofás Cama / Sofá cama / Madera
```

## Revisión

Nueva columna:

```text
Revisión
```

Valores:

```text
OK
REVISAR
```

Motivos de revisión:

- Sin enlace Supabase.
- Estado Error/Critical.
- Familia o medida pendiente.
- Pack/composición.
- Campos rellenables en Supabase.
- Clasificación baja.
- Incidencias del preview.

## Edición manual de parámetros

En el panel derecho:

```text
Editar clasificación preview
```

Campos editables:

```text
family
subgroup
size
materials
commercial_status
is_pack
confidence
classification_kind
```

Esto solo actualiza:

```text
preview en memoria
JSON exportado
```

No escribe en Supabase.

## JSON

El JSON incluye:

```text
review
manual_classification_edit
```

Si se edita manualmente:

```text
manual_classification_edit.applied = true
```

## Checklist

1. WooCommerce → Sincronizar + Autoclasificar.
2. Confirmar columna Revisión.
3. Revisar casos:
   - Futón sin cojines
   - Tatami + Futón + Funda/Cojín
   - Funda + fundas de cojines
   - Sofá cama Zúrich
4. Abrir detalle de una línea.
5. Editar clasificación preview.
6. Confirmar que la tabla se redibuja.
7. Exportar JSON.
8. Confirmar que el JSON incluye el ajuste manual.

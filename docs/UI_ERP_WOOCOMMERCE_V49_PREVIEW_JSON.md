# UI ERP v49 - WooCommerce Sync preview + JSON

## Objetivo

Primera versión real del módulo WooCommerce completo, en modo diagnóstico seguro.

## Qué hace

```text
WooCommerce
→ leer productos y variaciones
→ autoclasificar
→ comparar contra Supabase inventory_items
→ mostrar preview
→ exportar JSON
```

## Qué NO hace

```text
No escribe en Supabase
No escribe en WooCommerce
No actualiza stock
No toca precios internos
```

## Botón principal

```text
Sincronizar + Autoclasificar
```

## JSON exportado

Botón:

```text
Exportar JSON preview
```

El JSON incluye por item:

```text
status
match_method
woo
classification_after
supabase_match
proposed_supabase_update
issues
safe_to_apply_later
```

## Campos seguros para proponer relleno

Solo se proponen para v50 si Supabase está vacío:

```text
family
subgroup
size
materials
commercial_status
is_pack
woo_item_kind
woo_id
woo_parent_id
woo_sku
woo_name
woo_type
woo_price
woo_categories
woo_link_status
woo_link_notes
```

## Campos que Woo nunca debe pisar automáticamente

```text
primary_supplier_price
pascal_price
weighted_average_cost
store_stock
warehouse_stock
rotation_c
packages
```

## Estados

```text
OK
Warning
Error
Critical
```

## Reglas de enlace

1. Primero intenta por woo_id ya guardado en Supabase.
2. Luego intenta por SKU / referencia / item_id normalizados.
3. Si hay varios matches, Critical.
4. Si no hay match, Warning.

## Checklist de prueba

1. Abrir WooCommerce.
2. Pulsar Sincronizar + Autoclasificar.
3. Confirmar métricas: items Woo, enlazados, sin enlace, warnings, errores.
4. Seleccionar varias líneas y revisar panel derecho.
5. Pulsar Ver JSON línea.
6. Exportar JSON preview.
7. Revisar que JSON tenga classification_after y comparativa Supabase.
8. Confirmar que no se escribe nada en Supabase.

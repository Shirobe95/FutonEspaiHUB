# FutonHUB - Registro de tests de caracterizacion

Fecha: 2026-06-14

## Commit: entrypoint y navegacion

Comportamiento protegido:

- `Abrir ERP.bat` sigue siendo la entrada oficial.
- La entrada oficial ejecuta `GestorWoo/gestorwoo.py erp-prototype`.
- `gestorwoo.cli` mantiene el comando `erp-prototype` enlazado a `futonhub.ui.erp.prototype.run_erp_prototype`.
- La navegacion del ERP prototype conserva keys, labels, grupos y orden.
- Cada key de navegacion conserva metodo de vista en `FutonHubErpPrototype`.

Archivos tocados:

- `GestorWoo/tests/test_characterization_entrypoint.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_entrypoint -v
```

Resultado:

```text
Ran 4 tests in 2.268s
OK
```

Limitaciones:

- No instancia Tkinter.
- No prueba login real.
- No escribe en WooCommerce ni Supabase.
- El test del CLI inspecciona enlace/import y fuente del comando; no ejecuta `main()` para evitar cargar configuracion real.

## Commit: precio efectivo y payload Woo

Comportamiento protegido:

- `sale_price` activo es el precio efectivo visible.
- Sin `sale_price` activo, `regular_price` es el precio efectivo.
- `price` solo actua como fallback si no hay `regular_price` ni `sale_price` validos.
- Con rebaja activa y nuevo precio menor que `regular_price`, la publicacion debe escribir solo `sale_price`.
- Si el nuevo precio iguala o supera `regular_price`, la publicacion debe escribir `regular_price` y limpiar `sale_price`.
- Sin rebaja activa, la publicacion debe escribir `regular_price` y limpiar `sale_price`.

Archivos tocados:

- `GestorWoo/tests/test_characterization_woocommerce_price.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_woocommerce_price -v
```

Resultado:

```text
Ran 6 tests in 0.001s
OK
```

Limitaciones:

- Prueba funciones puras del servicio de publicacion.
- No instancia `WooCommerceClient`.
- No ejecuta preview ni publicacion real.
- No escribe en WooCommerce ni Supabase.

## Commit: clasificacion Woo y enlaces

Comportamiento protegido:

- Padres variables sin SKU quedan informativos.
- Productos test y sus variaciones se excluyen del seguimiento operativo.
- Si un padre variable comparte SKU con una variacion, la variacion conserva el enlace operativo.
- El enlace automatico prioriza `woo_id`.
- El enlace por SKU incluye alias basados en `heca_reference`.
- `build_sync_preview` conserva los estados `ignored_test_item`, `parent_sku_owned_by_variation`, `variable_parent_without_sku` y `sku`.
- El preview de enlace manual no toca WooCommerce y solo rellena campos de clasificacion vacios, sin pisar valores internos existentes.

Archivos tocados:

- `GestorWoo/tests/test_characterization_woocommerce_sync.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_woocommerce_sync -v
```

Resultado:

```text
Ran 7 tests in 0.004s
OK
```

Limitaciones:

- Usa monkeypatch/dobles para cargas Woo/Supabase.
- No instancia `WooCommerceClient`.
- No llama a `apply_manual_woo_link`.
- No escribe en WooCommerce ni Supabase.

## Commit: persistencia de log y snapshot

Comportamiento protegido:

- La publicacion Woo exige confirmacion real de `operation_snapshots`.
- Si el snapshot no aparece tras el primer intento, se reintenta.
- Si el snapshot sigue sin aparecer, se lanza `CloudAuditError` y la operacion queda bloqueada.
- La publicacion Woo exige confirmacion real de `audit_logs`.
- Si el audit log no aparece tras el primer intento, se reintenta.
- Si el audit log sigue sin aparecer, se lanza `CloudAuditError` y no se puede declarar la operacion como cerrada.

Archivos tocados:

- `GestorWoo/tests/test_characterization_blackbox_persistence.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_blackbox_persistence -v
```

Resultado:

```text
Ran 4 tests in 0.004s
OK
```

Limitaciones:

- Usa mocks sobre `write_snapshot`, `write_audit_event` y `_blackbox_record_exists`.
- No consulta Supabase real.
- No escribe en Supabase real.
- No toca WooCommerce.

## Commit: rollback Woo de regular_price y sale_price

Comportamiento protegido:

- Rollback de producto Woo restaura `regular_price` y `sale_price` desde `woo_before`.
- Rollback de variacion Woo usa `parent_woo_id` y restaura ambos campos.
- Tras escribir, el rollback relee WooCommerce.
- Si la relectura no confirma `regular_price` y `sale_price`, el rollback falla.
- El espejo Supabase se actualiza con los campos verificados.
- La propuesta queda marcada como `rolled_back` cuando el rollback Woo fue verificado.

Archivos tocados:

- `GestorWoo/tests/test_characterization_woocommerce_rollback.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_woocommerce_rollback -v
```

Resultado:

```text
Ran 3 tests in 0.696s
OK
```

Limitaciones:

- Usa un cliente Woo fake.
- Usa un cliente Supabase fake que solo registra updates.
- No escribe en WooCommerce real.
- No escribe en Supabase real.

## Commit: componentes de packs

Comportamiento protegido:

- `fetch_inventory_pack_components` usa `v_inventory_component_search` como ruta principal.
- La ruta principal deduplica filas repetidas por `relation_id` y codigo de componente.
- Si falla la vista, se usa fallback a `inventory_item_components`.
- El fallback de tabla puede resolver nombres mediante `_fill_component_names_from_inventory`.
- Si no hay relaciones, se usa fallback por `woo_sku` compuesto con conteo estable.
- La UI prioriza `hub_pack_components_text`/`hub_pack_components_multiline` cacheados.
- La UI tambien puede mostrar componentes desde `woo_sku` compuesto si no hay texto cacheado.

Archivos tocados:

- `GestorWoo/tests/test_characterization_pack_components.py`
- `auditoria/CODEX_CARACTERIZACION_TESTS.md`

Comando ejecutado:

```powershell
python -m unittest GestorWoo.tests.test_characterization_pack_components -v
```

Resultado:

```text
Ran 5 tests in 0.001s
OK
```

Limitaciones:

- Usa cliente Supabase fake.
- No consulta Supabase real.
- No instancia Tkinter.
- No escribe en WooCommerce ni Supabase.

## Verificacion global de la fase

Comando ejecutado:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 40 tests in 0.079s
OK
```

Resumen:

- Tests existentes iniciales: 11.
- Tests de caracterizacion anadidos: 29.
- Total actual: 40.

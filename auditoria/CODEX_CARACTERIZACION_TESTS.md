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

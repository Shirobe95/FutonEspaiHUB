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

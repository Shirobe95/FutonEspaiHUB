# FutonHUB - Corte 004D1 inventory item creation

Fecha: 2026-06-16

Estado:

```text
Cerrado y aprobado.
```

## Objetivo

Extraer el flujo existente de creacion manual de items de Inventario desde `prototype.py` a un mixin dedicado, sin cambiar comportamiento observable ni reglas de negocio.

## Alcance

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/inventory_create.py
```

Mixin:

```text
ErpInventoryCreateMixin
```

`FutonHubErpPrototype` sigue siendo el adaptador principal. El boton existente de Inventario sigue llamando a `_open_create_inventory_item_modal`.

## Simbolos extraidos

- `ErpInventoryCreateMixin._open_create_inventory_item_modal`

Los callbacks internos permanecen dentro del metodo:

- `add_entry`
- `get_payload`
- `preview`
- `save`

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/inventory_create.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/src/futonhub/cloud/services/inventory.py
GestorWoo/tests/test_characterization_inventory_create.py
GestorWoo/tests/test_characterization_inventory_edit.py
auditoria/CODEX_CORTE_004D1_INVENTORY_CREATE.md
auditoria/CODEX_SMOKE_TESTS.md
```

## Comportamiento preservado

- Sesion Supabase obligatoria.
- `item_id` obligatorio, numerico y mayor que cero, validado por el servicio existente.
- `name` obligatorio, validado por el servicio existente.
- `heca_reference` vacio se completa en UI con `item_id` a siete digitos.
- `packages` por defecto `1` y validado como mayor que cero por el servicio existente.
- Precios y stocks no negativos, validados por el servicio existente.
- Duplicado bloqueado solo por `item_id`.
- Preview separado de la escritura.
- Creacion mediante `create_cloud_inventory_item`.
- `operation_id`, snapshot y audit log quedan a cargo del servicio existente.
- WooCommerce no se toca.
- El modal se cierra tras crear.
- `_inventory_loaded_once = False` tras crear.
- Refresco posterior con `_refresh_inventory(self._content, str(item_id), allow_empty=True)`.

## Exclusiones

No se modificaron:

- escrituras, inserciones, updates, snapshots, audit logs ni historial;
- esquemas, RLS, RPCs, tablas o columnas;
- WooCommerce;
- validacion de duplicados por `woo_sku`;
- enlaces Woo, `woo_id`, packs, alias o componentes;
- nuevas escrituras de historial;
- logs o snapshots del servicio;
- exportacion;
- comportamiento visual;
- deuda Unicode.

## Tests anadidos

Nuevo archivo:

```text
GestorWoo/tests/test_characterization_inventory_create.py
```

Cobertura:

- el modal bloquea sin sesion;
- el MRO resuelve `_open_create_inventory_item_modal` desde `inventory_create.py`;
- el payload conserva defaults actuales;
- `heca_reference` vacio se autocompleta a siete digitos;
- preview duplicado impide llamar a creacion;
- guardar tras confirmacion llama a `create_cloud_inventory_item`;
- no se llama a WooCommerce;
- tras crear se marca `_inventory_loaded_once = False`;
- tras crear se refresca Inventario con el `item_id`;
- se conserva la separacion entre preview y escritura.
- `INVENTORY_SELECT_COLUMNS` contiene los campos necesarios para leer lo creado;
- los campos creados se conservan en `InventoryItem.raw`;
- la edicion desde Detalle completo no genera falsos cambios cuando los valores ya estan cargados.

## Resultado de suite

Comando ejecutado:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 89 tests
OK
```

## Riesgos conocidos

- La creacion actual bloquea duplicados por `item_id`; no bloquea duplicados por `woo_sku`.
- El servicio mantiene snapshot y audit log como best-effort: si fallan, la creacion puede continuar.
- La creacion no genera filas directas en `inventory_change_history`.
- Este corte no crea packs, alias ni relaciones de componentes.

## Bug previo detectado durante smoke

Sintomas observados:

- Al crear un item nuevo, `rotation_c`, `primary_supplier_price` y `pascal_price` quedaban persistidos, pero al abrir Inventario/Detalle aparecian como `Sin definir`.
- Al introducir esos mismos valores desde Detalle completo, el preview detectaba cambios desde `Sin definir`; al guardar, el servicio respondia `No hay cambios para aplicar.`

Causa raiz:

- La creacion si persistia los valores mediante `create_cloud_inventory_item`.
- La lectura general de Inventario usaba `INVENTORY_SELECT_COLUMNS` sin varias columnas que el ERP crea, muestra y edita.
- Al refrescar, la fila cargada quedaba incompleta y `InventoryItem.raw` no contenia esos campos.

Correccion minima aplicada:

- Se amplio solo la proyeccion de lectura `INVENTORY_SELECT_COLUMNS`.
- Campos anadidos: `rotation_c`, `packages`, `primary_supplier_price`, `pascal_price`, `commercial_status`.
- No se modificaron inserciones, updates, normalizacion, snapshots, audit logs, historial, reglas de negocio ni WooCommerce.

Tests de regresion:

- `INVENTORY_SELECT_COLUMNS` contiene los cinco campos diagnosticados.
- Una fila cloud con esos campos conserva los valores en `InventoryItem.raw`.
- Si `raw` ya contiene `rotation_c = 2`, `primary_supplier_price = 15` y `pascal_price = 12`, reintroducir esos mismos valores no genera falsos cambios.
- Se mantiene una caracterizacion del fallo previo: si `raw` no trae esos campos, la UI interpreta cambios desde vacio.

Estado:

- Bug previo corregido.
- Smoke manual repetido y aprobado.

## Smoke manual aprobado

Resultado: aprobado por el usuario el 2026-06-16.

Evidencia manual:

- Creacion de items funcional.
- Validaciones correctas.
- `rotation_c`, `packages`, `primary_supplier_price`, `pascal_price` y `commercial_status` persistidos.
- Refresco correcto.
- Valores visibles en Detalle completo.
- Edicion posterior desde Detalle completo funcional.
- No aparecen falsos cambios.
- WooCommerce intacto.
- Cierre sin traceback.

Estado final:

- Corte 004D1 cerrado y aprobado.
- Creacion y edicion desde Detalle completo funcionan correctamente tras la correccion de proyeccion de lectura.
- No se modificaron escrituras, WooCommerce, RLS ni esquema.

# FutonHUB - Descubrimiento inicial Codex

Fecha: 2026-06-14
Rama solicitada: `refactor/modularizacion-v1`

## Estado Git y base de trabajo

- El directorio del checkpoint local no contiene `.git`.
- Se clono `https://github.com/Shirobe95/FutonEspaiHUB.git` dentro de `FutonEspaiHUB/`.
- Git informo: `warning: You appear to have cloned an empty repository.`
- En ese clon vacio se creo la rama `refactor/modularizacion-v1`.
- La unica base de codigo disponible para descubrir y refactorizar es este checkpoint local.

Riesgo operativo: antes de hacer commits utiles hay que decidir si se importa el checkpoint completo al clon vacio como commit base de la rama, o si se proporciona otro remoto/historial con contenido. No se debe trabajar sobre `main`.

## Documentos leidos

Leidos completos y en orden:

1. `auditoria/AUDITORIA_FUNCIONAL_V1.md`
2. `auditoria/MAPA_FUNCIONAL_CODIGO.md`
3. `auditoria/PLAN_REFACTORIZACION_CODEX.md`
4. `CHECKPOINT_V62_1_CODEX.md`
5. `CODEX_REVIEW_BRIEF_FUTONHUB_V13.md`
6. `ESTRUCTURA_PROYECTO.md`
7. `README.md`
8. `README_CHECKPOINT_V13.md`
9. `docs/ROADMAP_FUTONHUB.md`
10. `docs/FUNCTIONAL_INVENTORY.md`

Contrato vigente para esta fase:

- Abrir siempre mediante `Abrir ERP.bat`.
- Preservar comportamiento actual.
- No cambiar reglas comerciales, esquemas, RLS, RPC, tablas o columnas.
- No exponer ni sustituir `.env`.
- No anadir sincronizacion automatica general Inventario -> Woo.
- No tocar precio efectivo, relectura Woo, log/snapshot persistidos ni rollback real.
- No eliminar legacy sin demostrar consumidores.

## Baseline de tests

Comando ejecutado:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 11 tests in 2.238s
OK
```

Cobertura real observada:

- Arquitectura legacy/canonica basica.
- Existencia de navegacion del ERP prototype.
- Reexport de servicios legacy hacia `futonhub`.
- Validaciones basicas de precio.
- Payload de rollback interno.
- Rechazo de status desconocido en propuestas.

Huecos:

- No hay tests de caracterizacion suficientes sobre `prototype.py`.
- No hay tests directos para clasificacion Woo, enlace por `woo_id`/SKU/alias, padres variables, productos test, packs/componentes, payload efectivo Woo, persistencia log/snapshot o rollback Woo real con dobles.

## Entrypoints reales

### Entrada oficial de usuario

`Abrir ERP.bat`

Flujo observado:

```text
Abrir ERP.bat
  -> cd GestorWoo
  -> python/py -3 gestorwoo.py erp-prototype
```

Regla: no cambiar esta entrada ni sustituirla por otro lanzador.

### Bootstrap alternativo historico

`abrir_futon_espai.py`

Flujo observado:

```text
abrir_futon_espai.py
  -> GestorWoo/gestorwoo.py hub
```

Estado: historico/compatibilidad. No es la entrada oficial de esta fase.

### CLI principal

`GestorWoo/gestorwoo.py`

Flujo observado:

```text
GestorWoo/gestorwoo.py
  -> inserta GestorWoo/src en sys.path
  -> futonhub.app.cli.main()
```

`futonhub.app.cli` reexporta desde `gestorwoo.cli`.

### Comando ERP actual

`gestorwoo.cli`

```text
erp-prototype
  -> futonhub.ui.erp.prototype.run_erp_prototype()
  -> FutonHubErpPrototype()
```

### HUB anterior

`hub`

```text
hub
  -> futonhub.app.hub.run_hub()
  -> futonhub.ui.erp.hub.FutonEspaiHub
```

Estado: UI/HUB anterior con mixins. Mantener por compatibilidad; no convertir en entrada oficial de usuario.

## Grafo de imports resumido

```text
Abrir ERP.bat
  -> GestorWoo/gestorwoo.py
    -> futonhub.app.cli
      -> gestorwoo.cli
        -> futonhub.ui.erp.prototype.run_erp_prototype
          -> FutonHubErpPrototype
```

```text
GestorWoo/FutonEspaiLauncher.py
  -> futonhub.app.cli
```

```text
futonhub.app.hub
  -> futonhub.ui.erp.hub
    -> login/diagnostics/project_catalog/project_cards/launching/cloud_* mixins
```

```text
futonhub.ui.erp.prototype
  -> tkinter, ttk, filedialog, messagebox, simpledialog
  -> openpyxl
  -> pypdf dentro de carga PDF
  -> futonhub.cloud.auth
  -> futonhub.cloud.audit legacy aliases
  -> futonhub.cloud.services.inventory
  -> futonhub.cloud.services.price_proposals
  -> futonhub.cloud.services.orders
  -> futonhub.cloud.services.woocommerce_publish
  -> futonhub.cloud.services.woocommerce_sync_preview
  -> futonhub.cloud.services.supplier_prices
  -> futonhub.cloud.services.business_constants
  -> futonhub.cloud.services.security_logs
  -> futonhub.core.config
  -> futonhub.core.guard
  -> futonhub.ui.theme
  -> futonhub.ui.windowing
```

```text
gestorwoo.cloud.services.*
  -> reexport parcial de futonhub.cloud.services.*
```

## Dependencias directas de `prototype.py`

Servicios y funciones importadas:

- Auth/sesion:
  `SupabaseAuthError`, `register_device_seen`, `sign_in_with_password`
- Inventario:
  `list_cloud_inventory_items`, `search_cloud_inventory_items`, `fetch_inventory_item_history`, `fetch_inventory_pack_components`, `preview_internal_inventory_update`, `update_inventory_item_fields`, `preview_create_cloud_inventory_item`, `create_cloud_inventory_item`
- Propuestas precio:
  `list_real_price_proposals`, `create_real_price_proposal`, `preview_existing_price_proposal`, `format_existing_price_proposal_preview`, `review_latest_real_price_proposal`, `delete_real_price_proposal_group`
- Publicacion Woo:
  `preview_woocommerce_publish`, `format_woocommerce_publish_preview`, `publish_woocommerce_price`
- Sync Woo:
  `build_sync_preview`, `export_preview_json`, `apply_manual_classification_edit`, `search_manual_link_inventory_candidates`, `preview_manual_woo_link`, `format_manual_woo_link_preview`, `apply_manual_woo_link`
- Pedidos:
  `list_cloud_supplier_orders`, `list_cloud_supplier_order_items`, `create_supplier_order_draft`, `update_supplier_order_draft`, `update_supplier_order_calculation`, `cancel_supplier_order`, `preview_receive_supplier_order`, `receive_supplier_order`, `summarize_order_items`, `format_order_date`, `order_display_name`
- Precios proveedor:
  `list_supplier_price_inventory_items`, `get_supplier_price`, `update_supplier_price_inventory_item`
- Constantes:
  `DEFAULT_BUSINESS_CONSTANTS`, `list_business_constants`, `save_business_constants`
- Seguridad:
  `list_security_audit_logs`, `security_log_kpis`, `get_snapshot_by_operation`, `build_before_after_diff`, `preview_restore_snapshot`, `restore_snapshot_to_previous_state`, `export_security_logs_excel`
- Legacy audit:
  `legacy_list_audit_logs`, `legacy_list_operation_snapshots`
- Guard/config:
  `load_settings`, `active_locks`, `stale_locks`
- UI comun:
  `apply_theme`, `center_window`

Dependencias locales/terceros:

- `tkinter`, `threading`, `csv`, `json`, `os`, `re`, `unicodedata`, `warnings`
- `openpyxl`
- `pypdf` importado dentro de flujo PDF

## Servicios consumidos por cada vista

### Shell/login/topbar

- `futonhub.cloud.auth`
- `futonhub.core.config`
- `futonhub.ui.theme`
- `futonhub.ui.windowing`

### Dashboard

- Pedidos: `list_cloud_supplier_orders`
- Propuestas: `list_real_price_proposals`
- Seguridad/logs: `list_security_audit_logs`, `security_log_kpis`
- Locks: `active_locks`, `stale_locks`

### Inventario

- Inventario cloud completo.
- Propuestas de precio para llevar item a Cambio de Precios.
- Exportacion local con `openpyxl`.

### Cambio de Precios

- Inventario cloud para busqueda de items.
- Propuestas de precio.
- Publicacion Woo preview/execute.

### Pedidos

- `orders.py`
- `supplier_prices.py`
- `business_constants.py`
- Importacion Excel con `openpyxl`.
- Importacion PDF con `pypdf`.
- Exportacion auditoria Excel con `openpyxl`.

### WooCommerce

- `woocommerce_sync_preview.py`
- `woocommerce_publish.py` para preview/publicacion de propuestas aprobadas.
- Inventario indirecto mediante candidatos de enlace manual.

### Precios proveedor

- `supplier_prices.py`

### Informes/exportaciones

- Actualmente principalmente `EXPORT_RECORDS` en memoria.
- Exportaciones reales existen dispersas en Inventario, Pedidos y Seguridad.

### Configuracion

- `business_constants.py` para calculos.
- Generales y Seguridad tienen partes visuales/mock segun auditoria.

### Seguridad/logs/snapshots

- `security_logs.py`
- `futonhub.cloud.audit` legacy aliases
- `core.guard`
- Exportacion Excel.

## Secciones principales de `prototype.py`

Por lineas aproximadas:

- 84-253: constantes visuales y dataclasses UI.
- 255-607: datos estaticos/mock (`NAV_ITEMS`, inventario demo, propuestas demo, pedidos demo, Woo demo, export records).
- 635-1071: shell, sidebar, topbar, login y navegacion.
- 1072-1351: dashboard.
- 1352-2895: inventario.
- 2904-4094: cambio de precios.
- 4095-6778: pedidos.
- 6779-7622: WooCommerce.
- 7623-7883: precios proveedor.
- 7884-8107: informes/exportaciones.
- 8108-8287: configuracion.
- 8288-8996: seguridad/logs/snapshots.
- 8997-9254: helpers UI compartidos.
- 9258: `run_erp_prototype`.

## Duplicados y rutas legacy

Duplicados/compatibilidad observada:

- Dos UIs ERP:
  - `futonhub.ui.erp.prototype` = entrada oficial actual via `Abrir ERP.bat`.
  - `futonhub.ui.erp.hub` = HUB anterior con mixins.
- Dos caminos de apertura:
  - `Abrir ERP.bat` -> `erp-prototype` vigente.
  - `abrir_futon_espai.py` / `ABRIR_FUTON_ESPAI.bat` -> historicos.
- Namespace canonico y legacy:
  - `futonhub.*` implementa servicios modernos.
  - `gestorwoo.*` conserva CLI, wrappers y herramientas antiguas.
- Servicios legacy reexport:
  - `gestorwoo.cloud.services.*` reexporta parte de `futonhub.cloud.services.*`.
- Rollback:
  - `futonhub.cloud.services.security_logs` contiene flujo moderno para seguridad/snapshots.
  - `futonhub.cloud.services.rollback` y `gestorwoo.cloud.services.rollback` mantienen logica legacy/general.
- CalculoCoste:
  - `CalculoCoste/` sigue como aplicacion legacy paralela.
  - `futonhub.modules.cost.launcher` existe como entrada canonica parcial.
- Informes:
  - Modulo general usa `EXPORT_RECORDS` estatico.
  - Exportaciones reales estan embebidas en vistas concretas.

## Funciones sin referencias aparentes

Metodo usado: busqueda estatica por nombre en el checkpoint. Esto no prueba ausencia de uso porque Tkinter puede invocar callbacks, comandos, lambdas, closures o referencias dinamicas.

Candidatas a revisar, no eliminar:

- Entry/UI legacy:
  - `futonhub.ui.erp.hub.FutonEspaiHub` y sus mixins, si `hub` deja de ser necesario.
  - `gestorwoo.ui.run_app`, `gestorwoo.inventory.run_inventory_app`, `gestorwoo.backup.run_backup_app`, `gestorwoo.security.run_logs_app`, usados por CLI legacy.
- Datos demo en `prototype.py`:
  - `INVENTORY_ITEMS`, `SAVED_PROPOSALS`, `SUPPLIER_ORDERS`, `WOO_DIFFERENCES`, `EXPORT_RECORDS` tienen uso parcial como fallback/mock. No eliminar hasta sustituir con tests y evidencia.
- `legacy_list_audit_logs` y `legacy_list_operation_snapshots` se mantienen como fallback de seguridad. Confirmar consumidores antes de retirar.
- Comandos BAT de `scripts/testing` y `scripts/admin` son herramientas operativas/historicas; no borrar en esta fase.

Hallazgo adicional a revisar fuera de la refactorizacion estructural:

- En `gestorwoo.cli`, la rama `cloud-supplier-prices-diagnostic` parece devolver una tupla/llamadas incorrectas en vez de ejecutar solo `run_cloud_supplier_prices_diagnostic()`. Marcar como bug candidato; no mezclar con modularizacion sin aprobacion.

## Riesgos

1. El remoto clonado esta vacio; no hay historial para comparar ni `main` real con contenido.
2. `prototype.py` concentra UI, estado, callbacks, formato, import/export y orquestacion.
3. Los servicios criticos se importan directamente desde la UI; mover metodos puede crear ciclos si se extrae sin adaptadores.
4. La suite actual no caracteriza los flujos criticos validados E2E.
5. Hay mocks mezclados con datos reales en el mismo archivo.
6. Hay multiples entrypoints historicos que pueden confundir pruebas manuales.
7. Woo precio efectivo depende de `regular_price` y `sale_price`; cualquier helper duplicado puede romper el contrato.
8. Publicacion Woo exige escribir, releer, verificar y persistir log/snapshot antes de exito.
9. Pedidos contiene muchas reglas de negocio en UI; extraerlo pronto seria alto riesgo.
10. Legacy no debe borrarse hasta demostrar consumidores.

## Propuesta de cortes modulares

Corte 0: base Git

- Resolver con el usuario si se importa el checkpoint al clon vacio como commit base en `refactor/modularizacion-v1`.
- No tocar `main`.

Corte 1: caracterizacion

- Anadir tests sin mover codigo:
  - entrypoint `Abrir ERP.bat` contiene `gestorwoo.py erp-prototype`;
  - `NAV_ITEMS` conserva labels y orden esperado;
  - `_effective_woo_price` y `_pricing_payload_for_effective_price`;
  - clasificacion Woo y productos test;
  - enlace manual preview/apply con dobles;
  - persistencia log/snapshot con mocks;
  - rollback precio restaura `regular_price` y `sale_price`;
  - componentes de packs con dobles.

Corte 2: shell y UI compartida

- Extraer dataclasses/constantes visuales a `futonhub/ui/erp/shared.py` o `shared/ui.py`.
- Extraer helpers UI de bajo riesgo: `_status_chip`, `_button`, `_field`, `_combo_field`, `_card`, `_show_working_overlay`, `_close_working_overlay`.
- Mantener `FutonHubErpPrototype` como adaptador temporal que hereda o delega.

Corte 3: navegacion

- Extraer `NAV_ITEMS`, sidebar, topbar, `_show_view`, `_page_header`.
- Mantener mismas keys y callbacks.

Corte 4: dashboard

- Extraer dashboard despues de que shell sea estable.
- Tests de datos recolectados con servicios mock.

Corte 5: inventario

- Extraer vista inventario y modales.
- Mantener servicios intactos.
- Tests de formato/estado/pack components.

Corte 6: WooCommerce

- Extraer sync preview, clasificacion, enlace manual y preview JSON.
- Tests de productos test, padres variables, SKU/alias.

Corte 7: cambio de precios

- Extraer propuestas y publicacion Woo.
- Requiere tests de caracterizacion mas fuertes antes de mover.

Corte 8: seguridad/logs

- Extraer vista de seguridad, diff, snapshot y rollback.
- Mantener verificacion de persistencia.

Corte 9: proveedores, pedidos, informes, configuracion

- Proveedores antes que pedidos.
- Pedidos al final por densidad y riesgo.
- Informes/configuracion deben conservar honestidad funcional: no convertir mocks en "real" en esta fase.

## Plan de commits pequenos

1. `docs: add initial modularization discovery`
2. `test: characterize erp entrypoint and navigation contract`
3. `test: characterize woo pricing payload and effective price`
4. `test: characterize woo sync classification and link rules`
5. `test: characterize logs snapshots and price rollback`
6. `refactor: extract erp shared ui primitives`
7. `refactor: extract erp shell and navigation`
8. `refactor: extract dashboard view`
9. `refactor: extract inventory view`
10. `refactor: extract woocommerce view`
11. `refactor: extract price changes view`
12. `refactor: extract security logs view`
13. `refactor: extract supplier prices view`
14. `refactor: extract orders view`
15. `refactor: extract reports and settings views`

Cada commit estructural debe incluir:

- tests ejecutados;
- imports verificados;
- archivos movidos;
- checklist manual;
- actualizacion de auditoria.

## Checklist manual inicial

Antes de aceptar cualquier extraccion:

- Abrir con `Abrir ERP.bat`.
- Login Supabase visible.
- Dashboard carga sin romper.
- Navegacion conserva:
  Dashboard, Inventario, Cambio de Precios, Pedidos, WooCommerce, Informes / Exportaciones, Configuracion, Seguridad / Logs.
- Inventario busca y abre detalle.
- Packs/componentes se muestran sin recursion ni nombres vacios.
- Cambio de Precios lista propuestas y abre preview.
- Preview Woo no publica.
- Publicacion Woo exige confirmacion y no declara exito sin relectura.
- Seguridad muestra logs/snapshots y rollback preview.
- Rollback precio real restaura `regular_price` y `sale_price`.
- Informes/configuracion no aparentan mas funcionalidad de la existente.


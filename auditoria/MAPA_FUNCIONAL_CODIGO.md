# FutonHUB · Mapa funcional y de código para Codex

**Checkpoint:** v62.1 Codex Handoff  
**Fecha:** 2026-06-14  
**Propósito:** indicar qué existe, dónde vive, qué se ha probado y qué no debe alterarse durante la primera refactorización.

> Regla central: la primera fase es una refactorización de preservación de comportamiento. No se añaden funciones, no se cambian reglas comerciales y no se “simplifica” lógica sin una prueba equivalente.

---

## 1. Entrada oficial

| Elemento | Ruta | Estado | Regla |
|---|---|---|---|
| Entrada oficial | `Abrir ERP.bat` | Operativo | Debe seguir siendo la forma oficial de abrir el ERP |
| CLI ejecutada por la entrada oficial | `GestorWoo/gestorwoo.py` | Operativo | `Abrir ERP.bat` la invoca con `erp-prototype` |
| Dispatcher real | `gestorwoo.cli` | Operativo | Resuelve el comando `erp-prototype` |
| ERP actual | `futonhub.ui.erp.prototype` | Operativo | Contiene `FutonHubErpPrototype` y `run_erp_prototype` |
| Lanzador alternativo/historico | `abrir_futon_espai.py` | Legacy util | No es la entrada oficial de esta fase |
| Soporte launcher/build | `GestorWoo/FutonEspaiLauncher.py` | Soporte build | Mantener compatibilidad |
La UI ERP real se concentra actualmente en:

```text
GestorWoo/src/futonhub/ui/erp/prototype.py
```

Este archivo tiene aproximadamente 9.260 líneas y contiene navegación, vistas, modales, orquestación y parte de la lógica de presentación.

---

## 2. Capas existentes

```text
Abrir ERP.bat
  └─ GestorWoo/gestorwoo.py erp-prototype
      └─ gestorwoo.cli
          └─ futonhub.ui.erp.prototype
              └─ GestorWoo/src/futonhub/ui/erp/prototype.py
                  ↓
GestorWoo/src/futonhub/cloud/services/
  ├─ inventory.py
  ├─ price_proposals.py
  ├─ woocommerce_publish.py
  ├─ woocommerce_sync_preview.py
  ├─ orders.py
  ├─ supplier_prices.py
  ├─ business_constants.py
  ├─ security_logs.py
  └─ rollback.py
              ↓
GestorWoo/src/futonhub/cloud/
  ├─ client.py
  ├─ auth.py
  ├─ audit.py
  ├─ permissions.py
  ├─ locks.py
  └─ operational.py
              ↓
Supabase / WooCommerce / archivos locales
```

---

## 3. Mapa por módulo

### 3.1 Login y sesión

**UI / orquestación**
- `ui/erp/prototype.py`
  - `_show_startup_login`
  - `_login_supabase`
  - `_finish_login`
  - `_render_session_status`
- `ui/erp/login.py`
- `ui/erp/launching.py`

**Backend**
- `cloud/auth.py`
- `cloud/client.py`
- `cloud/permissions.py`

**Comportamiento validado**
- Login Supabase real.
- Lectura de rol.
- Sesión admin/worker.
- Restricciones visuales y varias validaciones backend.

**No asumir**
- No existe todavía una consola ERP completa para gestionar usuarios, roles y dispositivos.

---

### 3.2 Dashboard

**UI**
- `prototype.py`
  - `_build_dashboard`
  - `_dashboard_collect_data`
  - `_dashboard_show_attention`
  - `_dashboard_activity_card`
  - `_dashboard_system_card`

**Servicios consumidos**
- pedidos, propuestas y seguridad/logs.

**Estado**
- Implementado con datos reales en varias tarjetas.
- Requiere prueba de consistencia completa antes de declararlo terminado.

---

### 3.3 Inventario

**UI**
- `prototype.py`
  - `_build_inventory`
  - `_refresh_inventory`
  - `_open_create_inventory_item_modal`
  - `_open_inventory_detail_window`
  - `_open_inventory_stock_preview_modal`
  - `_open_inventory_changes_review`
  - `_apply_inventory_detail_changes`
  - `_render_inventory_history`
  - `_export_inventory_visible`
  - `_render_inventory_pack_inline_box`
  - `_open_inventory_pack_contents_popup`
  - `_carry_inventory_item_to_prices`

**Backend principal**
- `cloud/services/inventory.py`
  - `list_cloud_inventory_items`
  - `search_cloud_inventory_items`
  - `fetch_inventory_pack_components`
  - `preview_internal_inventory_update`
  - `update_internal_inventory_item`
  - `fetch_inventory_item_history`
  - `preview_inventory_item_field_update`
  - `update_inventory_item_fields`
  - `preview_create_cloud_inventory_item`
  - `create_cloud_inventory_item`

**Importación**
- `cloud/services/inventory_item_import.py`

**Validado**
- Lectura, búsqueda, detalle, edición interna, stock interno, creación, exportación visible.
- Packs y componentes visibles.
- 1.116 relaciones de componentes resueltas.

**Límite**
- Editar Inventario no publica automáticamente todos los campos en Woo.
- Debe conservarse esta separación hasta definir una matriz de sincronización explícita.

---

### 3.4 WooCommerce: lectura, clasificación y enlace

**UI**
- `prototype.py`
  - `_build_woocommerce`
  - `_refresh_woo_sync_preview`
  - `_finish_woo_sync_preview`
  - `_open_woo_classification_edit_modal`
  - `_open_woo_manual_link_modal`
  - `_export_woo_sync_preview_json`
  - `_render_woo_sync_detail`

**Backend**
- `cloud/services/woocommerce_sync_preview.py`
  - `load_woocommerce_items`
  - `load_inventory_items`
  - `classify_woo_item`
  - `normalize_sku`
  - `find_inventory_match`
  - `search_manual_link_inventory_candidates`
  - `preview_manual_woo_link`
  - `apply_manual_woo_link`
  - `apply_manual_classification_edit`
  - `build_sync_preview`
  - `export_preview_json`

**Validado E2E**
- 778 elementos Woo analizados.
- 646 enlaces operativos.
- 0 pendientes operativos.
- 0 críticos.
- Productos test excluidos.
- Padres variables informativos.
- SKU compartido padre/variación resuelto a favor de la variación.
- Packs, alias y componentes relacionados.

**No cambiar sin tests**
- Normalización SKU.
- Reglas de padre variable.
- Detección de productos test.
- Lógica de packs con SKU compuesto.
- Priorización `woo_id` / SKU / alias.

---

### 3.5 Propuestas y publicación de precios

**UI**
- `prototype.py`
  - `_build_prices`
  - `_build_saved_proposals_workspace`
  - `_build_price_edit_workspace`
  - `_refresh_price_proposals`
  - `_open_price_proposal_preview`
  - `_open_price_review_modal`
  - `_save_price_edit`
  - `_open_woo_publish_preview_modal`

**Propuestas**
- `cloud/services/price_proposals.py`
  - `preview_real_price_proposal`
  - `create_real_price_proposal`
  - `review_latest_real_price_proposal`
  - `delete_real_price_proposal_group`
  - `list_real_price_proposals`

**Publicación Woo**
- `cloud/services/woocommerce_publish.py`
  - `_effective_woo_price`
  - `_pricing_payload_for_effective_price`
  - `_ensure_snapshot_persisted`
  - `_ensure_audit_persisted`
  - `preview_woocommerce_publish`
  - `publish_woocommerce_price`

**Rollback**
- `cloud/services/security_logs.py`
  - `preview_restore_snapshot`
  - `restore_snapshot_to_previous_state`
- `cloud/services/rollback.py`
  - lógica legacy/general de rollback

**Validado E2E**
- Propuesta 128 → 138.
- Woo muestra precio efectivo 138.
- Relectura posterior confirma el valor.
- Audit log y snapshot persistidos.
- Rollback real devuelve Woo a 128.
- Estado `rolled_back` aceptado y visible.

**Reglas que no deben romperse**
- Si hay `sale_price` activo, el precio efectivo no es `regular_price`.
- No declarar éxito sin relectura Woo.
- No publicar si snapshot previo no quedó persistido.
- No cerrar operación sin verificar audit log.
- Rollback debe restaurar `regular_price` y `sale_price`, no solo un valor genérico.

---

### 3.6 Pedidos

**UI**
- `prototype.py`, aproximadamente líneas 4095–6778.
- Importación Excel/PDF.
- Editor de líneas.
- Cálculo en memoria.
- Guardado borrador.
- Exportación Excel.
- Recepción.
- Cancelación y borrado.

**Backend**
- `cloud/services/orders.py`
  - `list_cloud_supplier_orders`
  - `list_cloud_supplier_order_items`
  - `create_supplier_order_draft`
  - `update_supplier_order_draft`
  - `update_supplier_order_calculation`
  - `cancel_supplier_order`
  - `preview_receive_supplier_order`
  - `receive_supplier_order`

**Dependencias**
- `supplier_prices.py`
- `business_constants.py`
- lógica legacy en `CalculoCoste/`

**Estado**
- Mucha lógica real.
- No declarar completo hasta una campaña E2E:
  importación → cálculo → guardado → reapertura → recepción → stock → coste ponderado → log/snapshot.

---

### 3.7 Precios de proveedor

**UI**
- `prototype.py`
  - `_build_suppliers`
  - `_build_supplier_prices`

**Backend**
- `cloud/services/supplier_prices.py`
  - lectura legacy local
  - preview de migración
  - migración Supabase
  - resolución de precio por proveedor
  - diagnóstico
  - edición

**Estado**
- Implementado.
- Falta prueba E2E documentada desde edición hasta consumo real en pedido.

---

### 3.8 Seguridad, logs, snapshots y rollback

**UI**
- `prototype.py`
  - `_build_security`
  - `_render_security_workspace`
  - `_refresh_security_data`
  - `_open_security_log_detail`
  - `_render_before_after_diff`
  - `_open_snapshot_detail_modal`
  - `_restore_snapshot_from_security_detail`
  - `_export_visible_security_logs`

**Backend**
- `cloud/services/security_logs.py`
- `cloud/audit.py`
- `cloud/locks.py`
- RPC y RLS en `docs/supabase/`

**Validado**
- Log y snapshot para publicación de precio.
- Verificación de persistencia.
- Rollback real de precio.

**Pendiente**
- Probar rollback y snapshots de inventario, pedidos y otras entidades.
- Revisar si todos los módulos generan caja negra de forma homogénea.

---

### 3.9 Informes y exportaciones

**UI**
- `prototype.py`
  - `_build_reports`
  - `_render_export_detail`
  - `_open_new_export_modal`
  - `_open_export_action_modal`

**Estado**
- La ventana general es principalmente visual/mock.
- Existen exportaciones reales puntuales:
  - inventario visible;
  - auditoría de pedidos;
  - logs de seguridad.

**No declarar**
- No existe todavía un motor de informes general completo.

---

### 3.10 Configuración

**UI**
- `prototype.py`
  - `_build_settings`
  - `_render_settings_general`
  - `_render_settings_calculations`
  - `_render_settings_security`

**Backend real**
- `cloud/services/business_constants.py` para constantes de cálculo.

**Estado**
- Cálculos/constantes: lógica real.
- Generales: principalmente interfaz.
- Seguridad: switches visuales sin persistencia completa.

---

### 3.11 Legacy y paralelos

- `CalculoCoste/`
- comandos CLI y scripts BAT de diagnóstico/prueba.
- `GestorWoo/data/gestorwoo.sqlite3`
- lanzadores históricos.
- `cloud/services/rollback.py` frente al rollback moderno desde Seguridad.

**Regla**
No borrar durante la primera fase. Mover a `legacy/` solo después de:
1. identificar consumidores;
2. crear tests;
3. comprobar que no lo usa `Abrir ERP.bat`;
4. documentar sustituto.

---

## 4. Puntos de alto riesgo durante la refactorización

1. `prototype.py` mezcla UI, estado y orquestación.
2. `price_proposals.py` mezcla lógica operativa, legacy, tests y utilidades.
3. Hay dos caminos de rollback.
4. Existen varios lanzadores.
5. Hay scripts históricos que documentan reglas comerciales reales.
6. Los nombres de campos Supabase tienen compatibilidad histórica.
7. Las operaciones Woo requieren caja negra antes y después.
8. Los packs usan vistas y relaciones creadas por migraciones posteriores.
9. La configuración `.env` funcional no debe exponerse ni reemplazarse.
10. El programa debe seguir abriéndose con `Abrir ERP.bat`.

---

## 5. Arquitectura objetivo sugerida

```text
GestorWoo/src/futonhub/
├── app/
│   ├── bootstrap.py
│   ├── navigation.py
│   └── session.py
├── modules/
│   ├── dashboard/
│   ├── inventory/
│   ├── woocommerce/
│   ├── price_changes/
│   ├── orders/
│   ├── supplier_prices/
│   ├── security/
│   ├── reports/
│   └── settings/
├── infrastructure/
│   ├── supabase/
│   ├── woocommerce/
│   ├── files/
│   └── audit/
├── shared/
│   ├── models/
│   ├── validation/
│   ├── formatting/
│   └── ui/
└── tests/
```

Cada módulo debería contener, cuando aplique:

```text
models.py
service.py
repository.py
validators.py
ui.py
tests/
```

No es obligatorio imponer esta estructura exacta. Codex debe justificar cualquier alternativa y mantener dependencias unidireccionales.

---

## 6. Criterio de migración por módulo

Un módulo solo se considera extraído cuando:

- la UI se abre;
- conserva el comportamiento;
- no introduce importaciones circulares;
- tiene tests de caracterización;
- supera pruebas unitarias;
- supera prueba manual indicada;
- no cambia esquema ni datos;
- actualiza esta auditoría;
- documenta archivos antiguos que quedaron sin uso.

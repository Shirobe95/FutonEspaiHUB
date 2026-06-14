# FutonHUB - Corte 003 dashboard view

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract dashboard view
```

## Alcance

Tercer corte estructural autorizado:

- construccion visual del Dashboard;
- recoleccion y transformacion de datos usados exclusivamente por Dashboard;
- tarjetas, KPIs y acciones propias del Dashboard;
- helpers privados exclusivos de esta vista.

No se movieron Inventario, WooCommerce, Precios, Seguridad ni Pedidos.
No se tocaron servicios.
No se cambio el entrypoint.
`FutonHubErpPrototype` sigue siendo el adaptador principal.
La vista sigue invocandose desde `_show_view("dashboard")`.

## Simbolos movidos

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/dashboard.py
```

Mixin temporal:

```text
ErpDashboardMixin
```

Metodos movidos a `ErpDashboardMixin`:

```text
_build_dashboard
_dashboard_collect_data
_dashboard_show_attention
_dashboard_activity_card
_dashboard_attention_card
_dashboard_compact_list_card
_dashboard_system_card
```

Adaptador:

```text
class FutonHubErpPrototype(ErpDashboardMixin, ErpShellNavigationMixin, ErpSharedUiMixin, tk.Tk)
```

`_show_view` permanece en `shell.py` y conserva la clave `dashboard` apuntando a `self._build_dashboard`.

## Simbolos no movidos

No se movio `_update_dashboard_detail` porque no tiene referencias actuales. Queda fuera del corte para evitar trasladar codigo sin consumidor demostrado.

No se movieron helpers compartidos con Seguridad u otras vistas:

```text
_format_datetime_short
_normalize_security_level
```

El mixin de Dashboard los consume desde `FutonHubErpPrototype`.

## Dependencias sobre estado de instancia

`ErpDashboardMixin` asume atributos ya inicializados por `FutonHubErpPrototype.__init__` o por shell/login:

```text
_cloud_session
_current_key
```

Tambien llama a metodos definidos en otros mixins o en el adaptador:

```text
_page_header
_metric
_card
_status_row
_button
_show_view
_format_datetime_short
_normalize_security_level
```

## Servicios consumidos

La recoleccion del Dashboard consume los mismos servicios que antes, ahora desde `dashboard.py`:

```text
futonhub.cloud.services.orders.list_cloud_supplier_orders
futonhub.cloud.services.orders.order_display_name
futonhub.cloud.services.price_proposals.list_real_price_proposals
futonhub.cloud.services.security_logs.list_audit_logs
```

No se modificaron firmas, queries, payloads, esquemas Supabase, RLS, RPC, tablas ni columnas.

## Tests de caracterizacion anadidos

Nuevo archivo:

```text
GestorWoo/tests/test_characterization_dashboard.py
```

Comportamiento protegido:

- sin sesion cloud no se llaman servicios y se devuelven sistemas offline;
- se agregan pedidos abiertos, pedidos en validacion, recepciones parciales, propuestas pendientes, actividad reciente y errores de hoy;
- errores de un servicio se registran en `data["errors"]` sin bloquear las demas secciones.

Los tests usan dobles/mocks sobre el modulo `futonhub.ui.erp.dashboard` y no escriben en WooCommerce ni Supabase.

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/dashboard.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/tests/test_characterization_dashboard.py
auditoria/CODEX_CORTE_003_DASHBOARD.md
```

## Tests

Antes del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 40 tests in 0.069s
OK
```

Verificacion de imports/compilacion tras mover simbolos:

```powershell
python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/ui/erp/dashboard.py GestorWoo/src/futonhub/ui/erp/shell.py GestorWoo/src/futonhub/ui/erp/shared_ui.py GestorWoo/tests/test_characterization_dashboard.py
```

Resultado:

```text
OK
```

Despues del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 43 tests in 0.079s
OK
```

## Checklist manual

Pendiente de ejecutar manualmente por requerir UI/login:

- `Abrir ERP.bat`
- login
- abrir Dashboard
- revisar KPIs superiores
- revisar Actividad reciente
- revisar Bloques de atencion
- revisar Pedidos recientes
- revisar Estado de sistemas
- navegacion Dashboard -> Inventario -> Dashboard
- navegacion Dashboard -> Precios -> Dashboard
- navegacion Dashboard -> Pedidos -> Dashboard
- acciones contextuales:
  - click en KPI con modal
  - boton `Ir al modulo`
  - boton `Cerrar`
  - botones `Ver`
  - boton `Ver modulo`
- cierre del ERP

Checklist tecnico automatizado:

- `prototype.py` compila.
- `dashboard.py` compila.
- La suite completa sigue pasando.
- No se tocaron servicios.
- No se movieron vistas funcionales ajenas al Dashboard.

## Limitaciones

- No se ejecuta login real en tests automaticos.
- No se abre Tkinter durante la suite automatica.
- No se escribe en WooCommerce ni Supabase.

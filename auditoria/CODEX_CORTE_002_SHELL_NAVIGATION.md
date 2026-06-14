# FutonHUB - Corte 002 shell and navigation

Fecha: 2026-06-15

Commit previsto:

```text
refactor: extract erp shell and navigation
```

## Alcance

Segundo corte estructural autorizado:

- `NAV_ITEMS`;
- sidebar;
- topbar;
- cabecera de pagina;
- seleccion y cambio de vista;
- resaltado del elemento activo;
- contenedor principal;
- helpers estrictamente necesarios para navegacion.

No se movieron Dashboard ni vistas funcionales.
No se tocaron servicios.
No se cambio el entrypoint.
`FutonHubErpPrototype` sigue siendo el adaptador principal.

## Simbolos movidos

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/shell.py
```

Constante de navegacion movida:

```text
NAV_ITEMS
```

Mixin temporal movido:

```text
ErpShellNavigationMixin
```

Metodos movidos a `ErpShellNavigationMixin`:

```text
_build_shell
_build_sidebar
_build_topbar
_render_session_status
_show_view
_page_header
```

Adaptador:

```text
class FutonHubErpPrototype(ErpShellNavigationMixin, ErpSharedUiMixin, tk.Tk)
```

`prototype.py` sigue importando y reexportando `NAV_ITEMS`, de modo que los consumidores existentes como tests o imports directos no cambian.

## Dependencias sobre estado de instancia

`ErpShellNavigationMixin` asume los atributos ya inicializados por `FutonHubErpPrototype.__init__`:

```text
_nav_buttons
_content
_status_area
_cloud_session
_current_key
```

Tambien llama a metodos que siguen definidos en `FutonHubErpPrototype` o `ErpSharedUiMixin`:

```text
_status_chip
_button
_page_header_action_command
_build_dashboard
_build_inventory
_build_prices
_build_order_calc
_build_woocommerce
_build_supplier_prices
_build_reports
_build_settings
_build_security
```

No se introducen dependencias hacia servicios cloud ni hacia modulos funcionales extraidos.

## Compatibilidad

Se mantiene:

- `Abrir ERP.bat` como entrada oficial.
- `gestorwoo.cli` apuntando a `futonhub.ui.erp.prototype.run_erp_prototype`.
- `FutonHubErpPrototype` en `futonhub.ui.erp.prototype`.
- `NAV_ITEMS` importable desde `futonhub.ui.erp.prototype`.
- Mixin `ErpSharedUiMixin` y reexportaciones del corte 001.

Las dataclasses especificas de dominio permanecen temporalmente en `shared_ui.py` y quedan marcadas en codigo como candidatas a trasladarse cuando se extraigan sus modulos. No se agregaron nuevos modelos de dominio a ese archivo.

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/shell.py
GestorWoo/src/futonhub/ui/erp/prototype.py
GestorWoo/src/futonhub/ui/erp/shared_ui.py
auditoria/CODEX_CORTE_002_SHELL_NAVIGATION.md
```

## Tests

Antes del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 40 tests in 0.072s
OK
```

Verificacion de imports/compilacion tras mover simbolos:

```powershell
python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/ui/erp/shared_ui.py GestorWoo/src/futonhub/ui/erp/shell.py
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
Ran 40 tests in 0.074s
OK
```

No se anadieron tests nuevos porque la red existente ya protege:

- entrypoint oficial;
- dispatcher `erp-prototype`;
- claves, labels, grupos y orden de navegacion;
- permanencia de los metodos de vista en `FutonHubErpPrototype`.

## Checklist manual

Pendiente de ejecutar manualmente por requerir UI/login:

- `Abrir ERP.bat`
- login
- sidebar
- cambio entre todas las vistas:
  - Dashboard
  - Inventario
  - Cambio de Precios
  - Pedidos
  - WooCommerce
  - Precio Proveedores
  - Informes / Exportaciones
  - Seguridad / Logs
  - Configuracion
- cierre del ERP

Checklist tecnico automatizado:

- `prototype.py` compila.
- `shell.py` compila.
- La suite completa sigue pasando.
- No se tocaron servicios.
- No se movieron vistas funcionales.

## Limitaciones

- No se ejecuta login real en tests automaticos.
- No se abre Tkinter durante la suite automatica.
- No se escribe en WooCommerce ni Supabase.

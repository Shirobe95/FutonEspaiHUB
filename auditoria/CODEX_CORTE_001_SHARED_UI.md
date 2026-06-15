# FutonHUB - Corte 001 shared UI primitives

Fecha: 2026-06-14

Commit previsto:

```text
refactor: extract erp shared ui primitives
```

Commit real:

```text
e00855ca4bc1fd69151b3ebe2a6b9a0867f85a8b
```

Hash padre:

```text
0adf26a1bfbc3899f8c499c5195da98c0ccbfb65
```

Estado de push:

```text
Pushed a origin/refactor/modularizacion-v1
```

## Alcance

Primer corte estructural autorizado:

- constantes visuales;
- dataclasses puramente UI;
- helpers de botones, tarjetas, campos y chips;
- overlays de trabajo;
- helpers UI compartidos de bajo riesgo.

No se movieron vistas funcionales completas.
No se tocaron servicios.
No se cambio el entrypoint.
`FutonHubErpPrototype` sigue siendo el adaptador principal.

## Simbolos movidos

Nuevo archivo:

```text
GestorWoo/src/futonhub/ui/erp/shared_ui.py
```

Constantes visuales movidas:

```text
BG
SIDEBAR
CARD
LINE
SOFT
TEXT
MUTED
INDIGO
INDIGO_SOFT
GREEN
GREEN_SOFT
BLUE
BLUE_SOFT
AMBER
AMBER_SOFT
ORANGE
ORANGE_SOFT
ROSE
ROSE_SOFT
STATUS_STYLES
```

Dataclasses UI movidas:

```text
NavItem
InventoryItem
ProposalLine
PriceProposal
OrderItem
SupplierOrder
WooDifference
ExportRecord
SecurityEvent
SecurityLogRow
```

Helpers UI movidos a `ErpSharedUiMixin`:

```text
_show_working_overlay
_close_working_overlay
_metric
_provider_card
_simple_card
_status_row
_status_chip
_button
_field
_combo_field
_constant_row
_setting_switch_row
_card
```

Adaptador:

```text
class FutonHubErpPrototype(ErpSharedUiMixin, tk.Tk)
```

`prototype.py` sigue importando y reexportando los nombres anteriores, de modo que los consumidores existentes como tests o imports directos no cambian.

## Archivos tocados

```text
GestorWoo/src/futonhub/ui/erp/shared_ui.py
GestorWoo/src/futonhub/ui/erp/prototype.py
auditoria/MAPA_FUNCIONAL_CODIGO.md
auditoria/CODEX_CORTE_001_SHARED_UI.md
```

## Tests

Antes del corte:

```powershell
python -m unittest discover -s GestorWoo\tests -v
```

Resultado:

```text
Ran 40 tests in 0.076s
OK
```

Verificacion de imports/compilacion tras mover simbolos:

```powershell
python -m py_compile GestorWoo/src/futonhub/ui/erp/prototype.py GestorWoo/src/futonhub/ui/erp/shared_ui.py
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
Ran 40 tests in 0.076s
OK
```

## Checklist manual

Pendiente de ejecutar manualmente por requerir UI/login:

- `Abrir ERP.bat`
- login
- sidebar
- navegacion
- overlay
- dashboard

Checklist tecnico automatizado:

- `Abrir ERP.bat` sigue apuntando a `gestorwoo.py erp-prototype`.
- `gestorwoo.cli` sigue resolviendo `erp-prototype`.
- `FutonHubErpPrototype` sigue en `futonhub.ui.erp.prototype`.
- No se tocaron servicios cloud.
- No se movieron vistas funcionales completas.

## Limitaciones

- No se ejecuta login real en tests automaticos.
- No se abre Tkinter durante la suite automatica.
- No se escribe en WooCommerce ni Supabase.

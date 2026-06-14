# Roadmap FutonHUB

Ultima actualizacion: 2026-05-31

Este documento sirve como continuidad tecnica para trabajar con Codex o ChatGPT si se agotan tokens, mensajes o contexto.

Plan UI-ERP v1: `docs/UI_ERP_PLAN.md`.
Revision Fase 1 UI-ERP: `docs/UI_ERP_FASE1_REVISION.md`.
Inventario funcional: `docs/FUNCTIONAL_INVENTORY.md`.
Referencia visual/funcional UI: `docs/ui_reference/`.

## Objetivo del proyecto

Convertir las herramientas separadas `GestorWoo` y `CalculoCoste` en un mini ERP modular para Futon Espai.

Prioridades:

1. Mantener la herramienta usable durante toda la migracion.
2. Evitar romper ejecutables, scripts y flujos antiguos.
3. Mover dominio y UI hacia el namespace canonico `futonhub`.
4. Preparar el proyecto para nuevos modulos futuros.

## Estado actual

### Supabase / seguridad

Implementado en Supabase:

- SQL 19 de hardening aplicado.
- RPC locks online verificados: `Locks online RPC: OK`.
- RLS/RPC reforzados para usuarios autenticados.
- Estados de propuestas incluyen `publishing`.
- Flujo de publicacion WooCommerce protegido con lock online.

### Servicios cloud

Implementacion real movida a:

```text
GestorWoo/src/futonhub/cloud/services/
```

Modulos actuales:

```text
prices.py
price_proposals.py
inventory.py
rollback.py
woocommerce_publish.py
```

Compatibilidad legacy:

```text
GestorWoo/src/gestorwoo/cloud/services/
```

Estos modulos legacy reexportan desde `futonhub.cloud.services`.

### UI principal

Implementacion real del HUB movida a:

```text
GestorWoo/src/futonhub/ui/erp/hub.py
```

Wrapper legacy:

```text
GestorWoo/src/gestorwoo/hub.py
```

Bloques grandes separados:

```text
futonhub/ui/erp/cloud_admin.py
futonhub/ui/erp/cloud_inventory.py
futonhub/ui/erp/cloud_prices.py
futonhub/ui/erp/diagnostics.py
futonhub/ui/erp/launching.py
futonhub/ui/erp/login.py
futonhub/ui/erp/models.py
futonhub/ui/erp/project_cards.py
futonhub/ui/erp/project_catalog.py
futonhub/ui/erp/prototype.py
futonhub/ui/erp/window_focus.py
```

`FutonEspaiHub` hereda de:

```text
LoginMixin
DiagnosticsMixin
ProjectCatalogMixin
ProjectCardsMixin
ProjectLaunchingMixin
CloudInventoryBoardMixin
CloudPriceBoardMixin
CloudAdminToolsMixin
tk.Tk
```

La UI ERP importa desde `futonhub.*` en lugar de depender directamente de `gestorwoo.*`, salvo rutas/compatibilidad legacy encapsulada.

Prototipo aislado disponible:

```powershell
python GestorWoo\gestorwoo.py erp-prototype
```

Incluye menu lateral oficial v2 con:

```text
Dashboard
Inventario
Cambio de Precios
Pedidos
WooCommerce
Informes / Exportaciones
Seguridad / Logs
Configuracion
```

Proveedores iniciales dentro de `Pedidos`:

```text
Ekomat
Pascal
Heimei
Cipta
```

El prototipo arranca con el ERP oculto, muestra popup de login real Supabase, y solo construye/muestra la UI tras autenticar. La topbar queda limpia: `Online` + rol.

### Compatibilidad

Entradas mantenidas:

```text
GestorWoo/gestorwoo.py
GestorWoo/FutonEspaiLauncher.py
ABRIR_FUTON_ESPAI.bat
crear_exe_windows.bat
crear_exe_windows_debug.bat
```

Nuevo namespace canonico:

```text
futonhub
```

`pyproject.toml` ya expone:

```text
futonhub = "futonhub.app.cli:main"
gestorwoo = "gestorwoo.cli:main"
```

## Verificacion actual

Ultima verificacion ejecutada:

```powershell
python -m unittest discover -s GestorWoo\tests -v
python -m compileall -q GestorWoo\src GestorWoo\gestorwoo.py GestorWoo\FutonEspaiLauncher.py CalculoCoste GestorWoo\tests abrir_futon_espai.py
python GestorWoo\gestorwoo.py --help
```

Resultado:

```text
Tests: 10/10 OK
compileall: OK
CLI help: OK
```

`__pycache__` limpiado tras la ultima compilacion.

## Proximos pasos recomendados

### 0. Plan UI-ERP en 3 fases

Fase actual:

```text
Fase 2 iniciada: Logica real y pruebas por modulo
```

Ruta acordada:

1. Revisar todos los disenos y ajustarlos a lo que FutonHUB realmente tiene o necesita.
2. Conectar logica real por modulo, con pruebas aisladas y flujos protegidos.
3. Pulir acabado visual: radios, sombras ligeras, espaciado, estados, modales y botones.

Regla:

- no mezclar pulido visual final con conexion de logica critica
- no conectar accion real sin validacion, confirmacion y log
- mantener `Main` fuera de cambios directos hasta que la UI nueva este validada

Primer modulo conectado:

```text
Seguridad / Logs
```

Estado:

- lectura real de `audit_logs` con sesion Supabase autenticada
- lectura real de `operation_snapshots`
- conteo de locks locales activos/caducados
- tabla de eventos y detalle de payload tecnico
- sin escrituras reales desde la UI

Segundo modulo conectado:

```text
Inventario
```

Estado:

- busqueda real en `inventory_items` Supabase desde la UI-ERP
- detalle visual alimentado por filas reales
- `cubic_meters` alimenta el M3 de calculo; `size` queda solo como medidas/dimensiones
- preview real de cambio interno de stock con `preview_internal_inventory_update`
- sin aplicar escrituras desde la UI
- WooCommerce no se toca

Tercer modulo conectado:

```text
Cambio de Precios
```

Estado:

- lectura real de `price_change_proposals` Supabase desde la UI-ERP
- bandeja visual alimentada por propuestas reales visibles para la sesion
- lista de propuestas con scroll y columna `Estado` alineada al estado real de negocio
- preview real de seguridad con `preview_existing_price_proposal`
- aprobar/rechazar conectado con modal protegido: preview real, confirmacion escrita, snapshot y audit log
- WooCommerce no se toca

Cuarto modulo conectado:

```text
WooCommerce
```

Estado:

- preview real de publicacion WooCommerce desde propuestas aprobadas
- lee Supabase y WooCommerce para detectar OK/WARNING/ERROR antes de publicar
- muestra resultado en modal de solo lectura
- no publica, no sincroniza y no ejecuta PUT

### 1. Terminar modularizacion UI

Separacion ya realizada:

```text
futonhub/ui/erp/login.py
futonhub/ui/erp/diagnostics.py
futonhub/ui/erp/project_catalog.py
futonhub/ui/erp/project_cards.py
futonhub/ui/erp/launching.py
```

Pendiente opcional antes del rediseño:

```text
futonhub/ui/erp/layout.py
futonhub/ui/erp/navigation.py
```

### 2. Reducir dependencia de `gestorwoo`

Wrappers base creados:

```text
futonhub/core/config.py
futonhub/core/pathing.py
futonhub/core/diagnostics.py
futonhub/core/guard.py
futonhub/cloud/audit.py
futonhub/cloud/auth.py
futonhub/cloud/client.py
futonhub/cloud/locks.py
futonhub/cloud/permissions.py
futonhub/cloud/operational.py
futonhub/ui/theme.py
futonhub/ui/windowing.py
```

Objetivo siguiente: mover la implementacion real de esos wrappers cuando sea necesario.

### 3. Migrar CalculoCoste

Estado actual:

```text
CalculoCoste/
```

sigue como carpeta legacy.

Entrada canonica existente:

```text
futonhub/modules/cost/launcher.py
```

Siguiente fase:

```text
futonhub/modules/cost/
```

mover logica real de calculo, manteniendo `CalculoCoste` como wrapper temporal.

### 4. Tests de import/arquitectura

Creado:

```text
GestorWoo/tests/test_architecture.py
```

Cubre:

- `gestorwoo.hub` sigue reexportando.
- `futonhub.ui.erp.hub` es la implementacion real.
- servicios legacy apuntan a `futonhub.cloud.services`.
- CLI legacy importa el HUB canonico.
- los bloques grandes del HUB viven en mixins separados.

### 5. Preparar nueva UI ERP

Referencia canonica importada:

```text
docs/ui_reference/FutonHUB_UI_pack_Codex_v2/
```

Reglas vigentes:

- HTML como referencia visual.
- Markdown como contrato funcional.
- No convertir selects en entries.
- No tocar `Main` directamente.
- Integrar visualmente primero.
- Conectar logica real despues con validacion, confirmacion y logs.

Cuando la arquitectura este estable:

- Redisenar pantalla principal como mini ERP.
- Separar navegacion por modulos.
- Convertir tableros cloud en vistas internas mas consistentes.
- Mantener flujos protegidos: preview, confirmacion escrita, audit log, snapshot, lock.

## Reglas de trabajo

- No romper compatibilidad legacy hasta que exista reemplazo probado.
- Despues de cada migracion ejecutar tests, compileall e import smoke tests.
- Limpiar `__pycache__` despues de usar `compileall`.
- Documentar cada cambio estructural en este roadmap y en `docs/ESTRUCTURA_ERP_OBJETIVO.md`.
- Todo cambio que toque WooCommerce real debe mantener preview, confirmacion y caja negra.

## Comandos utiles

```powershell
python -m unittest discover -s GestorWoo\tests -v
python -m compileall -q GestorWoo\src GestorWoo\gestorwoo.py GestorWoo\FutonEspaiLauncher.py CalculoCoste GestorWoo\tests abrir_futon_espai.py
python GestorWoo\gestorwoo.py --help
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__
```

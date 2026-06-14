# FutonHUB - Estructura ERP objetivo

Estado actual: migracion progresiva desde herramientas separadas hacia mini ERP.

Roadmap operativo de continuidad: `docs/ROADMAP_FUTONHUB.md`.
Plan de UI-ERP: `docs/UI_ERP_PLAN.md`.
Inventario funcional: `docs/FUNCTIONAL_INVENTORY.md`.

## Paquete canonico nuevo

```text
GestorWoo/src/futonhub/
  app/                 Entradas de aplicacion: CLI y HUB.
  core/                Configuracion y rutas.
  cloud/               Cliente Supabase, audit, auth, locks.
  cloud/services/      Servicios de dominio ya separados.
  ui/erp/              UI principal del ERP.
  modules/             Modulos funcionales del ERP.
```

## Compatibilidad temporal

```text
GestorWoo/src/gestorwoo/
```

Sigue existiendo para que la UI actual, scripts y exe no se rompan durante la migracion.
El objetivo es mover dominio por dominio a `futonhub/` y dejar `gestorwoo` como alias legacy.

## Modulos ya separados

```text
futonhub/cloud/services/prices.py
futonhub/cloud/services/price_proposals.py
futonhub/cloud/services/inventory.py
futonhub/cloud/services/rollback.py
futonhub/cloud/services/woocommerce_publish.py
```

Estos modulos contienen ahora la implementacion real de servicios cloud.
`gestorwoo.cloud.services` queda como capa legacy de reexportacion para no romper CLI, UI ni tests existentes.

## UI principal

```text
futonhub/ui/erp/hub.py
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

El HUB principal vive ahora en `futonhub.ui.erp.hub`.
`gestorwoo.hub` queda como wrapper legacy para imports antiguos.
Los tableros cloud, login, diagnosticos, catalogo, tarjetas y lanzadores ya estan separados como mixins de UI para mantener el HUB como ensamblador.
`prototype.py` contiene el shell Tkinter aislado para validar UI-ERP antes de reemplazar el HUB estable.

## CalculoCoste

`CalculoCoste/` aun queda como carpeta fisica legacy porque contiene scripts y `data.xlsx`.

Nuevo punto de entrada canonico:

```text
futonhub/modules/cost/launcher.py
```

Cuando la UI ERP este lista, se movera la logica de coste a:

```text
futonhub/modules/cost/
```

y `CalculoCoste/` quedara como lanzador legacy o se eliminara en una version posterior.

## Orden recomendado de migracion fisica

1. Mantener `GestorWoo/` y `CalculoCoste/` funcionando.
2. Usar `futonhub.app.cli` como entrada nueva.
3. Servicios cloud movidos desde `gestorwoo.cloud.services` a `futonhub.cloud.services`.
4. UI principal movida a `futonhub/ui/erp`; siguiente fase: separar pantallas/tableros.
5. Mover coste hacia `futonhub/modules/cost`.
6. Renombrar ejecutables/scripts cuando ya no dependan de rutas legacy.

# Changelog

## 0.6.1 · Stock Updates & Proposal Workflow

- Actualizaciones > Stock incorpora el formato operativo validado por Futon
  Espai: `A=Codigo`, `C=Total`, `G=Tienda`, con almacen calculado como
  `Total - Tienda`.
- Stock acepta valores firmados validos, mantiene errores por fila como no
  bloqueantes y aplica unicamente filas `READY`, con preview, snapshot,
  postcheck, rollback y doble proteccion contra ejecuciones repetidas.
- Stock protege campos no autorizados y evita escrituras en descatalogados,
  invalidos y duplicados de identidad; smoke humano real:
  `UPDATES-20260904-084735-F891046B`.
- Actualizaciones anade control de acceso acotado al modulo: Andy conserva
  Stock, Rotacion C y Precios de Proveedores; Futon Espai conserva Stock y no
  ve ni ejecuta Rotacion C ni Precios de Proveedores.
- Cambio de Precios mantiene exclusiones confirmadas del catalogo fuente sin
  aplicar una regla global de ocultar articulos sin Woo.
- Propuestas limita la carga inicial a las 10 propuestas logicas mas recientes,
  conserva el historial completo, calcula contadores reales de Items/Suben/Bajan
  sin placeholders y mantiene detalle lazy.
- Smokes humanos registrados para Stock, control de acceso, catalogo fuente de
  precios, historial de propuestas y contadores de propuestas.

## 0.6.0 · Proposal History & Price Impact Catalogue

- Cambio de Precios: refuerza la resolucion Woo de Tatamis Plegables con
  identidad remota exacta compartida entre catalogo, impactos y publicacion.
- Cambio de Precios: corrige el coverage del grafo para targets directos sin
  derivados, manteniendo comportamiento fail-closed ante fallos de carga.
- Cambio de Precios: excluye `208001` y `216001` del catalogo seleccionable de
  Nueva Propuesta sin perderlos como targets derivados publicables/verificables.
- Cambio de Precios: preserva impactos derivados del Tatami Plegable 90 hacia
  Crudo, Negro y Marron Chocolate.
- Propuestas: elimina limites fijos ocultos en el historial y carga todas las
  propuestas accesibles en orden mas reciente primero.
- Propuestas: una nueva propuesta guardada no sobrescribe otra pendiente del
  mismo target salvo actualizacion explicita por `proposal_id`.
- Woo/Fundas: mantiene los mappings corregidos durante mantenimiento y las
  regresiones de publicacion, sale_price, rollback, partial success y
  verificacion live.
- Smoke humano: `HUMAN_PLEGABLE_SELECTABLE_SMOKE=PASS_REAL` y
  `HUMAN_PROPOSAL_HISTORY_SMOKE=PASS_REAL`.

## 0.5.1 · Price Publication Reliability

- Cambio de Precios: consolida la publicacion fiable de precios WooCommerce con
  resolucion exacta de targets product/variation, SKUs literales y sin matching
  aproximado.
- Cambio de Precios: preserva revalidacion live, snapshot, auditoria,
  verificacion GET posterior, rollback y aislamiento por target ante fallos.
- Cambio de Precios: corrige la interpretacion de combinaciones derivadas,
  cuarentenas resueltas por Woo live, casos sin precio base y resumen honesto de
  resultados.
- Verificado smoke humano real Tatami 80x200 con combinaciones y post-smoke
  read-only contra WooCommerce live.

## 0.5.0 · PLUS ULTRA

- FutonHUB ERP alcanza una version estable para operativa diaria: Dashboard,
  Inventario, Pedidos/Recepcion, Cambio de Precios WooCommerce, relaciones Woo,
  Biblioteca de Formulas, Configuracion y Actualizaciones.
- Catalogo e Inventario: politica central de Descatalogados consolidada; los
  94 articulos descatalogados se respetan en los workflows operativos.
- Seguridad de sesion: Remember Me seguro mediante Windows DPAPI, auto-login
  con refresh session y accion visible `Cerrar sesion / Cambiar usuario`.
- Distribucion/runtime: mejora de tiempo de arranque, lazy Woo dependency y
  contratos runtime independientes de artefactos locales de auditoria.
- Actualizaciones masivas: soporte controlado para Rotacion C, Stock y Precios
  Proveedores con templates Excel, preview, revalidation, snapshot, auditoria,
  rollback y proteccion de Descatalogados.
- Actualizaciones: resolucion controlada de IDs con/sin cero inicial; los alias
  Woo ya no provocan falsas ambiguedades frente a una identidad fisica unica.
- Cambio de Precios: conserva el hardening Woo heredado de rc8 para publisher,
  targets product/variation, combinaciones derivadas, revalidacion, auditoria y
  rollback.
- Configuracion/Calculos: `IVA Recargo de Equivalencia` deja de mostrarse como
  constante editable; el calculo economico conserva la variable/factor interno.
- Inventario: retirado el aviso legacy de catalogo sin cambiar busqueda,
  filtros, detalle, packs, Woo info, stock ni exclusion de Descatalogados.
- Pascal: la ausencia de precio Pascal es un estado valido de negocio; no se
  declara reconciliacion masiva de datos Pascal en esta version.

## v0.5.0-rc.8 - 2026-08-21

- Cambio de Precios: corrige la publicacion real de cambios de precio a
  WooCommerce.
- Cambio de Precios: corrige targets Woo product/variation y endpoints de
  variaciones.
- Cambio de Precios: corrige la publicacion de combinaciones y relaciones
  derivadas.
- Cambio de Precios: anade revalidacion segura de contexto Woo y precios live.
- Cambio de Precios: mantiene snapshot, auditoria, rollback y verificacion
  posterior.
- Cambio de Precios: recupera propuestas legacy con identidad Woo incorrecta
  mediante SKU exacto.
- Cambio de Precios: corrige errores de preview, revalidacion y modal en blanco.
- Cambio de Precios: tras aplicar correctamente vuelve al listado de Propuestas
  de Precios.

## v0.5.0-rc.7 - 2026-08-19

- Pedidos: endurece calculos con constantes Supabase fail-closed.
- Pedidos: corrige reparto dinamico del coste de descarga por unidades
  participantes.
- Rendimiento: mejora arranque, Inventario y carga de runtime.
- Constantes: reduce lecturas repetidas manteniendo freshness por calculo.
- Biblioteca de Formulas: organiza por proveedor y area real de uso.
- Catalogo e Inventario: mantiene las mejoras introducidas en rc.6.

## v0.5.0-rc.6 - 2026-08-18

- Pedidos: se incorpora PED_CALC_005A; Cipta y Hemei usan la ruta import
  USD/EUR, mientras Ekomat y Pascal conservan la formula general.
- Catalogo: correcciones confirmadas de identidad/nombre, Toppers como familia
  propia, `0619008` preservando `item_id=619011`, y Macao operativo en
  `0302009`.
- Inventario: nuevo contrato runtime fail-closed de visibilidad para incluir
  solo seis packs comerciales aprobados y excluir tres Duo Latex historicos.
- Cambio de Precios: la visibilidad extra de Inventario no amplía por si sola
  la elegibilidad de precios; componentes de proveedor quedan fuera de
  propagacion automatica.
- Biblioteca de Formulas: filtro secundario por proveedor en Pedidos sin
  duplicar formulas.

## v0.5.0-rc.5 - 2026-08-13

- Responsive global acotado para portatiles: ventana principal con minsize
  menor, centrado/clamping contra viewport real y layout adaptable de filtros
  jerarquicos.
- Cambio de Precios: la seleccion de productos separa controles, paginacion y
  acciones para que `Anadir seleccionados` siga visible/accesible en
  resoluciones pequenas.
- Inventario y ventanas auxiliares: modales principales ajustan tamano y minimo
  al viewport sin cambiar reglas de negocio.
- Distribucion: nuevo smoke estructural de runtime sin `auditoria/`, sin rutas
  locales de desarrollo y con combinaciones de precio cargadas desde
  `runtime_config`.
- Sin cambios de precios, stock, WooCommerce, Supabase, catalogo comercial ni
  Macao `0402014`.

## v0.5.0-rc.4 - 2026-08-11

- Hotfix final de distribucion runtime para Cambio de Precios.
- `CombinationPriceImpactService()` carga el baseline de combinaciones desde
  `runtime_config/combination_price_impact` y ya no depende de artefactos
  locales de auditoria.
- La sincronizacion inicial Woo usa el grafo aprobado empaquetado y validado
  con checksum canonico `utf8_text_lf_v1`.
- El runtime distribuido sin carpeta de auditoria cubre Inventario y Cambio de
  Precios con baseline operacional y combinaciones en modo lectura.

## v0.5.0-rc.3 - 2026-08-11

- Hotfix runtime de distribucion para Inventario.
- `CatalogOperationalBaseline()` ya no depende de `auditoria/out/woo_map_001a_3`
  en instalaciones distribuidas; carga un contrato operativo versionado bajo
  `GestorWoo/src/futonhub/runtime_config`.
- Nuevo contrato `catalog_operational_baseline.csv` con 254 filas: 188
  operativas y 66 en cuarentena, sin precios, stock, credenciales ni rutas
  locales.
- El mensaje de Inventario separa fallos reales de lectura Supabase de fallos
  de configuracion runtime local.
- Macao `0402014` conserva cuarentena y no participa en propagacion de precios.

## v0.5.0-rc.2 - 2026-08-11

- Hotfix de distribucion para el contrato runtime del catalogo fisico.
- El checksum de `physical_catalog_snapshot.csv` pasa a ser canonico de texto
  UTF-8 con BOM opcional y saltos de linea normalizados a LF
  (`utf8_text_lf_v1`), evitando divergencias entre working tree Windows, Git,
  GitHub zipball y FutonHub-Launcher.
- La validacion SHA sigue activa y fail-closed ante manifest invalido, modo no
  soportado, CSV no UTF-8, checksum incorrecto o contenido manipulado.
- No se modifica el contenido comercial del snapshot; Macao `0402014` sigue en
  cuarentena hasta revision humana.

## v0.5.0-rc.1 - 2026-08-11

- PRE-FIRE release candidate. Not a stable release.
- Runtime: the physical catalog eligibility contract is now versioned below
  `GestorWoo/src/futonhub/runtime_config` and no longer depends on
  `auditoria/out`.
- Distribution: `FutonHub-Launcher` tracks the commit HEAD of
  `refactor/modularizacion-v1` through `DirectGitUpdater`; no ERP GitHub
  Release asset is required.
- Packaging: the executable builder includes the runtime catalog contract.
- Price safety: terminal direct-price contexts explicitly set
  `price_change_eligible = NO`.
- Mapping: `0402014` remains quarantined without a direct Woo target, alias,
  automatic Woo creation or access to Woo variation `3661`.

## v0.4.0-rc.2

- Pedidos: P.V.P. desde WooCommerce con fallback por SKU exacto.
- Pedidos: carga de precio proveedor, Rotacion C, M3 y bultos desde Inventario.
- Pedidos: correccion de estado visible/editor para lineas enriquecidas.
- Pedidos: items comerciales reales con is_pack=True ya no se excluyen si son simples y no derivados.
- Pedidos: casos 1018005 y 1002010 validados por smoke manual.
- UI/servicios: limpieza ASCII de textos visibles.
- Tests: suite completa OK.

## [0.4.0-rc.1] - 2026-07-03

### Añadido

- P.V.P. automático de Pedidos obtenido desde WooCommerce en vivo mediante lectura `GET`.
- Nueva fuente comercial `woo_price` para distinguir P.V.P. real de WooCommerce.
- Trazabilidad de origen de P.V.P.: WooCommerce, Manual P.V.P., Manual Margen, Margen global o Pendiente.
- Exportación de Pedidos con bloque inicial: Coste Final, Ponderado, P.V.P., Margen de Venta y Origen P.V.P.

### Cambiado

- El cálculo automático de Pedidos usa P.V.P. real de WooCommerce y calcula el Margen de Venta desde Ponderado.
- Las líneas sin edición manual intentan resolver su vínculo Woo desde `inventory_items` antes de consultar WooCommerce.
- Las ediciones manuales de P.V.P., Margen individual o Margen global conservan prioridad sobre WooCommerce.

### Corregido

- Resolución de `woo_id` para líneas crudas de pedido desde Inventario/Supabase.
- Checkbox `Usar margen global` en líneas con origen WooCommerce.
- Tratamiento controlado de productos o variaciones Woo no encontrados.
- Evita inventar P.V.P. cuando WooCommerce no devuelve un precio válido.

### Validación

- 94 tests específicos de Pedidos.
- 382 tests en la suite completa.
- `py_compile` correcto.
- AST correcto.
- Smoke manual pendiente.

### Nota

- Esta es una versión de prueba para validación mediante Launcher. No es el cierre estable final de FUNC-PED-004.

## [0.3.0] - 2026-07-03

### Añadido

- Cálculo bidireccional entre P.V.P. y Margen de Venta.
- Persistencia de la fuente comercial por línea: `global_margin`, `individual_margin` o `pvp`.
- Compatibilidad con márgenes individuales negativos derivados de un P.V.P. válido.
- Editor de artículos con cuerpo desplazable y footer fijo.

### Cambiado

- P.V.P. y Margen de Venta pasan a calcularse desde el Precio Ponderado.
- Renombrado visible de Rentabilidad a Margen de Venta.
- Orden de columnas: Coste Final, Ponderado, P.V.P. y Margen de Venta.
- Exportación alineada con el nuevo orden comercial.

### Corregido

- Conservación del último campo editado al recalcular, guardar y reabrir.
- Botones Aceptar y Cancelar ocultos en pantallas de baja altura.
- Popup confuso cuando Inventario no tenía cambios secundarios que aplicar.
- Recálculo y persistencia de márgenes individuales negativos.

### Validación

- 64 tests específicos de Pedidos.
- 352 tests en la suite completa.
- `py_compile` correcto.
- AST correcto.
- Smoke manual aprobado mediante `Abrir ERP.bat`.

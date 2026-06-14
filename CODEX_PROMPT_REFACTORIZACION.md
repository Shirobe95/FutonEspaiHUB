# Prompt maestro para Codex · Modularización FutonHUB

Trabaja sobre este repositorio de FutonHUB en una rama nueva llamada `refactor/modularizacion-v1`.

## Contexto obligatorio

Antes de modificar código, lee completos y en este orden:

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

El programa se abre siempre mediante `Abrir ERP.bat`. No cambies esta regla ni conviertas scripts auxiliares en el entrypoint oficial.

## Misión

Realiza una refactorización controlada para separar FutonHUB por módulos y reducir el monolito `GestorWoo/src/futonhub/ui/erp/prototype.py`, conservando exactamente el comportamiento actual.

Esta fase NO es una reescritura y NO es una fase de nuevas funcionalidades.

## Reglas no negociables

- No tocar `main`; trabajar en la rama indicada.
- No exponer ni sustituir secretos `.env`.
- No cambiar esquemas Supabase, RLS, RPC, tablas o columnas.
- No ejecutar migraciones destructivas.
- No cambiar reglas comerciales.
- No rediseñar la UI.
- No implementar sincronización automática general Inventario → Woo.
- No alterar el cálculo de precio efectivo.
- No declarar una publicación Woo exitosa sin relectura.
- No eliminar la verificación de persistencia de logs y snapshots.
- No romper el rollback real de precios.
- No eliminar código legacy hasta demostrar que no tiene consumidores.
- No mezclar refactorización estructural y mejoras funcionales en el mismo commit.

## Funciones críticas ya validadas que deben preservarse

1. Woo sync y autoclasificación.
2. Enlace por `woo_id`, SKU y alias.
3. Padres variables informativos.
4. Exclusión de productos test.
5. Packs y componentes.
6. Propuestas de precio.
7. Precio efectivo basado en `regular_price` y `sale_price`.
8. Preview y confirmación.
9. Escritura Woo.
10. Relectura y validación.
11. Snapshot previo.
12. Audit log persistido.
13. Rollback real.
14. Apertura con `Abrir ERP.bat`.

## Primera entrega requerida antes de mover código

Genera un informe en `auditoria/CODEX_DESCUBRIMIENTO_INICIAL.md` con:

- grafo de imports;
- entrypoints reales;
- dependencias de `prototype.py`;
- servicios consumidos por cada vista;
- duplicados y rutas legacy;
- funciones sin referencias aparentes, marcadas solo como candidatas;
- riesgos;
- propuesta de cortes modulares;
- plan de commits pequeños.

No muevas código hasta completar ese informe.

## Estrategia de implementación

1. Ejecuta la suite actual y registra el resultado.
2. Añade tests de caracterización para funciones críticas.
3. Extrae primero shell, navegación y componentes UI compartidos.
4. Extrae módulos uno a uno.
5. Después de cada extracción:
   - ejecuta tests;
   - verifica imports;
   - documenta archivos movidos;
   - actualiza `auditoria/AUDITORIA_FUNCIONAL_V1.md`;
   - genera checklist manual;
   - crea un commit independiente.
6. Mantén adaptadores temporales si son necesarios para evitar un corte brusco.
7. Prefiere cambios mecánicos y revisables a una reescritura elegante pero riesgosa.

## Arquitectura objetivo orientativa

Puedes proponer una alternativa mejor, pero justifícala:

```text
futonhub/
├── app/
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
├── shared/
└── tests/
```

## Criterios de aceptación

La refactorización solo se acepta si:

- `Abrir ERP.bat` sigue arrancando.
- Login funciona.
- Woo sync mantiene sus contadores y clasificación.
- Inventario busca y abre detalles.
- Packs muestran componentes.
- Se crea una propuesta de precio.
- Se publica un precio efectivo en Woo.
- Se verifica por relectura.
- Se generan log y snapshot.
- El rollback devuelve el precio previo.
- Los tests existentes y nuevos pasan.
- No se han cambiado datos ni esquemas.
- La auditoría queda actualizada.
- Se entrega un resumen de diferencias y pruebas.

## Formato de trabajo

No hagas un mega-commit. Propón primero el plan y espera revisión. Después trabaja en una serie de commits pequeños, cada uno con:

- objetivo;
- archivos tocados;
- comportamiento preservado;
- tests;
- riesgos;
- prueba manual.

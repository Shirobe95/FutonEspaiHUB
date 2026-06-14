# FutonHUB · Checkpoint v62.1 para traspaso a Codex

## Estado congelado

Este checkpoint conserva la última versión validada antes de la modularización.

### Validado extremo a extremo

- Sincronización Woo de solo lectura.
- Autoclasificación.
- Enlaces Woo ↔ Inventario.
- Packs, alias y 1.116 relaciones de componentes.
- Propuestas de precio.
- Cálculo de precio efectivo Woo.
- Publicación de precio.
- Relectura y verificación posterior.
- Audit log.
- Snapshot.
- Rollback real de precio.
- Persistencia de caja negra verificada.

### No declarado completo

- Pedidos completos E2E.
- Precios de proveedor E2E.
- Dashboard completo.
- Informes generales.
- Configuración general.
- Configuración de seguridad.
- Backups cloud generales.
- Administración de usuarios y dispositivos.
- Sincronización universal Inventario → Woo.

## Regla operativa

Abrir siempre con:

```text
Abrir ERP.bat
```

## Regla de desarrollo

La primera tarea de Codex es ordenar y caracterizar, no añadir funciones.

## Archivos de lectura obligatoria

1. `auditoria/AUDITORIA_FUNCIONAL_V1.md`
2. `auditoria/MAPA_FUNCIONAL_CODIGO.md`
3. `auditoria/PLAN_REFACTORIZACION_CODEX.md`
4. `CODEX_REVIEW_BRIEF_FUTONHUB_V13.md`
5. `ESTRUCTURA_PROYECTO.md`
6. `README.md`
7. `README_CHECKPOINT_V13.md`
8. `docs/ROADMAP_FUTONHUB.md`
9. `docs/FUNCTIONAL_INVENTORY.md`
10. `CODEX_PROMPT_REFACTORIZACION.md`

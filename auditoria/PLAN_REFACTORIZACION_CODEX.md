# FutonHUB · Plan de refactorización controlada para Codex

## Objetivo

Separar el monolito actual por módulos sin cambiar comportamiento observable ni reglas de negocio.

## Fase 0 · Seguridad del checkpoint

- Trabajar en rama nueva: `refactor/modularizacion-v1`.
- No hacer commits directos sobre `main`.
- Etiquetar el estado actual como `checkpoint-v62.1-codex-handoff`.
- Conservar el ZIP original fuera del repositorio.
- No incluir `.env`, tokens, contraseñas ni secretos.
- No ejecutar migraciones destructivas.
- No tocar datos reales salvo pruebas explícitamente autorizadas.

## Fase 1 · Caracterización antes de mover

1. Ejecutar tests existentes.
2. Crear smoke tests del entrypoint.
3. Añadir tests de caracterización para:
   - normalización SKU;
   - clasificación de padres variables;
   - exclusión de test;
   - precio efectivo;
   - payload Woo;
   - persistencia de log/snapshot;
   - rollback de precios;
   - resolución de componentes de packs.
4. Registrar resultados en `auditoria/`.

## Fase 2 · Extraer shell y navegación

Extraer de `prototype.py`:

- shell principal;
- sidebar;
- topbar;
- navegación;
- overlay de trabajo;
- componentes UI compartidos.

No modificar contenidos de las vistas.

## Fase 3 · Extraer módulos uno por uno

Orden recomendado:

1. Dashboard.
2. Inventario.
3. WooCommerce.
4. Propuestas y publicación de precios.
5. Seguridad/logs/snapshots.
6. Precios de proveedor.
7. Pedidos.
8. Informes.
9. Configuración.

Después de cada módulo:

- ejecutar tests;
- abrir con `Abrir ERP.bat`;
- completar checklist manual;
- crear commit separado;
- actualizar mapa y auditoría.

## Fase 4 · Separar infraestructura

- Cliente Supabase.
- Cliente WooCommerce.
- Adaptadores de archivos.
- Auditoría.
- Locks.
- Configuración.

Las capas UI no deben construir consultas HTTP/SQL directamente.

## Fase 5 · Limpiar legacy

Solo después de comprobar usos:

- mover lanzadores viejos;
- aislar SQLite;
- separar `CalculoCoste`;
- decidir qué rollback queda como canónico;
- archivar scripts históricos.

## Prohibiciones de la primera refactorización

- No rediseñar UI.
- No cambiar nombres de tablas o columnas.
- No reescribir desde cero.
- No eliminar compatibilidad histórica.
- No añadir sincronización automática Inventario → Woo.
- No alterar reglas de precios.
- No mezclar mejoras funcionales con movimiento estructural.
- No declarar algo “sin uso” solo porque no aparece en una búsqueda superficial.

## Entregables de Codex

1. Rama modular.
2. Informe de arquitectura encontrada.
3. Diagrama de dependencias antes/después.
4. Lista de archivos movidos.
5. Tests añadidos.
6. Resultados de tests.
7. Matriz funcional actualizada.
8. Riesgos y deuda pendiente.
9. Instrucciones exactas de prueba manual.
10. PR pequeña o serie de PRs revisables, no un mega-cambio opaco.

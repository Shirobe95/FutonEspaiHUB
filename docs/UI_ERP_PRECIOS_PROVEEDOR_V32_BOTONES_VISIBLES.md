# UI ERP v32 - Precio Proveedores botones visibles

## Problema

La sección de Precio Proveedores cargaba la tabla y el panel de edición, pero los botones de acción quedaban demasiado abajo/ocultos en el panel lateral.

## Solución

Se recolocan los botones en una barra visible dentro del panel de detalle:

- Guardar cambios
- Cancelar

La barra muestra también la nota:

```text
Guarda en Supabase con log + snapshot
```

## Flujo

```text
Seleccionar item
→ editar precio principal / Pascal
→ escribir motivo opcional
→ Guardar cambios
→ confirmación
→ update Supabase
→ snapshot
→ audit log
→ recarga manteniendo seleccionado el item
```

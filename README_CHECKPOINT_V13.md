# FutonEspai HUB · Checkpoint estable v13

Este paquete congela la versión validada después de las pruebas de Supabase, roles, caja negra, propuestas de precio, publicación WooCommerce protegida, inventario interno y rollback.

## Cómo abrir

Desde la carpeta principal:

```powershell
.\ABRIR_FUTON_ESPAI.bat
```

O desde GestorWoo:

```powershell
python gestorwoo.py hub
```

## Diagnóstico recomendado

```powershell
python gestorwoo.py diagnostic
python gestorwoo.py cloud-login-diagnostic
python gestorwoo.py cloud-operational-status
```

## Documentación para Codex

Leer primero:

```text
CODEX_REVIEW_BRIEF_FUTONHUB_V13.md
```

## Seguridad

El `.env` incluido puede contener credenciales reales. No subir este paquete completo a GitHub público. Para repositorio, usar `.env.example` y mantener `.env` fuera de Git.

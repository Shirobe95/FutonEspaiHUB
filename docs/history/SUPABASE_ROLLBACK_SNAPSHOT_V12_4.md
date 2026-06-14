# FutonEspai HUB · v12.4 Rollback desde snapshot

Objetivo: permitir al **admin** revertir datos internos de Supabase usando `operation_snapshots.before_data`.

No toca WooCommerce.

## SQL recomendado

Ejecutar en Supabase:

```txt
docs/supabase/18_rpc_rollback_snapshot_v12_4.sql
```

## Comandos

Listar candidatos:

```powershell
python gestorwoo.py cloud-rollback-candidates --limit 30
```

Preview:

```powershell
python gestorwoo.py cloud-rollback-snapshot --operation-id OPERATION_ID
```

Ejecutar rollback:

```powershell
python gestorwoo.py cloud-rollback-snapshot --operation-id OPERATION_ID --execute --confirm REVERTIR
```

El comando vuelve a pedir escribir `REVERTIR`.

## Entidades soportadas

- `inventory_item` → `inventory_items`
- `price_change_proposal` → `price_change_proposals`
- `business_constant` → `business_constants`

## Seguridad

- Solo admin.
- Preview obligatorio.
- Confirmación escrita `REVERTIR`.
- Crea un nuevo snapshot del estado justo antes del rollback.
- Crea un `audit_log` con estado `ROLLED_BACK`.
- WooCommerce no se toca.

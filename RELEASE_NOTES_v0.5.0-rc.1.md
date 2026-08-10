# FutonHUB v0.5.0-rc.1

Status: `PRE-FIRE RELEASE CANDIDATE`

This is a release candidate for Launcher-driven commit distribution. It is not
a stable release and does not require a GitHub Release asset for the ERP.

## Included

- Catalog organisation and hierarchical commercial filtering completed in the
  prior approved cuts.
- Price proposal workspace hardening, live read-only Woo synchronisation, and
  direct/combination reconciliation work from the PRE-DEMO and PRE-FIRE cuts.
- Mapping safety controls that preserve literal SKU identity and prevent
  automatic alias creation.
- Self-contained physical catalog runtime configuration with a fail-closed
  checksum and no dependency on `auditoria/out`.
- Cama Macao (`0402014`) commercial quarantine: it remains visible as an
  inventory item but has no automatic Woo price target until a real direct Woo
  entity is approved.

## Safety regression

- `0402014` remains distinct from Base para Tatamis Macao (`0302009`).
- A missing literal Woo link produces `NO_WOO_LINK` and
  `price_change_eligible = NO`.
- The item cannot target Woo variation `3661`, cannot be converted to an alias,
  and initiates no Woo creation or price write.

## Distribution model

- `FutonHub-Launcher` resolves the HEAD of `refactor/modularizacion-v1`.
- `DirectGitUpdater` downloads the commit zipball, stages it, runs health
  checks, backs up and swaps the runtime, and rolls back on failure.
- No ERP GitHub Release asset or release feed is required.

See `RELEASE_005A_1_RUNTIME_CONFIG_AUDIT.md` for the runtime contract audit.

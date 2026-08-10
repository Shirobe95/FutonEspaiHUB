# FUTONHUB - RELEASE-005A.1 PRE-FIRE v0.5.0-rc.1

Status: `LOCAL_RELEASE_IN_VALIDATION`
Date: 2026-08-11

## Distribution model corrected

- FutonHub-Launcher version `0.12.0` follows `Shirobe95/FutonEspaiHUB` branch
  `refactor/modularizacion-v1`.
- The Launcher resolves remote HEAD, downloads the commit zipball and installs
  it through `DirectGitUpdater` with staged and active health checks,
  backup/swap and automatic rollback.
- The ERP requires no GitHub Release asset and no release feed.
- No Launcher change is required for this ERP release.

## Runtime packaging

- The physical catalog eligibility contract is now a versioned runtime input:
  `futonhub/runtime_config/physical_catalog_snapshot_manifest.json` and CSV.
- It holds 254 physical eligible rows and only identity, eligibility and
  commercial taxonomy fields.
- It excludes prices, stock, credentials, Woo targets and audit traces.
- Runtime loading has no `auditoria/out` fallback and fails closed on a missing
  or tampered contract.

## Safety

- `0402014` remains visible and quarantined from direct price changes.
- It has no direct Woo target, no alias, no automatic Woo creation and cannot
  target `3661`.
- The no-auditoria runtime test verifies zero Woo, Supabase and SQL writes.

## Release next state

- Run final validation and stage the approved functional code, tests, runtime
  config, version bump and release documents.
- Commit and tag on `refactor/modularizacion-v1`.
- If network push remains unavailable after those gates, report
  `LOCAL_RELEASE_READY_FOR_PUSH` with the two exact `git push` commands.

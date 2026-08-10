# FUTONHUB - RELEASE-005A PRE-FIRE v0.5.0-rc.1

Status: `SUPERSEDED_BY_RELEASE_005A_1`
Date: 2026-08-10

## Global status

This file records the initial audit only. Its conclusion about the updater is
superseded by `OBSIDIAN_UPDATE_RELEASE_005A_1.md`.

## Completed in this cut

- Audited the real local installation and executable path.
- Confirmed that `FutonEspaiLauncher.py` is an app entrypoint, not an updater.
- Confirmed no local `FutonHub-Launcher` checkout, no tracked updater client,
  no tracked release workflow, and no asset contract.
- Added explicit `price_change_eligible = NO` to terminal direct-price contexts.
- Added a regression for Cama Macao `0402014`: visible catalog identity, no
  automatic Woo target, no `3661`, no alias/packs, and zero Woo/Supabase/SQL
  writes.
- Added release hygiene ignores for local audit output and dependency artifacts.

## Validation

- Targeted Macao plus initial-sync tests: 24 OK.
- Full suite: 804 OK.
- No WooCommerce, Supabase, SQL, price, stock, Git remote, commit, tag, push,
  or GitHub Release action was performed.

## Release blockers

1. No updater / release-feed / expected-release-asset contract.
2. Remote GitHub channel unreachable in this session; GitHub CLI unavailable.
3. Runtime physical catalog snapshot depends on untracked `auditoria/out`
   content that the release policy excludes.
4. Existing `git diff --check` failure in `prototype.py` due trailing whitespace.

## Recommended next work

- `[MODO DIARIO] RELEASE-005A.1`: establish and test the launcher/update
  contract, including release asset, checksum, rollback, and client discovery.
- `[MODO DIARIO] RELEASE-005A.2`: package the runtime catalog configuration as
  a versioned release input, without shipping raw audit artifacts.
- `[MODO DIARIO] RELEASE-005A.3`: clean release staging, resolve the existing
  whitespace error, run final validation, then repeat publication preflight.
- `[PENDIENTE REVISION USUARIO]`: approve the distribution architecture and the
  packaging location for the runtime catalog snapshot.

# RELEASE-005A Update Path Audit

Status: `SUPERSEDED_BY_RELEASE_005A_1`

## Required release identity

| Field | Value |
| --- | --- |
| `CURRENT_APP_VERSION` | `0.4.0rc2` |
| `TARGET_APP_VERSION` | `0.5.0rc1` |
| `SOURCE_BRANCH` | `refactor/modularizacion-v1` |
| `RELEASE_TAG` | `v0.5.0-rc.1` |
| `EXPECTED_ASSET` | `NO`; clients receive a GitHub zipball for the resolved commit. |
| `CLIENT_UPDATE_MECHANISM` | `FutonHub-Launcher` uses `GitHubClient.resolve_head()` and `DirectGitUpdater.install_commit()` against `refactor/modularizacion-v1`. |
| `LAUNCHER_CHANGE_REQUIRED` | `NO` |

## Evidence

- External verification supplied for RELEASE-005A.1 confirms the Launcher
  configuration points to `Shirobe95/FutonEspaiHUB`, branch
  `refactor/modularizacion-v1`, with Launcher version `0.12.0`.
- The client resolves remote HEAD, downloads its zipball, stages a runtime,
  runs health checks, backs up and swaps, then rolls back automatically on a
  failed active health check.
- The physical catalog dependency identified by the initial audit is promoted
  to a versioned runtime contract and is covered by an isolated no-auditoria
  test in RELEASE-005A.1.

## Decision

The original conclusion about the absence of an updater is superseded. The only
technical blocker it found was the unversioned runtime catalog contract; that
is addressed by RELEASE-005A.1 before commit and push.

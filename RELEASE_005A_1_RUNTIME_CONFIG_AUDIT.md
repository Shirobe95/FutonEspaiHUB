# RELEASE-005A.1 Runtime Configuration Audit

Status: `READY_FOR_RUNTIME_PROMOTION`

## Current dependency

| Item | Current value |
| --- | --- |
| Manifest | `auditoria/out/physical_catalog_snapshot_manifest.json` |
| Snapshot | `auditoria/out/inv_org_003b_3/dat_catalog_003b_ui_eligible_254.csv` |
| Snapshot size | 122851 bytes, 254 rows |
| Loader | `GestorWoo/src/futonhub/ui/erp/catalog_filters.py` |
| Consumers | Inventory physical-catalog filtering and Price Change canonical metadata resolution |
| Missing behavior | Fails closed with `CatalogFilterConfigurationError`; Inventory displays a catalog-load error and Price Change cannot build canonical metadata |

## Classification

The CSV is the frozen `INV-ORG-003B.3` physical UI eligibility contract. It is
authoritative runtime configuration, not a transient audit report. The original
also contains catalog description, source traces, timestamp and review fields
that are unnecessary for runtime filtering or exact catalog resolution.

## Runtime promotion

The distributable contract will live below:

- `GestorWoo/src/futonhub/runtime_config/physical_catalog_snapshot_manifest.json`
- `GestorWoo/src/futonhub/runtime_config/physical_catalog_snapshot.csv`

The promoted CSV retains only the 16 fields needed for identity, eligibility,
display taxonomy and exact resolution. It contains no credentials, Woo links,
prices, stock values, costs, descriptions, source file paths or audit traces.
The loader has no fallback to `auditoria/out`.

## Integrity and tests

The manifest retains row count, allowed leading-zero comparison keys and the
SHA-256 of the promoted CSV. The standard loader continues to fail closed for a
missing, malformed or tampered runtime contract.

`test_release_005a_1_runtime_without_auditoria` will copy only the runtime
package into an isolated directory with no `auditoria` directory, then verify
ERP imports, physical catalog, inventory eligibility, price metadata mapping,
cascading filters, direct-price ineligibility and the Macao quarantine.

## Macao note

The frozen authoritative row for `0402014` currently identifies **Cama Macao**
with `family` and `filter_family` equal to `Camas`, `filter_group = Macao`,
and no direct Woo relation. The RELEASE-005A.1 brief labels it as `Bases para
Tatamis`, which conflicts with the existing approved snapshot. This cut does
not alter the record; it preserves the current snapshot and quarantine.

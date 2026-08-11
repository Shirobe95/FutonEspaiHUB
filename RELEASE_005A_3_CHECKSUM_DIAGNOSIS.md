# RELEASE-005A.3 Runtime Checksum Diagnosis

## Scope

The distributed physical catalog remained unchanged. This diagnosis covers only
the integrity representation of `physical_catalog_snapshot.csv` across the
Windows working tree, Git, GitHub zipball, and FutonHub-Launcher runtime.

## Evidence From v0.5.0-rc.1

Commit inspected: `14d55a7cb0158c6cf1a4f09073a2a9b0ce6701b1`

| Source | SHA-256 | Bytes | BOM | Line endings |
| --- | --- | ---: | --- | --- |
| Working tree | `5f64fbe82ca3d4136f2943570507d503cdc860d681f920ead115a11e28ced73e` | 56,640 | UTF-8 BOM | 255 CRLF |
| Git blob (`HEAD:...csv`) | `65626a832409990dfc34cfdaa168172b896b51aa65c42604a739261dd8742031` | 56,385 | UTF-8 BOM | 255 LF |
| Published manifest | `5f64fbe82ca3d4136f2943570507d503cdc860d681f920ead115a11e28ced73e` | n/a | n/a | raw-byte checksum |
| GitHub zipball extracted CSV | `65626a832409990dfc34cfdaa168172b896b51aa65c42604a739261dd8742031` | 56,385 | UTF-8 BOM | 255 LF |

The Git blob was read through `git cat-file blob` as bytes. The zipball CSV
was extracted and hashed as bytes; no PowerShell text redirection was used.

## Root Cause

The manifest was generated from the Windows working-tree representation. Git
and the GitHub zipball retain the same UTF-8 BOM and commercial content, but
use LF rather than CRLF. The 255 line-ending substitutions are the only byte
difference. The raw-byte SHA-256 therefore made a valid Launcher download fail
closed.

No BOM difference, catalog-row change, or commercial snapshot modification was
detected. Macao `0402014` was not changed.

## Hotfix Contract

The manifest now declares:

```json
"checksum_mode": "utf8_text_lf_v1"
```

The canonical checksum is computed by decoding UTF-8 with optional BOM,
normalizing CRLF and CR to LF, and hashing the normalized UTF-8 bytes. The
canonical checksum for the unchanged 254-row snapshot is:

```text
ae35a7d6499c43ecc8c0f68814f99a641bccf5324018c9b7cfca0efe9e27d73c
```

The loader accepts only this declared mode and continues to fail closed for an
invalid manifest, unsupported mode, non-UTF-8 input, changed CSV data, or a
checksum mismatch.

## Regression Evidence

`GestorWoo.tests.test_release_005a_3_runtime_checksum` covers LF, CRLF, BOM,
real cell mutation, incorrect manifest hash, and invalid checksum mode. The
existing isolated-runtime test confirms that the packaged snapshot loads with
no `auditoria/` directory and exactly 254 rows.

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from futonhub.core.runtime_integrity import CHECKSUM_MODE_UTF8_TEXT_LF_V1, canonical_text_sha256


CUT = "WOO-MAP-001A.3"
OPERATIONAL = "OPERATIONAL_BASELINE"
QUARANTINED_BUSINESS = "QUARANTINED_BUSINESS"
QUARANTINED_TECHNICAL = "QUARANTINED_TECHNICAL"
HISTORICAL = "HISTORICAL_OR_DISCONTINUED"
TEMPORARY = "TEMPORARY_OR_EXCEPTIONAL"
OUTSIDE_BASELINE = "OUTSIDE_APPROVED_BASELINE"

_RUNTIME_SCHEMA = "futonhub.runtime.catalog_operational_baseline.v1"
_RUNTIME_BASELINE_COLUMNS = {
    "item_id",
    "operational_status",
    "quarantine_group",
    "quarantine_reason",
    "can_participate_in_price_propagation",
    "business_review_status",
    "catalog_baseline_cut",
    "catalog_baseline_map_status",
}
_VALID_OPERATIONAL_STATUSES = {
    OPERATIONAL,
    QUARANTINED_BUSINESS,
    QUARANTINED_TECHNICAL,
    HISTORICAL,
    TEMPORARY,
}
_TRUE_VALUES = {"1", "true", "yes", "si"}


class CatalogOperationalBaselineError(ValueError):
    """Raised when the approved runtime operational baseline is inconsistent."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _truthy(value: Any) -> bool:
    return value is True or _text(value).lower() in _TRUE_VALUES


def _natural_key(value: object) -> tuple[tuple[int, object], ...]:
    parts = re.split(r"(\d+)", str(value or ""))
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)


def _raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: str(value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def catalog_operational_baseline_manifest_path() -> Path:
    """Return the packaged operational baseline contract shipped with the ERP."""
    return Path(__file__).resolve().parents[1] / "runtime_config" / "catalog_operational_baseline_manifest.json"


class CatalogOperationalBaseline:
    """Read-only overlay for the 188 operational and 66 quarantined physical items."""

    def __init__(self, artifact_root: str | Path | None = None) -> None:
        self.artifact_dir: Path | None = None
        self.manifest_path: Path | None = None
        self.source_path: Path | None = None
        self.source_kind = "runtime_config" if artifact_root is None else "legacy_artifact_root"
        if artifact_root is None:
            rows = self._load_runtime_rows()
        else:
            self.artifact_dir = self._resolve_legacy_artifact_dir(artifact_root)
            rows = self._load_legacy_artifact_rows(self.artifact_dir)
        self._load_final_rows(rows)

    @classmethod
    def load_runtime(cls) -> "CatalogOperationalBaseline":
        return cls()

    @classmethod
    def load_legacy_artifacts(cls, artifact_root: str | Path) -> "CatalogOperationalBaseline":
        return cls(artifact_root)

    @staticmethod
    def _resolve_legacy_artifact_dir(artifact_root: str | Path) -> Path:
        root = Path(artifact_root).resolve()
        if root.name == "woo_map_001a_3" and root.is_dir():
            return root
        candidate = root / "woo_map_001a_3"
        if candidate.is_dir():
            return candidate
        raise CatalogOperationalBaselineError(f"Cannot locate woo_map_001a_3 below {root}.")

    def _load_runtime_rows(self) -> list[dict[str, Any]]:
        manifest_path = catalog_operational_baseline_manifest_path()
        self.manifest_path = manifest_path
        if not manifest_path.is_file():
            raise CatalogOperationalBaselineError(
                f"No se encontro el manifiesto del baseline operativo: {manifest_path}"
            )
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if payload.get("schema") != _RUNTIME_SCHEMA:
                raise ValueError("unexpected runtime operational baseline schema")
            if payload.get("source_cut") != CUT:
                raise ValueError("unexpected runtime operational baseline cut")
            if payload.get("contains_prices") is not False:
                raise ValueError("runtime operational baseline must not contain prices")
            if payload.get("contains_stock") is not False:
                raise ValueError("runtime operational baseline must not contain stock")
            if payload.get("contains_credentials") is not False:
                raise ValueError("runtime operational baseline must not contain credentials")
            if payload.get("fail_closed") is not True:
                raise ValueError("runtime operational baseline must fail closed")
            relative_snapshot = str(payload["snapshot_relative_path"])
            expected_count = int(payload["expected_count"])
            expected_sha256 = str(payload["snapshot_sha256"])
            checksum_mode = str(payload["checksum_mode"])
            declared_columns = {str(column) for column in payload.get("required_columns") or []}
            if not relative_snapshot or Path(relative_snapshot).is_absolute() or expected_count <= 0:
                raise ValueError("invalid runtime operational baseline manifest values")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
                raise ValueError("invalid runtime operational baseline checksum")
            if checksum_mode != CHECKSUM_MODE_UTF8_TEXT_LF_V1:
                raise ValueError(f"unsupported runtime operational baseline checksum mode: {checksum_mode}")
            missing_declared = sorted(_RUNTIME_BASELINE_COLUMNS - declared_columns)
            if missing_declared:
                raise ValueError("runtime operational baseline manifest omits required columns: " + ", ".join(missing_declared))
            source_path = (manifest_path.parent / relative_snapshot).resolve()
            runtime_root = manifest_path.parent.resolve()
            if runtime_root not in source_path.parents:
                raise ValueError("runtime operational baseline path leaves runtime_config")
            self.source_path = source_path
            raw_bytes = source_path.read_bytes()
            actual_sha256 = canonical_text_sha256(raw_bytes, checksum_mode)
            if actual_sha256 != expected_sha256:
                raise ValueError("runtime operational baseline checksum mismatch")
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise CatalogOperationalBaselineError(f"Manifest de baseline operativo invalido: {manifest_path}: {exc}") from exc

        try:
            rows = _read_csv(source_path)
        except OSError as exc:
            raise CatalogOperationalBaselineError(f"No se pudo leer el baseline operativo runtime: {exc}") from exc
        missing_csv = sorted(_RUNTIME_BASELINE_COLUMNS - set(rows[0].keys() if rows else []))
        if missing_csv:
            raise CatalogOperationalBaselineError(
                "El baseline operativo runtime no contiene columnas requeridas: " + ", ".join(missing_csv)
            )
        if len(rows) != expected_count:
            raise CatalogOperationalBaselineError(
                f"El baseline operativo runtime debe contener {expected_count} filas; contiene {len(rows)}."
            )
        return rows

    def _load_legacy_artifact_rows(self, artifact_dir: Path) -> list[dict[str, Any]]:
        self._validate_legacy_manifest(artifact_dir)
        graph = json.loads((artifact_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.json").read_text(encoding="utf-8"))
        if graph.get("cut") != CUT or not isinstance(graph.get("physical_nodes"), list):
            raise CatalogOperationalBaselineError("The clean physical graph is not approved WOO-MAP-001A.3.")
        rows = [
            self._row_from_operational_artifact(dict(row))
            for row in graph["physical_nodes"]
        ]
        rows.extend(
            self._row_from_quarantine_artifact(row)
            for row in _read_csv(artifact_dir / "WOO_MAP_001A_3_QUARANTINE_SCOPE.csv")
            if _text(row.get("entity_type")) == "PHYSICAL_WITHOUT_STANDALONE_WOO"
        )
        return sorted(rows, key=lambda row: _natural_key(row.get("item_id")))

    @staticmethod
    def _validate_legacy_manifest(artifact_dir: Path) -> None:
        path = artifact_dir / "WOO_MAP_001A_3_ARTIFACT_MANIFEST.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("cut") != CUT:
            raise CatalogOperationalBaselineError("Unexpected baseline manifest cut.")
        declared = {
            _text(entry.get("name")): _text(entry.get("sha256")).lower()
            for entry in manifest.get("artifacts") or []
            if isinstance(entry, dict)
        }
        for name in ("WOO_MAP_001A_3_CLEAN_GRAPH.json", "WOO_MAP_001A_3_QUARANTINE_SCOPE.csv"):
            expected = declared.get(name)
            target = artifact_dir / name
            if not expected or not target.is_file() or _raw_sha256(target) != expected:
                raise CatalogOperationalBaselineError(f"Baseline artifact hash mismatch: {name}.")

    @staticmethod
    def _quarantine_status(row: Mapping[str, Any]) -> str:
        reason = " ".join(
            _text(row.get(key)).upper()
            for key in ("decision_group_id", "quarantine_reason", "notes")
        )
        if "TECH" in reason:
            return QUARANTINED_TECHNICAL
        if "TEMP" in reason or "EXCEPTION" in reason:
            return TEMPORARY
        if "HISTOR" in reason or "DISCONT" in reason:
            return HISTORICAL
        return QUARANTINED_BUSINESS

    @staticmethod
    def _row_from_operational_artifact(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "item_id": _text(row.get("item_id")),
            "operational_status": OPERATIONAL,
            "quarantine_group": "",
            "quarantine_reason": "",
            "can_participate_in_price_propagation": _text(row.get("can_participate_in_combination_delta")) == "YES",
            "business_review_status": "NOT_REQUIRED",
            "catalog_baseline_cut": CUT,
            "catalog_baseline_map_status": _text(row.get("map_status")),
        }

    def _row_from_quarantine_artifact(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "item_id": _text(row.get("entity_id")),
            "operational_status": self._quarantine_status(row),
            "quarantine_group": _text(row.get("decision_group_id")),
            "quarantine_reason": _text(row.get("quarantine_reason")),
            "can_participate_in_price_propagation": False,
            "business_review_status": _text(row.get("worker_review_status")) or "PENDING",
            "catalog_baseline_cut": CUT,
            "catalog_baseline_map_status": _text(row.get("original_status")),
        }

    def _load_final_rows(self, rows: Iterable[Mapping[str, Any]]) -> None:
        indexed = self._index_unique(rows, "item_id", "runtime baseline")
        for item_id, row in indexed.items():
            status = _text(row.get("operational_status"))
            if status not in _VALID_OPERATIONAL_STATUSES:
                raise CatalogOperationalBaselineError(f"Invalid operational status for {item_id}: {status!r}.")
            if _text(row.get("catalog_baseline_cut")) != CUT:
                raise CatalogOperationalBaselineError(f"Invalid baseline cut for {item_id}.")

        self.rows_by_item_id = indexed
        self.operational_by_item_id = {
            item_id: row
            for item_id, row in indexed.items()
            if _text(row.get("operational_status")) == OPERATIONAL
        }
        self.quarantine_by_item_id = {
            item_id: row
            for item_id, row in indexed.items()
            if _text(row.get("operational_status")) != OPERATIONAL
        }
        if len(self.operational_by_item_id) != 188 or len(self.quarantine_by_item_id) != 66:
            raise CatalogOperationalBaselineError(
                "Unexpected physical baseline counts: "
                f"operational={len(self.operational_by_item_id)}, quarantine={len(self.quarantine_by_item_id)}."
            )
        if len(indexed) != 254:
            raise CatalogOperationalBaselineError(f"Unexpected total physical baseline count: {len(indexed)}.")

    @staticmethod
    def _index_unique(rows: Iterable[Mapping[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw in rows:
            identity = _text(raw.get(key))
            if not identity or identity in result:
                raise CatalogOperationalBaselineError(f"Invalid {label} physical identity: {identity!r}.")
            row = dict(raw)
            row["item_id"] = identity
            row["operational_status"] = _text(row.get("operational_status"))
            row["quarantine_group"] = _text(row.get("quarantine_group"))
            row["quarantine_reason"] = _text(row.get("quarantine_reason"))
            row["can_participate_in_price_propagation"] = _truthy(row.get("can_participate_in_price_propagation"))
            row["business_review_status"] = _text(row.get("business_review_status")) or "PENDING"
            row["catalog_baseline_cut"] = _text(row.get("catalog_baseline_cut"))
            row["catalog_baseline_map_status"] = _text(row.get("catalog_baseline_map_status"))
            result[identity] = row
        return result

    def metadata_for_item_id(self, item_id: Any) -> dict[str, Any]:
        identity = _text(item_id)
        row = self.rows_by_item_id.get(identity)
        if row is not None:
            return {
                "operational_status": _text(row.get("operational_status")),
                "quarantine_group": _text(row.get("quarantine_group")),
                "quarantine_reason": _text(row.get("quarantine_reason")),
                "can_participate_in_price_propagation": bool(row.get("can_participate_in_price_propagation")),
                "business_review_status": _text(row.get("business_review_status")) or "PENDING",
                "catalog_baseline_cut": CUT,
                "catalog_baseline_map_status": _text(row.get("catalog_baseline_map_status")),
            }
        return {
            "operational_status": OUTSIDE_BASELINE,
            "quarantine_group": "OUTSIDE_BASELINE",
            "quarantine_reason": "Physical item is not present in the approved WOO-MAP-001A.3 baseline.",
            "can_participate_in_price_propagation": False,
            "business_review_status": "REVIEW_REQUIRED",
            "catalog_baseline_cut": CUT,
            "catalog_baseline_map_status": "UNKNOWN",
        }

    def enrich_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [
            {**dict(row), **self.metadata_for_item_id(row.get("item_id"))}
            for row in rows
        ]

    def describe(self) -> dict[str, Any]:
        return {
            "cut": CUT,
            "source_kind": self.source_kind,
            "source_path": str(self.source_path or self.artifact_dir or ""),
            "operational_physical_items": len(self.operational_by_item_id),
            "quarantined_physical_items": len(self.quarantine_by_item_id),
            "total_physical_items": len(self.operational_by_item_id) + len(self.quarantine_by_item_id),
            "persistence_clients": 0,
            "network_clients": 0,
        }

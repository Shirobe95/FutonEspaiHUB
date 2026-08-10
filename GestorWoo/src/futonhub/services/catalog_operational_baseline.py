from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


CUT = "WOO-MAP-001A.3"
OPERATIONAL = "OPERATIONAL_BASELINE"
QUARANTINED_BUSINESS = "QUARANTINED_BUSINESS"
QUARANTINED_TECHNICAL = "QUARANTINED_TECHNICAL"
HISTORICAL = "HISTORICAL_OR_DISCONTINUED"
TEMPORARY = "TEMPORARY_OR_EXCEPTIONAL"
OUTSIDE_BASELINE = "OUTSIDE_APPROVED_BASELINE"


class CatalogOperationalBaselineError(ValueError):
    """Raised when the approved local operational baseline is inconsistent."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


class CatalogOperationalBaseline:
    """Read-only overlay for the 188 operational and 66 quarantined physical items."""

    def __init__(self, artifact_root: str | Path | None = None) -> None:
        if artifact_root is None:
            artifact_root = Path(__file__).resolve().parents[4] / "auditoria" / "out"
        root = Path(artifact_root).resolve()
        if not (root / "woo_map_001a_3").is_dir():
            root = root / "auditoria" / "out"
        self.artifact_dir = root / "woo_map_001a_3"
        self._validate_manifest()

        graph = json.loads(
            (self.artifact_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.json").read_text(encoding="utf-8")
        )
        if graph.get("cut") != CUT or not isinstance(graph.get("physical_nodes"), list):
            raise CatalogOperationalBaselineError("The clean physical graph is not approved WOO-MAP-001A.3.")
        operational_rows = [dict(row) for row in graph["physical_nodes"]]
        quarantine_rows = [
            row
            for row in _read_csv(self.artifact_dir / "WOO_MAP_001A_3_QUARANTINE_SCOPE.csv")
            if _text(row.get("entity_type")) == "PHYSICAL_WITHOUT_STANDALONE_WOO"
        ]
        self.operational_by_item_id = self._index_unique(operational_rows, "item_id", "operational")
        self.quarantine_by_item_id = self._index_unique(quarantine_rows, "entity_id", "quarantine")
        overlap = set(self.operational_by_item_id).intersection(self.quarantine_by_item_id)
        if overlap:
            raise CatalogOperationalBaselineError(
                "Operational and quarantined physical identities overlap: " + ", ".join(sorted(overlap)[:5])
            )
        if len(self.operational_by_item_id) != 188 or len(self.quarantine_by_item_id) != 66:
            raise CatalogOperationalBaselineError(
                "Unexpected physical baseline counts: "
                f"operational={len(self.operational_by_item_id)}, quarantine={len(self.quarantine_by_item_id)}."
            )

    def _validate_manifest(self) -> None:
        path = self.artifact_dir / "WOO_MAP_001A_3_ARTIFACT_MANIFEST.json"
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
            target = self.artifact_dir / name
            if not expected or not target.is_file() or _sha256(target) != expected:
                raise CatalogOperationalBaselineError(f"Baseline artifact hash mismatch: {name}.")

    @staticmethod
    def _index_unique(rows: Iterable[Mapping[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for raw in rows:
            identity = _text(raw.get(key))
            if not identity or identity in result:
                raise CatalogOperationalBaselineError(f"Invalid {label} physical identity: {identity!r}.")
            result[identity] = dict(raw)
        return result

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

    def metadata_for_item_id(self, item_id: Any) -> dict[str, Any]:
        identity = _text(item_id)
        operational = self.operational_by_item_id.get(identity)
        if operational is not None:
            participates = _text(operational.get("can_participate_in_combination_delta")) == "YES"
            return {
                "operational_status": OPERATIONAL,
                "quarantine_group": "",
                "quarantine_reason": "",
                "can_participate_in_price_propagation": participates,
                "business_review_status": "NOT_REQUIRED",
                "catalog_baseline_cut": CUT,
                "catalog_baseline_map_status": _text(operational.get("map_status")),
            }
        quarantined = self.quarantine_by_item_id.get(identity)
        if quarantined is not None:
            return {
                "operational_status": self._quarantine_status(quarantined),
                "quarantine_group": _text(quarantined.get("decision_group_id")),
                "quarantine_reason": _text(quarantined.get("quarantine_reason")),
                "can_participate_in_price_propagation": False,
                "business_review_status": _text(quarantined.get("worker_review_status")) or "PENDING",
                "catalog_baseline_cut": CUT,
                "catalog_baseline_map_status": _text(quarantined.get("original_status")),
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
            "operational_physical_items": len(self.operational_by_item_id),
            "quarantined_physical_items": len(self.quarantine_by_item_id),
            "total_physical_items": len(self.operational_by_item_id) + len(self.quarantine_by_item_id),
            "persistence_clients": 0,
            "network_clients": 0,
        }

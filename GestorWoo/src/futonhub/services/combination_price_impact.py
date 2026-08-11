from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping

from futonhub.core.runtime_integrity import CHECKSUM_MODE_UTF8_TEXT_LF_V1, canonical_text_sha256


CUT_001A3 = "WOO-MAP-001A.3"
CUT_001A4 = "WOO-MAP-001A.4"
STATE_001A3 = "PROVISIONAL_OPERATIONAL_BASELINE_WITH_QUARANTINE"
STATE_001A4 = "PRICE_COMBINATION_INPUT_PREPARED_READ_ONLY"
RUNTIME_SCHEMA = "futonhub.runtime.combination_price_impact.v1"

SPECIAL_LITERAL_SUFFIX_SKUS = frozenset({
    "0726007A",
    "0606001A",
    "1242002A",
    "0609007B",
})

_CENT = Decimal("0.01")
_EMPTY_PRICE_MARKERS = frozenset({"", "none", "null", "nan", "-"})
_RUNTIME_REQUIRED_FILES = frozenset({
    "WOO_MAP_001A_3_CLEAN_GRAPH.csv",
    "WOO_MAP_001A_3_CLEAN_GRAPH.json",
    "WOO_MAP_001A_3_CLEAN_COMBINATIONS.csv",
    "WOO_MAP_001A_3_QUARANTINE_SCOPE.csv",
    "WOO_MAP_001A_3_QUARANTINED_EDGES.csv",
    "WOO_MAP_001A_3_QUARANTINED_COMBINATIONS.csv",
    "WOO_MAP_001A_4_PRICE_COMBINATION_INPUT.csv",
    "WOO_MAP_001A_4_WOO_IMPACT_MATRIX.csv",
    "WOO_MAP_001A_4_EXCLUSIONS.csv",
})
_HEX_DIGITS = frozenset("0123456789abcdef")


class CombinationPriceImpactError(ValueError):
    """Raised when local graph artifacts are incomplete or inconsistent."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decimal(value: Any, *, field: str) -> Decimal:
    raw = _text(value).replace("EUR", "").replace("€", "").replace(",", ".")
    if raw.casefold() in _EMPTY_PRICE_MARKERS:
        raise CombinationPriceImpactError(f"{field} is empty or non-numeric.")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise CombinationPriceImpactError(f"{field} is not numeric: {value!r}.") from exc


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal | None) -> str:
    return "" if value is None else f"{_money(value):.2f}"


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX_DIGITS for char in value.casefold())


def _canonical_sha256(path: Path, checksum_mode: str) -> str:
    return canonical_text_sha256(path.read_bytes(), checksum_mode)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise CombinationPriceImpactError(f"Expected JSON object in {path.name}.")
    return data


def combination_price_impact_runtime_dir() -> Path:
    """Return the packaged runtime graph shipped with the ERP."""
    return Path(__file__).resolve().parents[1] / "runtime_config" / "combination_price_impact"


def approved_woo_edges_runtime_path() -> Path:
    """Return the packaged clean graph path used by initial Woo reconciliation."""
    root = combination_price_impact_runtime_dir().resolve()
    CombinationPriceImpactService._load_and_validate_runtime_manifest(root)
    return root / "WOO_MAP_001A_3_CLEAN_GRAPH.json"


def effective_edge_status(row: Mapping[str, Any]) -> str:
    """Return the approved status, never a superseded historical value."""
    return _text(row.get("new_edge_status")) or _text(row.get("edge_status"))


def effective_resolution_status(row: Mapping[str, Any]) -> str:
    """Return the approved resolution, never a superseded historical value."""
    return _text(row.get("new_resolution_status")) or _text(row.get("resolution_status"))


def _split_group_ids(value: Any) -> set[str]:
    return {part.strip() for part in _text(value).split("|") if part.strip()}


def _iter_identity_values(value: Any) -> Iterable[str]:
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            text = _text(item)
            if text:
                yield text
        return
    text = _text(value)
    if text:
        yield text


def _identity_sort(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


class CombinationPriceImpactService:
    """Read-only adapter over the approved 001A.3/001A.4 local graph."""

    def __init__(self, artifact_root: str | Path | None = None) -> None:
        self.runtime_manifest: dict[str, Any] | None = None
        self.source_kind = "runtime_config" if artifact_root is None else "legacy_artifact_root"
        if artifact_root is None:
            self.artifact_root = combination_price_impact_runtime_dir().resolve()
            self.cut3_dir = self.artifact_root
            self.cut4_dir = self.artifact_root
            self.runtime_manifest = self._load_and_validate_runtime_manifest(self.artifact_root)
            self.manifest_001a3, self.manifest_001a4 = self._split_runtime_manifests(self.runtime_manifest)
        else:
            self.artifact_root = self._resolve_legacy_artifact_root(artifact_root)
            self.cut3_dir = self.artifact_root / "woo_map_001a_3"
            self.cut4_dir = self.artifact_root / "woo_map_001a_4"
            self.manifest_001a3 = self._load_and_validate_legacy_manifest(
                self.cut3_dir / "WOO_MAP_001A_3_ARTIFACT_MANIFEST.json",
                expected_cut=CUT_001A3,
                expected_state=STATE_001A3,
            )
            self.manifest_001a4 = self._load_and_validate_legacy_manifest(
                self.cut4_dir / "WOO_MAP_001A_4_ARTIFACT_MANIFEST.json",
                expected_cut=CUT_001A4,
                expected_state=STATE_001A4,
            )
            if self.manifest_001a3.get("source_handoff_sha256") != self.manifest_001a4.get("source_handoff_sha256"):
                raise CombinationPriceImpactError("001A.3 and 001A.4 do not declare the same source handoff hash.")

        self.clean_graph_rows = _read_csv(self.cut3_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.csv")
        self.clean_graph_json = _read_json(self.cut3_dir / "WOO_MAP_001A_3_CLEAN_GRAPH.json")
        self.clean_combinations = _read_csv(self.cut3_dir / "WOO_MAP_001A_3_CLEAN_COMBINATIONS.csv")
        self.quarantine_scope = _read_csv(self.cut3_dir / "WOO_MAP_001A_3_QUARANTINE_SCOPE.csv")
        self.quarantined_edges = _read_csv(self.cut3_dir / "WOO_MAP_001A_3_QUARANTINED_EDGES.csv")
        self.quarantined_combinations = _read_csv(
            self.cut3_dir / "WOO_MAP_001A_3_QUARANTINED_COMBINATIONS.csv"
        )
        self.price_combinations = _read_csv(self.cut4_dir / "WOO_MAP_001A_4_PRICE_COMBINATION_INPUT.csv")
        self.impact_matrix = _read_csv(self.cut4_dir / "WOO_MAP_001A_4_WOO_IMPACT_MATRIX.csv")
        self.exclusions = _read_csv(self.cut4_dir / "WOO_MAP_001A_4_EXCLUSIONS.csv")

        self._validate_structures()
        self._validate_runtime_expected_counts()
        self._build_indexes()

    @staticmethod
    def _resolve_legacy_artifact_root(artifact_root: str | Path) -> Path:
        root = Path(artifact_root).resolve()
        if root.name == "woo_map_001a_3" and (root.parent / "woo_map_001a_4").is_dir():
            return root.parent
        if (root / "woo_map_001a_3").is_dir() and (root / "woo_map_001a_4").is_dir():
            return root
        raise CombinationPriceImpactError(f"Cannot locate explicit WOO-MAP artifact root below {root}.")

    @staticmethod
    def _load_and_validate_runtime_manifest(root: Path) -> dict[str, Any]:
        manifest_path = root / "combination_price_impact_manifest.json"
        try:
            manifest = _read_json(manifest_path)
            if manifest.get("schema") != RUNTIME_SCHEMA:
                raise ValueError("unexpected combination price impact runtime schema")
            if manifest.get("source_cuts") != [CUT_001A3, CUT_001A4]:
                raise ValueError("unexpected combination price impact runtime cuts")
            if manifest.get("fail_closed") is not True:
                raise ValueError("combination price impact runtime must fail closed")
            if manifest.get("contains_credentials") is not False:
                raise ValueError("combination price impact runtime must not contain credentials")
            if manifest.get("contains_stock") is not False:
                raise ValueError("combination price impact runtime must not contain stock")
            if manifest.get("contains_write_payloads") is not False:
                raise ValueError("combination price impact runtime must not contain write payloads")
            checksum_mode = _text(manifest.get("checksum_mode"))
            if checksum_mode != CHECKSUM_MODE_UTF8_TEXT_LF_V1:
                raise ValueError(f"unsupported runtime checksum mode: {checksum_mode}")
            required = set(str(name) for name in manifest.get("required_files") or [])
            if required != set(_RUNTIME_REQUIRED_FILES):
                raise ValueError("runtime manifest required files do not match the service contract")
            file_entries = manifest.get("files")
            if not isinstance(file_entries, list):
                raise ValueError("runtime manifest files must be a list")
            seen: set[str] = set()
            for entry in file_entries:
                if not isinstance(entry, dict):
                    raise ValueError("runtime manifest contains an invalid file entry")
                name = _text(entry.get("name"))
                relative_path = Path(_text(entry.get("relative_path") or name))
                expected_hash = _text(entry.get("sha256")).casefold()
                if not name or name in seen or name not in _RUNTIME_REQUIRED_FILES or not _is_sha256(expected_hash):
                    raise ValueError(f"invalid runtime manifest file entry: {name!r}")
                if relative_path.is_absolute() or ".." in relative_path.parts or relative_path.name != name:
                    raise ValueError(f"invalid runtime relative path for {name}")
                artifact_path = (root / relative_path).resolve()
                if root.resolve() not in artifact_path.parents:
                    raise ValueError(f"runtime artifact leaves runtime_config: {name}")
                if not artifact_path.is_file():
                    raise ValueError(f"missing runtime artifact: {name}")
                actual_hash = _canonical_sha256(artifact_path, checksum_mode)
                if actual_hash != expected_hash:
                    raise ValueError(f"runtime checksum mismatch for {name}")
                seen.add(name)
            missing = sorted(_RUNTIME_REQUIRED_FILES - seen)
            if missing:
                raise ValueError("runtime manifest omits files: " + ", ".join(missing))
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise CombinationPriceImpactError(
                f"Invalid combination price impact runtime manifest: {manifest_path}: {exc}"
            ) from exc
        return manifest

    @staticmethod
    def _split_runtime_manifests(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        handoff = _text(manifest.get("source_handoff_sha256"))
        files = [dict(entry) for entry in manifest.get("files") or []]
        cut3 = [entry for entry in files if _text(entry.get("name")).startswith("WOO_MAP_001A_3_")]
        cut4 = [entry for entry in files if _text(entry.get("name")).startswith("WOO_MAP_001A_4_")]
        return (
            {
                "cut": CUT_001A3,
                "state": STATE_001A3,
                "source_handoff_sha256": handoff,
                "artifacts": cut3,
            },
            {
                "cut": CUT_001A4,
                "state": STATE_001A4,
                "source_handoff_sha256": handoff,
                "artifacts": cut4,
            },
        )

    def _load_and_validate_legacy_manifest(
        self,
        path: Path,
        *,
        expected_cut: str,
        expected_state: str,
    ) -> dict[str, Any]:
        manifest = _read_json(path)
        if manifest.get("cut") != expected_cut:
            raise CombinationPriceImpactError(
                f"Unexpected artifact version in {path.name}: {manifest.get('cut')!r}."
            )
        if manifest.get("state") != expected_state:
            raise CombinationPriceImpactError(
                f"Unexpected artifact state in {path.name}: {manifest.get('state')!r}."
            )
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise CombinationPriceImpactError(f"Manifest {path.name} has no artifact inventory.")
        seen: set[str] = set()
        for entry in artifacts:
            if not isinstance(entry, dict):
                raise CombinationPriceImpactError(f"Invalid artifact entry in {path.name}.")
            name = _text(entry.get("name"))
            expected_hash = _text(entry.get("sha256")).casefold()
            if not name or name in seen or len(expected_hash) != 64:
                raise CombinationPriceImpactError(f"Invalid or duplicated manifest entry {name!r}.")
            seen.add(name)
            artifact_path = path.parent / name
            if not artifact_path.is_file():
                raise CombinationPriceImpactError(f"Missing declared artifact {artifact_path}.")
            actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                raise CombinationPriceImpactError(
                    f"SHA-256 mismatch for {artifact_path.name}: expected {expected_hash}, got {actual_hash}."
                )
            declared_bytes = entry.get("bytes")
            if declared_bytes is not None and int(declared_bytes) != artifact_path.stat().st_size:
                raise CombinationPriceImpactError(f"Byte-size mismatch for {artifact_path.name}.")
        return manifest

    @staticmethod
    def _require_columns(rows: list[dict[str, str]], required: set[str], label: str) -> None:
        if not rows:
            raise CombinationPriceImpactError(f"{label} is empty.")
        missing = required.difference(rows[0])
        if missing:
            raise CombinationPriceImpactError(f"{label} is missing columns: {sorted(missing)}.")

    def _validate_runtime_expected_counts(self) -> None:
        if not self.runtime_manifest:
            return
        expected = self.runtime_manifest.get("expected_counts") or {}
        actual = {
            "clean_graph_edges": len(self.clean_graph_rows),
            "operational_combinations": len(self.price_combinations),
            "impact_matrix_rows": len(self.impact_matrix),
            "excluded_combinations": len(self.exclusions),
            "clean_physical_nodes": len(self.clean_graph_json.get("physical_nodes") or []),
        }
        for key, value in actual.items():
            if key in expected and int(expected[key]) != value:
                raise CombinationPriceImpactError(
                    f"Runtime combination baseline count mismatch for {key}: expected {expected[key]}, got {value}."
                )

    def _validate_structures(self) -> None:
        if self.clean_graph_json.get("cut") != CUT_001A3 or self.clean_graph_json.get("state") != STATE_001A3:
            raise CombinationPriceImpactError("Clean graph JSON version/state is not approved 001A.3.")
        json_edges = self.clean_graph_json.get("composition_edges")
        if not isinstance(json_edges, list) or len(json_edges) != len(self.clean_graph_rows):
            raise CombinationPriceImpactError("Clean graph CSV/JSON edge counts differ.")

        self._require_columns(
            self.clean_graph_rows,
            {
                "edge_status",
                "new_edge_status",
                "resolution_status",
                "new_resolution_status",
                "edge_role",
                "component_sku",
                "component_item_id",
                "component_woo_id",
                "combination_woo_id",
            },
            "WOO_MAP_001A_3_CLEAN_GRAPH.csv",
        )
        self._require_columns(
            self.price_combinations,
            {
                "combination_woo_id",
                "combination_parent_woo_id",
                "combination_sku",
                "combination_name",
                "regular_price",
                "sale_price",
                "effective_price",
                "operational_status",
                "publication_allowed",
            },
            "WOO_MAP_001A_4_PRICE_COMBINATION_INPUT.csv",
        )
        self._require_columns(
            self.impact_matrix,
            {
                "combination_woo_id",
                "component_sku",
                "component_quantity",
                "component_item_id",
                "component_woo_id",
                "component_target_key",
                "relationship_type",
                "edge_rule",
                "edge_confidence",
            },
            "WOO_MAP_001A_4_WOO_IMPACT_MATRIX.csv",
        )
        self._require_columns(
            self.exclusions,
            {
                "combination_woo_id",
                "combination_sku",
                "quarantine_group_ids",
                "quarantine_reason",
                "exclusion_status",
                "publication_allowed",
            },
            "WOO_MAP_001A_4_EXCLUSIONS.csv",
        )

        clean_ids = {_text(row.get("combination_woo_id")) for row in self.price_combinations}
        excluded_ids = {_text(row.get("combination_woo_id")) for row in self.exclusions}
        matrix_ids = {_text(row.get("combination_woo_id")) for row in self.impact_matrix}
        if "" in clean_ids or "" in excluded_ids or "" in matrix_ids:
            raise CombinationPriceImpactError("Empty combination identity found in operational artifacts.")
        if clean_ids.intersection(excluded_ids):
            raise CombinationPriceImpactError("A quarantined combination leaked into the operational price input.")
        if matrix_ids != clean_ids:
            raise CombinationPriceImpactError("Impact matrix and operational combination identities differ.")
        if any(_text(row.get("operational_status")) != "INCLUDED_EXACT" for row in self.price_combinations):
            raise CombinationPriceImpactError("Operational input contains a non-exact combination.")

        for row in self.clean_graph_rows:
            if _text(row.get("edge_role")) != "PRIMARY_WOO":
                continue
            if effective_edge_status(row) != "EXACT":
                raise CombinationPriceImpactError(
                    "An operational primary edge remains blocked after applying the effective status."
                )

        suffix_rows = {
            _text(row.get("component_sku")): row
            for row in self.clean_graph_rows
            if _text(row.get("component_sku")) in SPECIAL_LITERAL_SUFFIX_SKUS
            and _text(row.get("edge_role")) == "PRIMARY_WOO"
        }
        if set(suffix_rows) != set(SPECIAL_LITERAL_SUFFIX_SKUS):
            raise CombinationPriceImpactError("Approved literal suffix identities are incomplete in the clean graph.")
        for sku, row in suffix_rows.items():
            if effective_edge_status(row) != "EXACT" or effective_resolution_status(row) != "COMPOSITION_EXACT_WOO_FULL_SKU":
                raise CombinationPriceImpactError(f"Literal suffix identity {sku} is not effectively exact.")
            if _text(row.get("component_sku")) != sku:
                raise CombinationPriceImpactError(f"Literal suffix identity {sku} was normalized unexpectedly.")

    def _build_indexes(self) -> None:
        self.combination_by_id = {
            _text(row.get("combination_woo_id")): dict(row) for row in self.price_combinations
        }
        self.exclusion_by_id = {
            _text(row.get("combination_woo_id")): dict(row) for row in self.exclusions
        }
        self.matrix_by_combination: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.matrix_by_target_key: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.matrix_by_sku: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.matrix_by_component_woo_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.inverse_by_canonical_identity: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        self.canonical_identities_by_item_id: dict[str, set[tuple[str, str]]] = defaultdict(set)
        self.canonical_identities_by_sku: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for raw in self.impact_matrix:
            row = dict(raw)
            combination_id = _text(row.get("combination_woo_id"))
            self.matrix_by_combination[combination_id].append(row)
            for index, value in (
                (self.matrix_by_target_key, row.get("component_target_key")),
                (self.matrix_by_target_key, row.get("component_item_id")),
                (self.matrix_by_sku, row.get("component_sku")),
                (self.matrix_by_component_woo_id, row.get("component_woo_id")),
            ):
                identity = _text(value)
                if identity:
                    index[identity].append(row)
            component_item_id = _text(row.get("component_item_id"))
            component_sku = _text(row.get("component_sku"))
            # Four approved literal-suffix components have Woo evidence but no
            # Supabase physical id. Their Woo component id is preserved as a
            # documented exact surrogate; no suffix or SKU normalization occurs.
            if not component_item_id and component_sku in SPECIAL_LITERAL_SUFFIX_SKUS:
                component_item_id = f"woo_component:{_text(row.get('component_woo_id'))}"
            canonical_identity = (component_item_id, component_sku)
            if not all(canonical_identity):
                raise CombinationPriceImpactError("Impact matrix has a component without exact item_id and SKU.")
            self.inverse_by_canonical_identity[canonical_identity].append(row)
            self.canonical_identities_by_item_id[canonical_identity[0]].add(canonical_identity)
            self.canonical_identities_by_sku[canonical_identity[1]].add(canonical_identity)

        # The approved clean baseline contains physical rows which are valid
        # direct-price identities even when they participate in no combination.
        # Keeping them in the inverse index lets the caller distinguish that
        # intended zero from an identity resolution failure.
        for raw in self.clean_graph_json.get("physical_nodes") or []:
            node = dict(raw)
            canonical_identity = (
                _text(node.get("canonical_item_id") or node.get("item_id")),
                _text(node.get("sku") or node.get("visible_code")),
            )
            if not all(canonical_identity):
                raise CombinationPriceImpactError("Approved physical baseline has an incomplete canonical identity.")
            self.inverse_by_canonical_identity.setdefault(canonical_identity, [])
            self.canonical_identities_by_item_id[canonical_identity[0]].add(canonical_identity)
            self.canonical_identities_by_sku[canonical_identity[1]].add(canonical_identity)

        for identity, rows in self.inverse_by_canonical_identity.items():
            destination_ids = [_text(row.get("combination_woo_id")) for row in rows]
            if len(destination_ids) != len(set(destination_ids)):
                raise CombinationPriceImpactError(
                    f"Exact canonical identity {identity!r} has duplicate Woo destinations in the impact matrix."
                )

        primary_edges: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in self.clean_graph_rows:
            if _text(row.get("edge_role")) != "PRIMARY_WOO":
                continue
            primary_edges[
                (_text(row.get("combination_woo_id")), _text(row.get("component_sku")))
            ].append(row)
        self.primary_edges = primary_edges

        self.quarantine_by_target_key: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.quarantine_by_sku: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.quarantine_by_component_woo_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        for raw in self.quarantined_edges:
            combination_id = _text(raw.get("combination_woo_id"))
            if combination_id not in self.exclusion_by_id:
                continue
            row = dict(raw)
            for index, value in (
                (self.quarantine_by_target_key, row.get("component_item_id")),
                (self.quarantine_by_target_key, row.get("physical_item_id")),
                (self.quarantine_by_sku, row.get("component_sku")),
                (self.quarantine_by_component_woo_id, row.get("component_woo_id")),
            ):
                identity = _text(value)
                if identity:
                    index[identity].append(row)

    @property
    def source_handoff_sha256(self) -> str:
        return _text(self.manifest_001a3.get("source_handoff_sha256"))

    @property
    def artifact_hashes(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for manifest in (self.manifest_001a3, self.manifest_001a4):
            for entry in manifest.get("artifacts") or []:
                hashes[_text(entry.get("name"))] = _text(entry.get("sha256"))
        return dict(sorted(hashes.items()))

    @property
    def graph_version(self) -> str:
        return f"{self.manifest_001a3.get('cut')}+{self.manifest_001a4.get('cut')}"

    def resolve_canonical_identity(self, candidate: Mapping[str, Any]) -> dict[str, str]:
        """Resolve only literal identities documented by the approved graph.

        Names, family text, approximate measures, leading-zero transformations
        and SKU suffix transformations are intentionally absent from this
        resolver. A contradictory exact id/SKU pair remains blocked.
        """
        item_ids = {
            _text(candidate.get(field))
            for field in ("canonical_item_id", "physical_item_id", "item_id", "component_item_id")
            if _text(candidate.get(field))
        }
        skus = {
            _text(candidate.get(field))
            for field in ("canonical_physical_sku", "physical_sku", "component_sku", "hub_item_code", "heca_reference")
            if _text(candidate.get(field))
        }
        id_matches = set().union(*(self.canonical_identities_by_item_id.get(value, set()) for value in item_ids)) if item_ids else set()
        sku_matches = set().union(*(self.canonical_identities_by_sku.get(value, set()) for value in skus)) if skus else set()
        matches = id_matches & sku_matches if id_matches and sku_matches else id_matches or sku_matches
        if len(matches) != 1:
            status = "IDENTITY_NOT_FOUND" if not matches else "IDENTITY_AMBIGUOUS"
            return {
                "canonical_physical_item_id": "",
                "canonical_physical_sku": "",
                "resolution_source": "APPROVED_GRAPH_EXACT_ONLY",
                "resolution_status": status,
            }
        item_id, sku = next(iter(matches))
        source = "EXACT_ITEM_ID_AND_SKU" if item_ids and skus else "EXACT_ITEM_ID" if item_ids else "EXACT_SKU"
        return {
            "canonical_physical_item_id": item_id,
            "canonical_physical_sku": sku,
            "resolution_source": source,
            "resolution_status": "RESOLVED_EXACT",
        }

    def affected_destinations_for_identity(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        """Return the complete expected Woo destination set for one exact component."""
        resolution = self.resolve_canonical_identity(candidate)
        if resolution["resolution_status"] != "RESOLVED_EXACT":
            return {**resolution, "status": "IDENTITY_MISMATCH", "destinations": [], "expected_count": 0}
        identity = (resolution["canonical_physical_item_id"], resolution["canonical_physical_sku"])
        destinations = [dict(row) for row in self.inverse_by_canonical_identity.get(identity, [])]
        return {
            **resolution,
            "status": "HAS_AFFECTED" if destinations else "NO_COMBINATIONS_BY_DESIGN",
            "destinations": destinations,
            "expected_count": len(destinations),
        }

    @staticmethod
    def _change_identity(change: Mapping[str, Any]) -> dict[str, set[str]]:
        target_keys: set[str] = set()
        skus: set[str] = set()
        woo_ids: set[str] = set()
        for field in ("component_target_key", "target_key", "item_id", "physical_item_id", "target_keys"):
            target_keys.update(_iter_identity_values(change.get(field)))
        for field in ("component_sku", "physical_sku", "sku", "hub_item_code", "heca_reference", "woo_sku", "skus"):
            skus.update(_iter_identity_values(change.get(field)))
        for field in ("component_woo_id", "woo_id", "woo_ids"):
            woo_ids.update(_iter_identity_values(change.get(field)))
        code = _text(change.get("code"))
        if code:
            target_keys.add(code)
            skus.add(code)
        if not target_keys and not skus and not woo_ids:
            raise CombinationPriceImpactError("A proposed change has no exact component identity.")
        return {"target_keys": target_keys, "skus": skus, "woo_ids": woo_ids}

    @staticmethod
    def _normalize_change(change: Mapping[str, Any], index: int) -> dict[str, Any]:
        old_value = change.get("old_price", change.get("current_price", change.get("price_before")))
        new_value = change.get("new_price", change.get("planned_price", change.get("price_after")))
        old_price = _money(_decimal(old_value, field=f"change[{index}].old_price"))
        new_price = _money(_decimal(new_value, field=f"change[{index}].new_price"))
        return {
            "change_index": index,
            "identities": CombinationPriceImpactService._change_identity(change),
            "old_price": old_price,
            "new_price": new_price,
            "unit_delta": _money(new_price - old_price),
            "trace_key": _text(change.get("proposal_key"))
            or _text(change.get("trace_key"))
            or _text(change.get("code"))
            or f"change-{index + 1}",
            "name": _text(change.get("name")),
            "source": dict(change),
        }

    @staticmethod
    def _edge_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
        return (
            _text(row.get("combination_woo_id")),
            _text(row.get("component_target_key")) or _text(row.get("component_item_id")),
            _text(row.get("component_sku")),
            _text(row.get("component_woo_id")),
        )

    @staticmethod
    def _quarantine_edge_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
        return (
            _text(row.get("combination_woo_id")),
            _text(row.get("component_item_id")) or _text(row.get("physical_item_id")),
            _text(row.get("component_sku")),
            _text(row.get("component_woo_id")),
        )

    def _matched_operational_edges(self, identities: Mapping[str, set[str]]) -> list[dict[str, str]]:
        matched: dict[tuple[str, str, str, str], dict[str, str]] = {}
        for identity in identities["target_keys"]:
            for row in self.matrix_by_target_key.get(identity, []):
                matched[self._edge_identity(row)] = row
        for identity in identities["skus"]:
            for row in self.matrix_by_sku.get(identity, []):
                matched[self._edge_identity(row)] = row
        for identity in identities["woo_ids"]:
            for row in self.matrix_by_component_woo_id.get(identity, []):
                matched[self._edge_identity(row)] = row
        return [matched[key] for key in sorted(matched)]

    def _matched_quarantine_edges(self, identities: Mapping[str, set[str]]) -> list[dict[str, str]]:
        matched: dict[tuple[str, str, str, str], dict[str, str]] = {}
        for identity in identities["target_keys"]:
            for row in self.quarantine_by_target_key.get(identity, []):
                matched[self._quarantine_edge_identity(row)] = row
        for identity in identities["skus"]:
            for row in self.quarantine_by_sku.get(identity, []):
                matched[self._quarantine_edge_identity(row)] = row
        for identity in identities["woo_ids"]:
            for row in self.quarantine_by_component_woo_id.get(identity, []):
                matched[self._quarantine_edge_identity(row)] = row
        return [matched[key] for key in sorted(matched)]

    def _relation_trace(self, matrix_row: Mapping[str, Any]) -> dict[str, str]:
        key = (_text(matrix_row.get("combination_woo_id")), _text(matrix_row.get("component_sku")))
        candidates = self.primary_edges.get(key, [])
        if not candidates:
            raise CombinationPriceImpactError(
                f"No clean-graph trace for combination {key[0]} component {key[1]}."
            )
        effective = [row for row in candidates if effective_edge_status(row) == "EXACT"]
        if not effective:
            raise CombinationPriceImpactError(
                f"No effectively exact edge for combination {key[0]} component {key[1]}."
            )
        row = sorted(
            effective,
            key=lambda item: (
                0 if _text(item.get("source")) == "WOO_SKU_COMPONENT_LIST" else 1,
                _text(item.get("source_row")),
            ),
        )[0]
        return {
            "source": _text(row.get("source")),
            "source_row": _text(row.get("source_row")),
            "historical_edge_status": _text(row.get("edge_status")),
            "effective_edge_status": effective_edge_status(row),
            "historical_resolution_status": _text(row.get("resolution_status")),
            "effective_resolution_status": effective_resolution_status(row),
            "rule_used": _text(row.get("rule_used")) or _text(matrix_row.get("edge_rule")),
            "confidence": _text(row.get("resolution_confidence"))
            or _text(matrix_row.get("edge_confidence")),
        }

    @staticmethod
    def _price_policy(combination: Mapping[str, Any]) -> dict[str, str]:
        regular = _text(combination.get("regular_price"))
        sale = _text(combination.get("sale_price"))
        sale_from = _text(combination.get("date_on_sale_from"))
        sale_to = _text(combination.get("date_on_sale_to"))
        if sale_from or sale_to:
            context = "SCHEDULED_DISCOUNT_PRESENT"
        elif sale:
            context = "SALE_PRICE_PRESENT_ACTIVE_STATE_UNVERIFIED"
        elif regular:
            context = "REGULAR_PRICE_ONLY"
        else:
            context = "PRICE_FIELDS_EMPTY"
        return {
            "price_context": context,
            "price_simulation_status": "BLOCKED_MISSING_PRICE_CONTEXT",
            "price_policy_reason": (
                "The approved direct pricing policy requires the complete current Woo variation context."
            ),
            "publication_allowed": "NO",
        }

    def impact_for_changes(self, changes: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        normalized = [self._normalize_change(change, index) for index, change in enumerate(changes)]
        operational_hits: dict[str, dict[tuple[str, str, str, str], tuple[dict[str, str], dict[str, Any]]]] = defaultdict(dict)
        quarantine_hits: dict[str, dict[tuple[str, str, str, str], tuple[dict[str, str], dict[str, Any]]]] = defaultdict(dict)
        unmatched: list[dict[str, Any]] = []

        for change in normalized:
            matched_operational = self._matched_operational_edges(change["identities"])
            matched_quarantine = self._matched_quarantine_edges(change["identities"])
            if not matched_operational and not matched_quarantine:
                unmatched.append({
                    "trace_key": change["trace_key"],
                    "reason": "NO_EXACT_COMPONENT_MATCH",
                    "publication_allowed": "NO",
                })
            for edge in matched_operational:
                combination_id = _text(edge.get("combination_woo_id"))
                edge_identity = self._edge_identity(edge)
                previous = operational_hits[combination_id].get(edge_identity)
                if previous and (
                    previous[1]["old_price"] != change["old_price"]
                    or previous[1]["new_price"] != change["new_price"]
                ):
                    raise CombinationPriceImpactError(
                        f"Conflicting proposed changes target the same exact component edge {edge_identity}."
                    )
                operational_hits[combination_id][edge_identity] = (edge, change)
            for edge in matched_quarantine:
                combination_id = _text(edge.get("combination_woo_id"))
                edge_identity = self._quarantine_edge_identity(edge)
                previous = quarantine_hits[combination_id].get(edge_identity)
                if previous and (
                    previous[1]["old_price"] != change["old_price"]
                    or previous[1]["new_price"] != change["new_price"]
                ):
                    raise CombinationPriceImpactError(
                        f"Conflicting proposed changes target the same quarantined edge {edge_identity}."
                    )
                quarantine_hits[combination_id][edge_identity] = (edge, change)

        included: list[dict[str, Any]] = []
        for combination_id in sorted(operational_hits, key=_identity_sort):
            if combination_id in self.exclusion_by_id:
                raise CombinationPriceImpactError(
                    f"Excluded combination {combination_id} entered the operational impact set."
                )
            combination = self.combination_by_id.get(combination_id)
            if not combination:
                raise CombinationPriceImpactError(f"Missing price input for combination {combination_id}.")
            components: list[dict[str, Any]] = []
            total_delta = Decimal("0")
            trace_keys: set[str] = set()
            relationships: set[str] = set()
            rules: set[str] = set()
            for edge_key in sorted(operational_hits[combination_id]):
                edge, change = operational_hits[combination_id][edge_key]
                quantity = _decimal(edge.get("component_quantity"), field="component_quantity")
                if quantity <= 0:
                    raise CombinationPriceImpactError(
                        f"Invalid quantity for combination {combination_id} component {edge.get('component_sku')}."
                    )
                weighted_delta = change["unit_delta"] * quantity
                total_delta += weighted_delta
                trace = self._relation_trace(edge)
                trace_keys.add(change["trace_key"])
                relationships.add(_text(edge.get("relationship_type")))
                rules.add(trace["rule_used"])
                components.append({
                    "component_target_key": _text(edge.get("component_target_key")),
                    "component_item_id": _text(edge.get("component_item_id")),
                    "component_woo_id": _text(edge.get("component_woo_id")),
                    "component_sku": _text(edge.get("component_sku")),
                    "quantity": _text(edge.get("component_quantity")),
                    "old_price": _money_text(change["old_price"]),
                    "new_price": _money_text(change["new_price"]),
                    "unit_delta": _money_text(change["unit_delta"]),
                    "weighted_delta": _money_text(weighted_delta),
                    "proposal_trace_key": change["trace_key"],
                    "relationship_type": _text(edge.get("relationship_type")),
                    "relation": trace,
                })
            current_price = _money(_decimal(combination.get("effective_price"), field="effective_price"))
            total_delta = _money(total_delta)
            simulated = _money(current_price + total_delta)
            policy = self._price_policy(combination)
            visual_state = "NO_CHANGE" if total_delta == 0 else "BLOCKED_MISSING_PRICE_CONTEXT"
            included.append({
                "combination_woo_id": combination_id,
                "combination_parent_woo_id": _text(combination.get("combination_parent_woo_id")),
                "combination_sku": _text(combination.get("combination_sku")),
                "combination_name": _text(combination.get("combination_name")),
                "woo_status": _text(combination.get("woo_status")),
                "regular_price": _text(combination.get("regular_price")),
                "sale_price": _text(combination.get("sale_price")),
                "effective_current_price": _money_text(current_price),
                "component_delta": _money_text(total_delta),
                "simulated_effective_price": _money_text(simulated),
                "modified_component_count": len(components),
                "modified_components": components,
                "proposal_trace_keys": sorted(trace_keys),
                "relationships": sorted(value for value in relationships if value),
                "relation_rules": sorted(value for value in rules if value),
                "inclusion_reason": "EXACT_COMPONENT_MATCH_IN_OPERATIONAL_GRAPH",
                "propagation_status": "READ_ONLY_PREVIEW",
                "visual_state": visual_state,
                "excluded": "NO",
                "exclusion_reason": "",
                **policy,
            })

        excluded: list[dict[str, Any]] = []
        for combination_id in sorted(quarantine_hits, key=_identity_sort):
            exclusion = self.exclusion_by_id.get(combination_id)
            if not exclusion:
                raise CombinationPriceImpactError(
                    f"Quarantined combination {combination_id} is missing from 001A.4 exclusions."
                )
            components: list[dict[str, Any]] = []
            for edge_key in sorted(quarantine_hits[combination_id]):
                edge, change = quarantine_hits[combination_id][edge_key]
                components.append({
                    "component_item_id": _text(edge.get("component_item_id"))
                    or _text(edge.get("physical_item_id")),
                    "component_woo_id": _text(edge.get("component_woo_id")),
                    "component_sku": _text(edge.get("component_sku")),
                    "quantity": _text(edge.get("quantity")),
                    "proposal_trace_key": change["trace_key"],
                })
            excluded.append({
                "combination_woo_id": combination_id,
                "combination_parent_woo_id": "",
                "combination_sku": _text(exclusion.get("combination_sku")),
                "combination_name": _text(exclusion.get("combination_name")),
                "effective_current_price": _text(exclusion.get("current_price")),
                "component_delta": "",
                "simulated_effective_price": "",
                "modified_component_count": len(components),
                "modified_components": components,
                "proposal_trace_keys": sorted({row[1]["trace_key"] for row in quarantine_hits[combination_id].values()}),
                "relationships": [],
                "relation_rules": [],
                "inclusion_reason": "",
                "propagation_status": "BLOCKED_QUARANTINE",
                "visual_state": "EXCLUIDA POR CUARENTENA",
                "excluded": "YES",
                "exclusion_reason": _text(exclusion.get("quarantine_reason")),
                "quarantine_group_ids": sorted(_split_group_ids(exclusion.get("quarantine_group_ids"))),
                "price_context": "NOT_EVALUATED_QUARANTINE",
                "price_simulation_status": "BLOCKED",
                "price_policy_reason": "Quarantined combinations cannot enter simulation or propagation.",
                "publication_allowed": "NO",
            })

        if {row["combination_woo_id"] for row in included}.intersection(
            row["combination_woo_id"] for row in excluded
        ):
            raise CombinationPriceImpactError("Operational and excluded results overlap.")

        result = {
            "status": "READ_ONLY_PREVIEW",
            "cuts": [CUT_001A3, CUT_001A4],
            "source_handoff_sha256": self.source_handoff_sha256,
            "artifact_hashes": self.artifact_hashes,
            "matching_policy": "EXACT_ONLY_LITERAL_IDENTITIES",
            "suffix_policy": "PRESERVE_FULL_SKU_NO_SUFFIX_NORMALIZATION",
            "price_policy": "EXISTING_DIRECT_PRICE_POLICY_REQUIRES_LIVE_CONTEXT",
            "publication_allowed": "NO",
            "proposed_change_count": len(normalized),
            "included_combinations": included,
            "excluded_combinations": excluded,
            "unmatched_changes": unmatched,
            "counts": {
                "base_items_modified": len(normalized),
                "included_combinations": len(included),
                "excluded_combinations": len(excluded),
                "resulting_woo_variations": len(included),
                "no_change_combinations": sum(row["visual_state"] == "NO_CHANGE" for row in included),
                "policy_pending_combinations": sum(
                    row["price_simulation_status"] == "POLICY_PENDING" for row in included
                ),
                "missing_price_context_combinations": sum(
                    row["price_simulation_status"] == "BLOCKED_MISSING_PRICE_CONTEXT" for row in included
                ),
                "traceability_errors": len(unmatched),
            },
        }
        return result

    def describe(self) -> dict[str, Any]:
        return {
            "status": "READY_READ_ONLY",
            "graph_version": self.graph_version,
            "source_kind": self.source_kind,
            "artifact_root": str(self.artifact_root),
            "cuts": [CUT_001A3, CUT_001A4],
            "source_handoff_sha256": self.source_handoff_sha256,
            "artifact_hashes": self.artifact_hashes,
            "clean_graph_edges": len(self.clean_graph_rows),
            "operational_combinations": len(self.price_combinations),
            "impact_matrix_rows": len(self.impact_matrix),
            "excluded_combinations": len(self.exclusions),
            "target_key_index_size": len(self.matrix_by_target_key),
            "physical_sku_index_size": len(self.matrix_by_sku),
            "component_woo_id_index_size": len(self.matrix_by_component_woo_id),
            "canonical_identity_index_size": len(self.inverse_by_canonical_identity),
            "physical_components_with_destinations": sum(bool(rows) for rows in self.inverse_by_canonical_identity.values()),
            "physical_components_without_destinations": sum(not rows for rows in self.inverse_by_canonical_identity.values()),
            "combination_woo_id_index_size": len(self.matrix_by_combination),
            "special_literal_suffix_skus": sorted(SPECIAL_LITERAL_SUFFIX_SKUS),
            "matching_policy": "EXACT_ONLY_LITERAL_IDENTITIES",
            "price_policy": "EXISTING_DIRECT_PRICE_POLICY_REQUIRES_LIVE_CONTEXT",
            "publication_allowed": "NO",
            "network_clients": 0,
            "persistence_clients": 0,
        }


def render_combination_impact_html(result: Mapping[str, Any], destination: str | Path) -> Path:
    """Write a standalone responsive HTML rendering of an impact preview."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    counts = result.get("counts") or {}
    cards = [
        ("Artículos base", counts.get("base_items_modified", 0)),
        ("Combinaciones afectadas", counts.get("included_combinations", 0)),
        ("Excluidas", counts.get("excluded_combinations", 0)),
        ("Sin cambio", counts.get("no_change_combinations", 0)),
    ]
    card_html = "".join(
        f'<div class="metric"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>'
        for label, value in cards
    )

    def combination_html(row: Mapping[str, Any], *, excluded: bool) -> str:
        state = _text(row.get("visual_state"))
        state_class = "excluded" if excluded else ("no-change" if state == "SIN CAMBIO" else "pending")
        current = _text(row.get("effective_current_price")) or "-"
        delta = _text(row.get("component_delta")) or "-"
        simulated = _text(row.get("simulated_effective_price")) or "-"
        reason = _text(row.get("exclusion_reason")) or _text(row.get("price_policy_reason"))
        components = row.get("modified_components") or []
        component_rows = "".join(
            "<tr>"
            f"<td>{escape(_text(component.get('component_sku')) or '-')}</td>"
            f"<td>{escape(_text(component.get('component_target_key')) or _text(component.get('component_item_id')) or '-')}</td>"
            f"<td>{escape(_text(component.get('quantity')) or '-')}</td>"
            f"<td>{escape(_text(component.get('old_price')) or '-')}</td>"
            f"<td>{escape(_text(component.get('new_price')) or '-')}</td>"
            f"<td>{escape(_text(component.get('weighted_delta')) or '-')}</td>"
            f"<td>{escape(_text(component.get('proposal_trace_key')) or '-')}</td>"
            "</tr>"
            for component in components
        )
        return (
            '<details class="combination" open>'
            "<summary>"
            '<div class="identity">'
            f'<span class="sku">{escape(_text(row.get("combination_sku")) or "Sin SKU")}</span>'
            f'<span class="name">{escape(_text(row.get("combination_name")))}</span>'
            "</div>"
            '<div class="prices">'
            f'<span><small>Actual</small>{escape(current)} €</span>'
            f'<span><small>Delta</small>{escape(delta)} €</span>'
            f'<span><small>Simulado</small>{escape(simulated)} €</span>'
            f'<b class="state {state_class}">{escape(state)}</b>'
            "</div>"
            "</summary>"
            f'<p class="reason">{escape(reason)}</p>'
            '<div class="table-wrap"><table><thead><tr>'
            "<th>Componente</th><th>Target exacto</th><th>Cantidad</th><th>Anterior</th>"
            "<th>Nuevo</th><th>Delta ponderado</th><th>Trazabilidad</th>"
            f"</tr></thead><tbody>{component_rows}</tbody></table></div>"
            "</details>"
        )

    included_html = "".join(
        combination_html(row, excluded=False) for row in result.get("included_combinations") or []
    ) or '<p class="empty">No hay combinaciones operativas afectadas.</p>'
    excluded_html = "".join(
        combination_html(row, excluded=True) for row in result.get("excluded_combinations") or []
    ) or '<p class="empty">No hay exclusiones afectadas por esta muestra.</p>'
    unmatched_html = "".join(
        f'<li><b>{escape(_text(row.get("trace_key")))}</b>: {escape(_text(row.get("reason")))}</li>'
        for row in result.get("unmatched_changes") or []
    ) or "<li>Ninguno</li>"

    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FutonHUB · Impacto en combinaciones Woo</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#667085; --line:#d9dee7; --panel:#fff; --soft:#f4f6f8; --blue:#1769aa; --amber:#9a6700; --amber-bg:#fff4ce; --red:#b42318; --red-bg:#fee4e2; --green:#157347; --green-bg:#e7f6ec; }}
    * {{ box-sizing:border-box; }}
    html,body {{ max-width:100%; overflow-x:hidden; }}
    body {{ margin:0; background:#eef1f4; color:var(--ink); font:14px/1.45 "Segoe UI", Arial, sans-serif; }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:20px clamp(16px,4vw,44px); }}
    header h1 {{ margin:0; font-size:24px; letter-spacing:0; }}
    header p {{ margin:5px 0 0; color:var(--muted); }}
    main {{ width:100%; max-width:1280px; min-width:0; margin:auto; padding:20px clamp(12px,3vw,32px) 48px; }}
    .safety {{ border-left:4px solid var(--amber); background:var(--amber-bg); padding:12px 14px; margin-bottom:16px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:20px; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:14px; min-width:0; }}
    .metric span {{ color:var(--muted); display:block; }} .metric strong {{ font-size:25px; }}
    section {{ width:100%; min-width:0; margin-top:24px; }} h2 {{ font-size:18px; margin:0 0 10px; }}
    .combination {{ width:100%; min-width:0; background:var(--panel); border:1px solid var(--line); border-radius:6px; margin:9px 0; overflow:hidden; }}
    summary {{ width:100%; min-width:0; cursor:pointer; display:flex; gap:16px; align-items:center; justify-content:space-between; padding:14px; }}
    .identity {{ min-width:0; display:grid; gap:3px; }} .sku {{ font-weight:700; overflow-wrap:anywhere; }} .name {{ color:var(--muted); }}
    .prices {{ min-width:0; max-width:100%; display:flex; gap:16px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }}
    .prices span {{ font-weight:700; white-space:nowrap; }} .prices small {{ display:block; color:var(--muted); font-weight:400; }}
    .state {{ max-width:100%; border-radius:4px; padding:6px 8px; font-size:12px; white-space:nowrap; overflow-wrap:anywhere; }}
    .state.pending {{ color:var(--amber); background:var(--amber-bg); }} .state.excluded {{ color:var(--red); background:var(--red-bg); }} .state.no-change {{ color:var(--green); background:var(--green-bg); }}
    .reason {{ margin:0; padding:0 14px 12px; color:var(--muted); }}
    .table-wrap {{ width:100%; max-width:100%; min-width:0; overflow-x:auto; border-top:1px solid var(--line); }} table {{ width:100%; border-collapse:collapse; min-width:760px; }}
    th,td {{ text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); }} th {{ background:var(--soft); font-size:12px; }}
    .empty {{ background:#fff; border:1px dashed var(--line); padding:18px; color:var(--muted); }}
    .trace {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:14px 18px; }}
    @media (max-width:760px) {{
      header h1 {{ font-size:20px; }} .metrics {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
      summary {{ align-items:flex-start; flex-direction:column; }} .prices {{ justify-content:flex-start; gap:11px; width:100%; }}
      .prices span {{ min-width:62px; }} .state {{ white-space:normal; }} details[open] summary {{ border-bottom:1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <header><h1>Impacto en combinaciones Woo</h1><p>Preview local read-only · matching exacto · sufijos preservados</p></header>
  <main>
    <div class="safety"><b>Publicacion bloqueada en este preview local.</b> La politica aprobada se aplicara solo despues de leer el contexto Woo completo y actual de cada variacion.</div>
    <div class="metrics">{card_html}</div>
    <section><h2>Combinaciones operativas</h2>{included_html}</section>
    <section><h2>Exclusiones por cuarentena</h2>{excluded_html}</section>
    <section><h2>Errores de trazabilidad</h2><ul class="trace">{unmatched_html}</ul></section>
  </main>
</body>
</html>
"""
    destination.write_text(html, encoding="utf-8", newline="\n")
    return destination

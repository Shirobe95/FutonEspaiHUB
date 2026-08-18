from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from futonhub.core.runtime_integrity import CHECKSUM_MODE_UTF8_TEXT_LF_V1, canonical_text_sha256
from futonhub.ui.erp.catalog_filters import PhysicalCatalogSnapshot, natural_catalog_sort_key


RUNTIME_SCHEMA = "futonhub.runtime.inventory_visibility_overrides.v1"
EMPTY_OVERRIDE = "__EMPTY__"
VISIBLE_YES = "YES"
VISIBLE_NO = "NO"

REQUIRED_COLUMNS = {
    "item_id",
    "inventory_visible",
    "visibility_reason",
    "filter_family_override",
    "filter_group_override",
    "filter_size_override",
    "filter_gama_override",
    "name_override",
    "family_override",
    "business_usage",
    "price_policy_override",
}


class InventoryVisibilityConfigurationError(RuntimeError):
    """Raised when the packaged inventory visibility contract is not trusted."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def inventory_visibility_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "runtime_config" / "inventory_visibility_overrides_manifest.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: _text(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def _override_value(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    return "" if text == EMPTY_OVERRIDE else text


@dataclass(frozen=True)
class InventoryVisibilityOverrides:
    rows_by_item_id: dict[str, dict[str, str]]
    source_path: Path
    manifest_path: Path
    expected_count: int
    expected_effective_delta: int

    @classmethod
    @lru_cache(maxsize=1)
    def load_runtime_cached(cls) -> "InventoryVisibilityOverrides":
        return cls.load()

    @classmethod
    def load(cls, path: Path | None = None) -> "InventoryVisibilityOverrides":
        manifest_path = inventory_visibility_manifest_path()
        if not manifest_path.is_file():
            raise InventoryVisibilityConfigurationError(
                f"No se encontro el manifiesto de visibilidad de inventario: {manifest_path}"
            )
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if payload.get("schema") != RUNTIME_SCHEMA:
                raise ValueError("unexpected inventory visibility schema")
            if payload.get("contains_prices") is not False:
                raise ValueError("inventory visibility contract must not contain prices")
            if payload.get("contains_stock") is not False:
                raise ValueError("inventory visibility contract must not contain stock")
            if payload.get("contains_credentials") is not False:
                raise ValueError("inventory visibility contract must not contain credentials")
            if payload.get("fail_closed") is not True:
                raise ValueError("inventory visibility contract must fail closed")
            relative_snapshot = str(payload["snapshot_relative_path"])
            expected_count = int(payload["expected_count"])
            expected_effective_delta = int(payload.get("expected_effective_delta", 0))
            expected_sha256 = str(payload["snapshot_sha256"])
            checksum_mode = str(payload["checksum_mode"])
            declared_columns = {str(column) for column in payload.get("required_columns") or []}
            if not relative_snapshot or Path(relative_snapshot).is_absolute() or expected_count <= 0:
                raise ValueError("invalid inventory visibility manifest values")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
                raise ValueError("invalid inventory visibility checksum")
            if checksum_mode != CHECKSUM_MODE_UTF8_TEXT_LF_V1:
                raise ValueError(f"unsupported inventory visibility checksum mode: {checksum_mode}")
            missing_declared = sorted(REQUIRED_COLUMNS - declared_columns)
            if missing_declared:
                raise ValueError("manifest omits required columns: " + ", ".join(missing_declared))
            source_path = (manifest_path.parent / relative_snapshot).resolve()
            runtime_root = manifest_path.parent.resolve()
            if runtime_root not in source_path.parents:
                raise ValueError("inventory visibility path leaves runtime_config")
            if path is None:
                actual_sha256 = canonical_text_sha256(source_path.read_bytes(), checksum_mode)
                if actual_sha256 != expected_sha256:
                    raise ValueError("inventory visibility checksum mismatch")
            else:
                source_path = path
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise InventoryVisibilityConfigurationError(
                f"Manifest de visibilidad de inventario invalido: {manifest_path}: {exc}"
            ) from exc

        try:
            rows = _read_csv(source_path)
        except OSError as exc:
            raise InventoryVisibilityConfigurationError(f"No se pudo leer visibilidad de inventario runtime: {exc}") from exc
        missing_csv = sorted(REQUIRED_COLUMNS - set(rows[0].keys() if rows else []))
        if missing_csv:
            raise InventoryVisibilityConfigurationError(
                "La visibilidad de inventario runtime no contiene columnas requeridas: " + ", ".join(missing_csv)
            )
        if len(rows) != expected_count:
            raise InventoryVisibilityConfigurationError(
                f"La visibilidad de inventario runtime debe contener {expected_count} filas; contiene {len(rows)}."
            )

        indexed: dict[str, dict[str, str]] = {}
        for row in rows:
            item_id = _text(row.get("item_id"))
            visible = _text(row.get("inventory_visible")).upper()
            if not item_id or item_id in indexed or visible not in {VISIBLE_YES, VISIBLE_NO}:
                raise InventoryVisibilityConfigurationError("Visibilidad de inventario contiene item_id duplicado o estado invalido.")
            indexed[item_id] = {**row, "item_id": item_id, "inventory_visible": visible}
        return cls(
            rows_by_item_id=indexed,
            source_path=source_path,
            manifest_path=manifest_path,
            expected_count=expected_count,
            expected_effective_delta=expected_effective_delta,
        )

    @property
    def included_item_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (item_id for item_id, row in self.rows_by_item_id.items() if row["inventory_visible"] == VISIBLE_YES),
                key=natural_catalog_sort_key,
            )
        )

    @property
    def excluded_item_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (item_id for item_id, row in self.rows_by_item_id.items() if row["inventory_visible"] == VISIBLE_NO),
                key=natural_catalog_sort_key,
            )
        )

    def requested_item_ids(self, physical_item_ids: Iterable[Any]) -> tuple[str, ...]:
        values = {_text(value) for value in physical_item_ids if _text(value)}
        values.update(self.included_item_ids)
        return tuple(sorted(values, key=natural_catalog_sort_key))

    def expected_visible_count(self, physical_count: int) -> int:
        return int(physical_count) + self.expected_effective_delta

    def metadata_for_item_id(self, item_id: Any) -> dict[str, str]:
        return dict(self.rows_by_item_id.get(_text(item_id)) or {})

    def _apply_row_overrides(self, row: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(row)
        mapping = {
            "name_override": "name",
            "family_override": "family",
            "filter_family_override": "filter_family",
            "filter_group_override": "filter_group",
            "filter_size_override": "filter_size",
            "filter_gama_override": "filter_gama",
        }
        for source_field, target_field in mapping.items():
            value = _override_value(override.get(source_field))
            if value is not None:
                result[target_field] = value
        result["inventory_visibility_reason"] = _text(override.get("visibility_reason"))
        result["inventory_visibility_contract"] = RUNTIME_SCHEMA
        result["business_usage"] = _text(override.get("business_usage"))
        price_policy = _text(override.get("price_policy_override")).upper()
        if price_policy:
            result["price_policy_override"] = price_policy
            if price_policy == "NO":
                result["price_operable"] = False
                result["sale_item"] = "NO"
        return result

    def apply_to_live_rows(
        self,
        snapshot: PhysicalCatalogSnapshot,
        rows: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        live_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            item_id = _text(row.get("item_id"))
            if item_id and item_id not in live_by_id:
                live_by_id[item_id] = dict(row)

        result_by_id = {
            _text(row.get("item_id")): dict(row)
            for row in snapshot.eligible_live_rows(rows)
            if _text(row.get("item_id")) not in self.excluded_item_ids
        }
        for item_id in self.included_item_ids:
            live = live_by_id.get(item_id)
            if live is None:
                continue
            result_by_id[item_id] = self._apply_row_overrides(live, self.rows_by_item_id[item_id])
        for item_id, override in self.rows_by_item_id.items():
            if item_id in result_by_id:
                result_by_id[item_id] = self._apply_row_overrides(result_by_id[item_id], override)
        return sorted(result_by_id.values(), key=lambda row: natural_catalog_sort_key(row.get("name") or row.get("item_id")))

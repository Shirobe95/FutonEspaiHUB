from __future__ import annotations

import csv
import json
import re
import tkinter as tk
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Iterable, Mapping

from futonhub.core.runtime_integrity import CHECKSUM_MODE_UTF8_TEXT_LF_V1, canonical_text_sha256
from futonhub.ui.erp.responsive import catalog_filter_bar_layout


FILTER_FIELDS = ("filter_family", "filter_group", "filter_size", "filter_gama")
_LITERAL_CODE_SEARCH_FIELDS = (
    "physical_sku",
    "hub_item_code",
    "heca_reference",
    "item_id",
    "base_item_code",
    "canonical_item_id",
    "woo_sku",
    "woo_id",
)
_LITERAL_CODE_EXACT_PRIORITY = {
    "physical_sku": 1,
    "hub_item_code": 2,
    "heca_reference": 3,
    "item_id": 4,
    # These identifiers remain exact identity inputs. They share the fourth
    # rank because no stronger display identity was supplied by the user.
    "base_item_code": 4,
    "canonical_item_id": 4,
    # Woo identifiers are explicit auxiliary lookup values only.
    "woo_sku": 4,
    "woo_id": 4,
}
# Kept for callers that imported the former frozen 003A value. Runtime uses the
# versioned snapshot manifest and its expected_count instead.
EXPECTED_PHYSICAL_UI_ELIGIBLE_COUNT = 208
LEGACY_PHYSICAL_UI_ELIGIBLE_COUNT = 208
_TRUE_VALUES = {"1", "true", "yes", "si"}
_CODE_FIELDS = ("heca_reference", "hub_item_code", "base_item_code")
_RELATION_ID_FIELDS = ("canonical_item_id", "linked_item_id", "parent_item_id", "base_item_id")
_VALID_PHYSICAL_SOURCES = {"dat", "maestro", "user_approved", "user_confirmed"}
_RUNTIME_PHYSICAL_CATALOG_COLUMNS = {
    "item_id", "heca_reference", "hub_item_code", "base_item_code", "item_record_type", "is_pack",
    "name", "family", "size", "filter_family", "filter_group", "filter_size", "filter_gama",
    "physical_validation_source", "canonical_resolution_status", "ui_eligibility_status",
}
_TEXT_CHECKSUM_MODE_UTF8_TEXT_LF_V1 = CHECKSUM_MODE_UTF8_TEXT_LF_V1


class CatalogFilterConfigurationError(RuntimeError):
    """Raised when the frozen 003A eligibility snapshot cannot be trusted."""


def normalize_catalog_text(value: object) -> str:
    text = str(value or "").strip().casefold()
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def classify_catalog_query(value: object) -> str:
    """Classify a user query without changing its stored identifier spelling."""
    query = str(value or "").strip()
    if not query:
        return "EMPTY"
    # Codes have no whitespace and retain their separators and suffixes. A
    # digit is required so ordinary product names remain secondary text search.
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", query) and any(char.isdigit() for char in query):
        return "CODE_LITERAL"
    return "TEXT"


def ranked_catalog_search_rows(
    rows: Iterable[Mapping[str, Any]],
    query: object,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    """Return literal code matches first, with deterministic diagnostics.

    The function intentionally never converts identifiers to numbers and never
    strips zeroes, suffixes, or separators. Code-like queries allow exact and
    literal-prefix matches only; this prevents numeric near matches such as
    ``2014`` from silently resolving ``0402014``.
    """
    literal_query = str(query or "").strip()
    query_type = classify_catalog_query(literal_query)
    materialized = [dict(row) for row in rows]
    if query_type == "EMPTY":
        return materialized, {
            "query": literal_query,
            "query_type": query_type,
            "matched_field": "",
            "matched_value": "",
            "result_count": len(materialized),
            "top_result_physical_sku": str(materialized[0].get("physical_sku") or "") if materialized else "",
        }

    matches: list[tuple[tuple[int, int, int], dict[str, Any], str, str]] = []
    literal_folded = literal_query.casefold()
    text_query = normalize_catalog_text(literal_query)
    for position, row in enumerate(materialized):
        matched_field = ""
        matched_value = ""
        rank: int | None = None
        if query_type == "CODE_LITERAL":
            for field in _LITERAL_CODE_SEARCH_FIELDS:
                value = str(row.get(field) or "").strip()
                if value and value.casefold() == literal_folded:
                    matched_field = field
                    matched_value = value
                    rank = _LITERAL_CODE_EXACT_PRIORITY[field]
                    break
            if rank is None:
                for field in _LITERAL_CODE_SEARCH_FIELDS:
                    value = str(row.get(field) or "").strip()
                    if value and value.casefold().startswith(literal_folded):
                        matched_field = field
                        matched_value = value
                        rank = 5
                        break
        else:
            for field in (*_LITERAL_CODE_SEARCH_FIELDS, "code", "name", "display_name"):
                value = str(row.get(field) or "").strip()
                if value and text_query in normalize_catalog_text(value):
                    matched_field = field
                    matched_value = value
                    rank = 6
                    break
        if rank is not None:
            field_order = _LITERAL_CODE_SEARCH_FIELDS.index(matched_field) if matched_field in _LITERAL_CODE_SEARCH_FIELDS else len(_LITERAL_CODE_SEARCH_FIELDS)
            matches.append(((rank, field_order, position), row, matched_field, matched_value))

    matches.sort(key=lambda item: item[0])
    ordered_rows = [row for _sort, row, _field, _value in matches]
    first = matches[0] if matches else None
    return ordered_rows, {
        "query": literal_query,
        "query_type": query_type,
        "matched_field": first[2] if first else "",
        "matched_value": first[3] if first else "",
        "result_count": len(ordered_rows),
        "top_result_physical_sku": str(first[1].get("physical_sku") or "") if first else "",
    }


def natural_catalog_sort_key(value: object) -> tuple[tuple[int, object], ...]:
    normalized = normalize_catalog_text(value)
    pieces = re.split(r"(\d+)", normalized)
    return tuple((0, int(piece)) if piece.isdigit() else (1, piece) for piece in pieces)


def _truthy(value: object) -> bool:
    return value is True or normalize_catalog_text(value) in _TRUE_VALUES


def normalize_physical_code_comparison_key(value: object) -> str:
    """Return a comparison key for numeric codes without changing their visible text."""
    raw = str(value or "").strip()
    if not raw or not re.fullmatch(r"[0-9]+", raw):
        return raw
    return raw.lstrip("0") or "0"


def physical_catalog_snapshot_manifest_path() -> Path:
    """Return the versioned physical-catalog contract shipped with the ERP."""
    return Path(__file__).resolve().parents[2] / "runtime_config" / "physical_catalog_snapshot_manifest.json"


def _physical_catalog_snapshot_configuration() -> tuple[Path, int, frozenset[str], str, str, Path]:
    manifest_path = physical_catalog_snapshot_manifest_path()
    if not manifest_path.is_file():
        raise CatalogFilterConfigurationError(
            f"No se encontro el manifiesto de allowlist fisica vigente: {manifest_path}"
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        relative_snapshot = str(payload["snapshot_relative_path"])
        expected_count = int(payload["expected_count"])
        snapshot_sha256 = str(payload["snapshot_sha256"])
        checksum_mode = str(payload["checksum_mode"])
        if not relative_snapshot or Path(relative_snapshot).is_absolute() or expected_count <= 0:
            raise ValueError("invalid snapshot manifest values")
        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256):
            raise ValueError("invalid snapshot checksum")
        if checksum_mode != _TEXT_CHECKSUM_MODE_UTF8_TEXT_LF_V1:
            raise ValueError(f"unsupported snapshot checksum mode: {checksum_mode}")
        source_path = (manifest_path.parent / relative_snapshot).resolve()
        root = manifest_path.parent.resolve()
        if root not in source_path.parents:
            raise ValueError("snapshot path leaves the runtime configuration directory")
        approved_keys = frozenset(
            normalize_physical_code_comparison_key(value)
            for value in payload.get("approved_leading_zero_comparison_keys", [])
            if normalize_physical_code_comparison_key(value)
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise CatalogFilterConfigurationError(f"Manifest de allowlist fisica invalido: {manifest_path}: {exc}") from exc
    return source_path, expected_count, approved_keys, snapshot_sha256, checksum_mode, manifest_path


@dataclass(frozen=True)
class CatalogFilterSelection:
    filter_family: str = ""
    filter_group: str = ""
    filter_size: str = ""
    filter_gama: str = ""
    query: str = ""

    def with_filter(self, field: str, value: object) -> "CatalogFilterSelection":
        if field not in FILTER_FIELDS:
            raise ValueError(f"Unknown catalog filter field: {field}")
        updates: dict[str, str] = {field: str(value or "").strip()}
        for child in FILTER_FIELDS[FILTER_FIELDS.index(field) + 1:]:
            updates[child] = ""
        return replace(self, **updates)

    def with_query(self, value: object) -> "CatalogFilterSelection":
        return replace(self, query=str(value or "").strip())

    @property
    def has_hierarchy(self) -> bool:
        return any(getattr(self, field) for field in FILTER_FIELDS)


@dataclass(frozen=True)
class VisibleItemSelection:
    """Selection state that is always constrained to the currently visible IDs."""

    selected_item_ids: frozenset[str] = frozenset()

    @staticmethod
    def _normalized_ids(item_ids: Iterable[object]) -> frozenset[str]:
        return frozenset(str(item_id or "").strip() for item_id in item_ids if str(item_id or "").strip())

    def reconcile(self, visible_item_ids: Iterable[object]) -> "VisibleItemSelection":
        return replace(self, selected_item_ids=self.selected_item_ids & self._normalized_ids(visible_item_ids))

    def with_item(self, item_id: object, selected: bool, visible_item_ids: Iterable[object]) -> "VisibleItemSelection":
        visible = self._normalized_ids(visible_item_ids)
        value = str(item_id or "").strip()
        current = self.selected_item_ids & visible
        if selected and value in visible:
            current = current | {value}
        else:
            current = current - {value}
        return replace(self, selected_item_ids=frozenset(current))

    def toggle_all_visible(self, visible_item_ids: Iterable[object]) -> "VisibleItemSelection":
        visible = self._normalized_ids(visible_item_ids)
        current = self.selected_item_ids & visible
        return replace(self, selected_item_ids=frozenset() if visible and current == visible else visible)


def row_matches_catalog_filters(row: Mapping[str, Any], selection: CatalogFilterSelection) -> bool:
    for field in FILTER_FIELDS:
        wanted = getattr(selection, field)
        if wanted and normalize_catalog_text(row.get(field)) != normalize_catalog_text(wanted):
            return False
    needle = normalize_catalog_text(selection.query)
    if not needle:
        return True
    haystack = " ".join(str(row.get(key) or "") for key in ("item_id", "heca_reference", "hub_item_code", "code", "name"))
    return needle in normalize_catalog_text(haystack)


def filter_catalog_rows(rows: Iterable[Mapping[str, Any]], selection: CatalogFilterSelection) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row_matches_catalog_filters(row, selection)]


def catalog_filter_options(rows: Iterable[Mapping[str, Any]], selection: CatalogFilterSelection) -> dict[str, list[str]]:
    """Return cascading option values using only selections above each level."""
    materialized = [dict(row) for row in rows]
    result: dict[str, list[str]] = {}
    for index, field in enumerate(FILTER_FIELDS):
        ancestors = CatalogFilterSelection(**{
            ancestor: getattr(selection, ancestor)
            for ancestor in FILTER_FIELDS[:index]
        })
        values = {
            str(row.get(field) or "").strip()
            for row in materialized
            if row_matches_catalog_filters(row, ancestors) and str(row.get(field) or "").strip()
        }
        result[field] = sorted(values, key=natural_catalog_sort_key)
    return result


@dataclass(frozen=True)
class PhysicalCatalogSnapshot:
    rows_by_item_id: dict[str, dict[str, str]]
    rows_by_code: dict[str, dict[str, str]]
    rows_by_approved_comparison_key: dict[str, dict[str, str]]
    source_path: Path
    expected_count: int
    manifest_path: Path | None

    @property
    def item_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.rows_by_item_id, key=natural_catalog_sort_key))

    @classmethod
    def load(cls, path: Path | None = None) -> "PhysicalCatalogSnapshot":
        configured_path, expected_count, approved_keys, expected_sha256, checksum_mode, manifest_path = _physical_catalog_snapshot_configuration()
        source_path = path or configured_path
        if not source_path.is_file():
            raise CatalogFilterConfigurationError(
                f"No se encontro la allowlist fisica vigente: {source_path}"
            )
        try:
            with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = set(reader.fieldnames or [])
                missing = sorted(_RUNTIME_PHYSICAL_CATALOG_COLUMNS - headers)
                if missing:
                    raise CatalogFilterConfigurationError(
                    "La allowlist fisica vigente no contiene columnas requeridas: " + ", ".join(missing)
                    )
                rows = [
                    {key: str(value or "").strip() for key, value in row.items()}
                    for row in reader
                ]
        except OSError as exc:
            raise CatalogFilterConfigurationError(f"No se pudo leer la allowlist fisica 003A: {exc}") from exc

        if path is None:
            try:
                digest = canonical_text_sha256(source_path.read_bytes(), checksum_mode)
            except (OSError, ValueError) as exc:
                raise CatalogFilterConfigurationError(
                    "No se pudo validar la huella SHA-256 de la allowlist fisica vigente."
                ) from exc
            if digest != expected_sha256:
                raise CatalogFilterConfigurationError(
                    "La allowlist fisica vigente no coincide con la huella SHA-256 del manifiesto."
                )

        rows_by_item_id: dict[str, dict[str, str]] = {}
        code_candidates: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            item_id = row.get("item_id", "")
            source = normalize_catalog_text(row.get("physical_validation_source"))
            if (
                not item_id
                or row.get("ui_eligibility_status") != "PHYSICAL_UI_ELIGIBLE"
                or normalize_catalog_text(row.get("item_record_type")) != "simple"
                or _truthy(row.get("is_pack"))
                or source not in _VALID_PHYSICAL_SOURCES
                or any(not row.get(field) for field in FILTER_FIELDS)
                or item_id in rows_by_item_id
            ):
                raise CatalogFilterConfigurationError(
                    "La allowlist fisica vigente contiene una fila no valida o duplicada."
                )
            rows_by_item_id[item_id] = row
            for field in _CODE_FIELDS:
                code = normalize_catalog_text(row.get(field))
                if code:
                    code_candidates.setdefault(code, []).append(row)

        if len(rows_by_item_id) != expected_count:
            raise CatalogFilterConfigurationError(
                f"La allowlist fisica vigente debe contener {expected_count} filas; contiene {len(rows_by_item_id)}."
            )

        rows_by_code = {
            code: candidates[0]
            for code, candidates in code_candidates.items()
            if len({candidate["item_id"] for candidate in candidates}) == 1
        }
        comparison_candidates: dict[str, list[dict[str, str]]] = {}
        for code, candidates in code_candidates.items():
            comparison_key = normalize_physical_code_comparison_key(code)
            if comparison_key in approved_keys:
                comparison_candidates.setdefault(comparison_key, []).extend(candidates)
        rows_by_approved_comparison_key = {
            key: candidates[0]
            for key, candidates in comparison_candidates.items()
            if len({candidate["item_id"] for candidate in candidates}) == 1
        }
        return cls(
            rows_by_item_id=rows_by_item_id,
            rows_by_code=rows_by_code,
            rows_by_approved_comparison_key=rows_by_approved_comparison_key,
            source_path=source_path,
            expected_count=expected_count,
            manifest_path=manifest_path,
        )

    def eligible_live_rows(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Keep only current physical rows that still satisfy the frozen 003A contract."""
        accepted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source_row in rows:
            row = dict(source_row)
            item_id = str(row.get("item_id") or "").strip()
            if item_id in seen or item_id not in self.rows_by_item_id:
                continue
            if normalize_catalog_text(row.get("item_record_type")) != "simple" or _truthy(row.get("is_pack")):
                continue
            if any(not str(row.get(field) or "").strip() for field in FILTER_FIELDS):
                continue
            seen.add(item_id)
            accepted.append(row)
        return sorted(accepted, key=lambda row: natural_catalog_sort_key(row.get("name") or row.get("item_id")))

    def resolve_price_row(self, row: Mapping[str, Any]) -> tuple[dict[str, str] | None, str]:
        """Resolve catalog metadata only through deterministic identity fields."""
        item_id = str(row.get("item_id") or "").strip()
        if item_id in self.rows_by_item_id:
            return self.rows_by_item_id[item_id], "explicit_item_id"
        for key in _RELATION_ID_FIELDS:
            relation_id = str(row.get(key) or "").strip()
            if relation_id in self.rows_by_item_id:
                return self.rows_by_item_id[relation_id], f"persistent_relation:{key}"
        for key in _CODE_FIELDS:
            code = normalize_catalog_text(row.get(key))
            if code and code in self.rows_by_code:
                return self.rows_by_code[code], f"exact_{key}"
            comparison_key = normalize_physical_code_comparison_key(row.get(key))
            if comparison_key and comparison_key in self.rows_by_approved_comparison_key:
                return self.rows_by_approved_comparison_key[comparison_key], f"approved_leading_zero_{key}"
        base_code = normalize_catalog_text(row.get("base_item_code"))
        if base_code and base_code in self.rows_by_code:
            return self.rows_by_code[base_code], "repository_relation:base_item_code"
        comparison_key = normalize_physical_code_comparison_key(row.get("base_item_code"))
        if comparison_key and comparison_key in self.rows_by_approved_comparison_key:
            return self.rows_by_approved_comparison_key[comparison_key], "approved_leading_zero_base_item_code"
        return None, "unmapped"


def default_physical_catalog_snapshot_path() -> Path:
    return _physical_catalog_snapshot_configuration()[0]


def build_catalog_filter_bar(
    parent: tk.Misc,
    *,
    selection: CatalogFilterSelection,
    options: Mapping[str, list[str]],
    options_for_selection: Callable[[CatalogFilterSelection], Mapping[str, list[str]]] | None = None,
    on_selection_change: Callable[[CatalogFilterSelection], None],
    on_apply: Callable[[CatalogFilterSelection], None],
    on_clear: Callable[[], None],
    button_factory: Callable[..., tk.Widget],
    colors: Mapping[str, str],
) -> tk.Frame:
    """Build the compact shared hierarchy bar without mutating result data."""
    card = tk.Frame(parent, bg=colors["card"], highlightbackground=colors["line"], highlightthickness=1)
    card.pack(fill=tk.X, pady=(0, 12))
    inner = tk.Frame(card, bg=colors["card"])
    inner.pack(fill=tk.X, padx=14, pady=10)
    for column in range(4):
        inner.columnconfigure(column, weight=1)
    inner.columnconfigure(4, weight=2)

    labels = {
        "filter_family": "Familia",
        "filter_group": "Grupo",
        "filter_size": "Tamaño",
        "filter_gama": "Gama",
    }
    active_selection = selection
    combo_by_field: dict[str, ttk.Combobox] = {}
    value_var_by_field: dict[str, tk.StringVar] = {}
    filter_hosts: list[tk.Frame] = []

    def update_dependent_options(updated: CatalogFilterSelection, changed_field: str) -> None:
        if options_for_selection is None:
            return
        refreshed = options_for_selection(updated)
        changed_index = FILTER_FIELDS.index(changed_field)
        for field in FILTER_FIELDS[changed_index + 1:]:
            values = ["Todos", *(refreshed.get(field) or [])]
            combo_by_field[field].configure(values=values)
            value_var_by_field[field].set("Todos")

    def selection_changed(field: str, value_var: tk.StringVar) -> None:
        nonlocal active_selection
        active_selection = active_selection.with_filter(field, "" if value_var.get() == "Todos" else value_var.get())
        on_selection_change(active_selection)
        update_dependent_options(active_selection, field)

    for index, field in enumerate(FILTER_FIELDS):
        host = tk.Frame(inner, bg=colors["card"])
        filter_hosts.append(host)
        tk.Label(host, text=labels[field], bg=colors["card"], fg=colors["text"], font=("Segoe UI", 8, "bold")).pack(anchor=tk.W)
        current = getattr(selection, field)
        values = ["Todos", *(options.get(field) or [])]
        value_var = tk.StringVar(value=current or "Todos")
        combo = ttk.Combobox(host, state="readonly", textvariable=value_var, values=values, width=18)
        combo.pack(fill=tk.X, pady=(3, 0), ipady=3)
        combo_by_field[field] = combo
        value_var_by_field[field] = value_var
        combo.bind("<<ComboboxSelected>>", lambda _event, field=field, value_var=value_var: selection_changed(field, value_var))

    search_host = tk.Frame(inner, bg=colors["card"])
    tk.Label(search_host, text="Buscar código o nombre", bg=colors["card"], fg=colors["text"], font=("Segoe UI", 8, "bold")).pack(anchor=tk.W)
    query_var = tk.StringVar(value=selection.query)
    query_entry = tk.Entry(
        search_host,
        textvariable=query_var,
        bg=colors["card"],
        fg=colors["text"],
        insertbackground=colors["text"],
        relief=tk.FLAT,
        highlightbackground=colors["line"],
        highlightcolor=colors["indigo"],
        highlightthickness=1,
        font=("Segoe UI", 9),
    )
    query_entry.pack(fill=tk.X, pady=(3, 0), ipady=5)
    query_entry.bind("<Return>", lambda _event: on_apply(active_selection.with_query(query_var.get())))

    button_host = tk.Frame(inner, bg=colors["card"])
    button_factory(button_host, "Aplicar filtros", primary=True, command=lambda: on_apply(active_selection.with_query(query_var.get()))).pack(side=tk.LEFT, padx=(0, 6))
    button_factory(button_host, "Limpiar", command=on_clear).pack(side=tk.LEFT)

    layout_state = {"key": None}

    def apply_responsive_layout(width: int) -> None:
        layout = catalog_filter_bar_layout(width)
        key = (
            layout.filter_columns,
            layout.search_row,
            layout.search_column,
            layout.search_columnspan,
            layout.button_row,
            layout.button_column,
            layout.button_columnspan,
        )
        if key == layout_state["key"]:
            return
        layout_state["key"] = key
        for column in range(6):
            inner.columnconfigure(column, weight=0)
        for child in (*filter_hosts, search_host, button_host):
            child.grid_forget()
        for index, host in enumerate(filter_hosts):
            row = index // layout.filter_columns
            column = index % layout.filter_columns
            inner.columnconfigure(column, weight=1)
            host.grid(row=row, column=column, sticky="ew", padx=(0, 8), pady=(0, 8))
        for column in range(layout.search_column, layout.search_column + layout.search_columnspan):
            inner.columnconfigure(column, weight=2 if column == layout.search_column else 1)
        search_host.grid(
            row=layout.search_row,
            column=layout.search_column,
            columnspan=layout.search_columnspan,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 8),
        )
        button_host.grid(
            row=layout.button_row,
            column=layout.button_column,
            columnspan=layout.button_columnspan,
            sticky="e",
            padx=(0, 0),
            pady=(0, 8),
        )

    apply_responsive_layout(0)
    inner.bind("<Configure>", lambda event: apply_responsive_layout(event.width))
    return card

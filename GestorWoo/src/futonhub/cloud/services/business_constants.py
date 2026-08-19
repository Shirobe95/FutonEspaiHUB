from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Iterable
from typing import Any

from futonhub.cloud.audit import AuditEvent, OperationSnapshot, new_operation_id, write_audit_event, write_snapshot


DEFAULT_BUSINESS_CONSTANTS: dict[str, dict[str, Any]] = {
    "IMPORTE_DESCARGA_MT": {"value": 12.0, "unit": "EUR/m", "description": "Importe descarga por metro"},
    "PC_GASTOS_MANIPULACION": {"value": 2.0, "unit": "%", "description": "Porcentaje manipulacion"},
    "PC_GASTOS_FINANCIACION": {"value": 2.5, "unit": "%", "description": "Porcentaje financiacion"},
    "IMPORTES_VARIOS": {"value": 1.0, "unit": "%", "description": "Importes varios"},
    "COSTE_TOTAL_DESCARGA_FUTONES_IVA": {"value": 326.0, "unit": "EUR", "description": "Descarga futones con IVA"},
    "IVA_RECARGO_EQUIVALENCIA": {"value": 26.2, "unit": "%", "description": "IVA + recargo equivalencia"},
    "COSTE_DIARIO_ALMACENAJE_M3": {"value": 0.15, "unit": "EUR/m3", "description": "Almacenaje diario por M3"},
    "PRICE_DROP_BLOCK_PERCENT": {"value": 30.0, "unit": "%", "description": "Bajada maxima de precio antes de bloquear"},
}

SUPPLIER_ORDER_GENERAL_REQUIRED_CONSTANTS: tuple[str, ...] = (
    "COSTE_TOTAL_DESCARGA_FUTONES_IVA",
    "IVA_RECARGO_EQUIVALENCIA",
    "COSTE_DIARIO_ALMACENAJE_M3",
)

SUPPLIER_ORDER_IMPORT_USD_EUR_REQUIRED_CONSTANTS: tuple[str, ...] = (
    "IMPORTE_DESCARGA_MT",
    "IMPORTES_VARIOS",
    "PC_GASTOS_MANIPULACION",
    "PC_GASTOS_FINANCIACION",
    "COSTE_DIARIO_ALMACENAJE_M3",
)

SUPPLIER_ORDER_REQUIRED_CONSTANTS_BY_MODE: dict[str, tuple[str, ...]] = {
    "general": SUPPLIER_ORDER_GENERAL_REQUIRED_CONSTANTS,
    "import_usd_eur": SUPPLIER_ORDER_IMPORT_USD_EUR_REQUIRED_CONSTANTS,
}


class BusinessConstantsValidationError(RuntimeError):
    """Raised when economic constants from Supabase are incomplete or invalid."""

    def __init__(
        self,
        message: str,
        *,
        missing_keys: Iterable[str] = (),
        invalid_keys: Iterable[str] = (),
    ) -> None:
        self.missing_keys = tuple(missing_keys)
        self.invalid_keys = tuple(invalid_keys)
        details = []
        if self.missing_keys:
            details.append("missing_keys=" + ",".join(self.missing_keys))
        if self.invalid_keys:
            details.append("invalid_keys=" + ",".join(self.invalid_keys))
        super().__init__(message + (f" ({'; '.join(details)})" if details else ""))


def supplier_order_required_business_constant_keys(calculation_mode: str) -> tuple[str, ...]:
    return SUPPLIER_ORDER_REQUIRED_CONSTANTS_BY_MODE.get(
        calculation_mode,
        SUPPLIER_ORDER_GENERAL_REQUIRED_CONSTANTS,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def _strict_float(value: Any) -> float:
    if value is None or value == "":
        raise ValueError("empty")
    text = str(value).replace(",", ".").strip()
    if not text:
        raise ValueError("empty")
    return float(text)


def _row_key(row: dict[str, Any]) -> str:
    return str(row.get("key") or row.get("name") or row.get("constant_key") or "").strip()


def _value_from_row(row: dict[str, Any]) -> Any:
    for key in ("value", "numeric_value", "constant_value", "valor"):
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    source = row.get("source_row")
    if isinstance(source, dict):
        for key in ("value", "numeric_value", "constant_value", "valor"):
            if source.get(key) not in (None, ""):
                return source.get(key)
    return None


def load_required_business_constants(session, required_keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Lee constantes economicas obligatorias sin fallback silencioso a defaults."""
    required = tuple(dict.fromkeys(str(key).strip() for key in required_keys if str(key).strip()))
    result = {key: dict(value) for key, value in DEFAULT_BUSINESS_CONSTANTS.items()}
    try:
        response = session.client.table("business_constants").select("*").execute()
        rows = getattr(response, "data", None) or []
    except Exception as exc:
        raise BusinessConstantsValidationError("No se pudieron leer business_constants desde Supabase.") from exc

    if not rows:
        raise BusinessConstantsValidationError(
            "Supabase no devolvio constantes de negocio.",
            missing_keys=required,
        )

    seen_required: set[str] = set()
    invalid: list[str] = []
    for row in rows:
        key = _row_key(row)
        if not key:
            continue
        base = result.setdefault(key, {"value": 0.0, "unit": "", "description": key})
        value = _value_from_row(row)
        if key in required:
            seen_required.add(key)
            try:
                base["value"] = _strict_float(value)
            except Exception:
                invalid.append(key)
                continue
        elif value not in (None, ""):
            base["value"] = _safe_float(value)
        if row.get("unit") not in (None, ""):
            base["unit"] = row.get("unit")
        if row.get("description") not in (None, ""):
            base["description"] = row.get("description")
        base["source_row"] = row

    missing = [key for key in required if key not in seen_required]
    invalid_unique = list(dict.fromkeys(invalid))
    if missing or invalid_unique:
        raise BusinessConstantsValidationError(
            "Supabase devolvio constantes de negocio incompletas o invalidas.",
            missing_keys=missing,
            invalid_keys=invalid_unique,
        )
    return result


def list_business_constants(
    session,
    *,
    raise_on_error: bool = False,
    required_keys: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Lee business_constants de Supabase.

    Tolera varios esquemas: value/numeric_value/constant_value/source_row.
    Si no hay filas visibles, devuelve defaults locales.
    """
    if required_keys is not None:
        return load_required_business_constants(session, required_keys)

    result = {key: dict(value) for key, value in DEFAULT_BUSINESS_CONSTANTS.items()}
    try:
        response = session.client.table("business_constants").select("*").execute()
        rows = getattr(response, "data", None) or []
    except Exception:
        if raise_on_error:
            raise
        return result

    for row in rows:
        key = _row_key(row)
        if not key:
            continue
        base = result.setdefault(key, {"value": 0.0, "unit": "", "description": key})
        value = _value_from_row(row)
        if value not in (None, ""):
            base["value"] = _safe_float(value)
        if row.get("unit") not in (None, ""):
            base["unit"] = row.get("unit")
        if row.get("description") not in (None, ""):
            base["description"] = row.get("description")
        base["source_row"] = row
    return result


def _strip_missing_schema_columns(payload: list[dict[str, Any]], error_text: str) -> tuple[list[dict[str, Any]], bool]:
    """Remove optional columns that Supabase says do not exist.

    The real `business_constants` table in production may be leaner than the
    development schema. We must not fail just because optional metadata columns
    like `source_row` or `updated_at` are missing.
    """
    text = str(error_text or "")
    removed = False
    optional_columns = ("source_row", "updated_at", "unit", "description")
    for column in optional_columns:
        if column in text:
            for row in payload:
                if column in row:
                    row.pop(column, None)
                    removed = True
    return payload, removed


def _upsert_business_constants_schema_safe(session, payload: list[dict[str, Any]]) -> None:
    """Upsert constants while tolerating optional columns absent from Supabase."""
    current_payload = [dict(row) for row in payload]
    attempted_messages: list[str] = []
    for _ in range(5):
        try:
            session.client.table("business_constants").upsert(current_payload, on_conflict="key").execute()
            return
        except Exception as exc:
            message = str(exc)
            attempted_messages.append(message)
            current_payload, removed = _strip_missing_schema_columns(current_payload, message)
            if removed:
                continue
            # Some Supabase schemas may not have a unique constraint/cache for
            # on_conflict="key". Fallback: update existing row by key, insert only
            # if update returns no data. This avoids relying on optional indexes.
            if "on conflict" in message.lower() or "unique" in message.lower() or "schema cache" in message.lower():
                break
            raise

    # Fallback update/insert minimal payload. We still avoid source_row/metadata.
    for row in current_payload:
        key = row.get("key")
        if not key:
            continue
        minimal = dict(row)
        for optional in ("source_row", "updated_at"):
            minimal.pop(optional, None)
        try:
            response = session.client.table("business_constants").update(minimal).eq("key", key).execute()
            data = getattr(response, "data", None) or []
            if data:
                continue
            session.client.table("business_constants").insert(minimal).execute()
        except Exception as exc:
            raise RuntimeError("; ".join(attempted_messages + [str(exc)]))


def save_business_constants(session, values: dict[str, Any]) -> dict[str, Any]:
    """Guarda constantes en Supabase con tolerancia al esquema real.

    La tabla real puede no tener `source_row`. Si falta, guardamos solo columnas
    esenciales: `key`, `value`, `unit`, `description`, `updated_at` cuando existan.
    """
    operation_id = new_operation_id("business_constants_update")
    before = {}
    try:
        before = list_business_constants(session)
    except Exception:
        before = {}

    now = _now_iso()
    payload: list[dict[str, Any]] = []
    defaults = DEFAULT_BUSINESS_CONSTANTS
    for key, raw_value in values.items():
        if key not in defaults:
            continue
        meta = defaults[key]
        payload.append(
            {
                "key": key,
                "value": _safe_float(raw_value),
                "unit": meta.get("unit", ""),
                "description": meta.get("description", key),
                "updated_at": now,
                "source_row": {
                    "updated_from": "UI ERP Configuracion",
                    "updated_by_email": session.email,
                    "operation_id": operation_id,
                },
            }
        )

    if not payload:
        raise ValueError("No hay constantes validas para guardar.")

    try:
        write_snapshot(
            session,
            OperationSnapshot(
                operation_id=operation_id,
                module="Configuracion",
                action="save_business_constants",
                entity_table="business_constants",
                entity_id="bulk",
                before_data=before,
                after_data={"values": payload},
                metadata={"count": len(payload)},
            ),
        )
    except Exception:
        pass

    _upsert_business_constants_schema_safe(session, payload)

    try:
        write_audit_event(
            session,
            AuditEvent(
                operation_id=operation_id,
                module="Configuracion",
                action="save_business_constants",
                entity_table="business_constants",
                entity_id="bulk",
                status="success",
                message=f"Constantes actualizadas desde UI ERP: {len(payload)}",
                metadata={"keys": [row["key"] for row in payload]},
            ),
        )
    except Exception:
        pass

    return {"operation_id": operation_id, "count": len(payload)}


def diagnose_business_constants_schema(session) -> dict[str, Any]:
    """Returns visible rows and inferred columns for business_constants."""
    try:
        response = session.client.table("business_constants").select("*").limit(20).execute()
        rows = getattr(response, "data", None) or []
    except Exception as exc:
        return {"ok": False, "error": str(exc), "rows": [], "columns": []}
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    return {"ok": True, "rows": rows, "columns": columns}

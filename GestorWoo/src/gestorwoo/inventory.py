from __future__ import annotations

import csv
import json
import re
import sqlite3
import zipfile
import threading
import tkinter as tk
import tkinter.font
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import openpyxl

from gestorwoo.config import Settings
from gestorwoo.theme import C_BG, C_PANEL, C_PANEL_LINE, apply_theme


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEL_PATH = ROOT.parent / "CalculoCoste" / "data.xlsx"
SUPPLIERS = ("Ekomat", "Pascal", "Hemei", "Cipta")


def _safe_security_log(db_path: Path, **kwargs: object) -> None:
    try:
        from gestorwoo.security import log_event
        log_event(db_path, **kwargs)
    except Exception:
        pass


MASTER_EXTRA_COLUMNS = {
    "order_calculated_price": "REAL",
    "weighted_average_cost": "REAL",
    "weighted_average_cost_updated_at": "TEXT",
    "family": "TEXT",
    "subgroup": "TEXT",
    "size": "TEXT",
    "materials": "TEXT",
    "commercial_status": "TEXT DEFAULT 'Normal'",
    "is_pack": "INTEGER DEFAULT 0",
    "store_stock": "REAL",
    "warehouse_stock": "REAL",
    "supplier_order_qty": "REAL",
    "supplier_order_provider": "TEXT",
    "supplier_order_file": "TEXT",
    "supplier_order_updated_at": "TEXT",
    "heca_reference": "TEXT",
    "notes": "TEXT",
    "woo_item_kind": "TEXT",
    "woo_id": "INTEGER",
    "woo_parent_id": "INTEGER",
    "woo_sku": "TEXT",
    "woo_name": "TEXT",
    "woo_type": "TEXT",
    "woo_price": "TEXT",
    "woo_categories": "TEXT",
    "woo_link_status": "TEXT DEFAULT 'Sin enlazar'",
    "woo_link_notes": "TEXT",
    "woo_synced_at": "TEXT",
}


@dataclass(frozen=True)
class WooLinkResult:
    total_inventory: int = 0
    linked: int = 0
    missing: int = 0
    conflicts: int = 0
    woo_without_inventory: int = 0
    details: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HecaImportResult:
    warehouses: int = 0
    stock_rows: int = 0
    stock_rows_nonzero: int = 0
    matched_inventory: int = 0
    unmatched_heca_codes: int = 0
    total_store_stock: float = 0.0
    total_warehouse_stock: float = 0.0



INVENTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_items (
    item_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    cubic_meters REAL,
    rotation_c REAL,
    packages INTEGER,
    primary_supplier_price TEXT,
    pascal_price TEXT,
    order_calculated_price REAL,
    weighted_average_cost REAL,
    weighted_average_cost_updated_at TEXT,
    family TEXT,
    subgroup TEXT,
    size TEXT,
    materials TEXT,
    commercial_status TEXT DEFAULT 'Normal',
    is_pack INTEGER DEFAULT 0,
    store_stock REAL,
    warehouse_stock REAL,
    supplier_order_qty REAL,
    supplier_order_provider TEXT,
    supplier_order_file TEXT,
    supplier_order_updated_at TEXT,
    heca_reference TEXT,
    notes TEXT,
    woo_item_kind TEXT,
    woo_id INTEGER,
    woo_parent_id INTEGER,
    woo_sku TEXT,
    woo_name TEXT,
    woo_type TEXT,
    woo_price TEXT,
    woo_categories TEXT,
    woo_link_status TEXT DEFAULT 'Sin enlazar',
    woo_link_notes TEXT,
    woo_synced_at TEXT,
    source TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventory_name ON inventory_items(name);


CREATE TABLE IF NOT EXISTS supplier_prices (
    item_id INTEGER NOT NULL,
    supplier TEXT NOT NULL,
    price TEXT,
    currency TEXT DEFAULT 'EUR',
    source TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(item_id, supplier),
    FOREIGN KEY(item_id) REFERENCES inventory_items(item_id)
);

CREATE INDEX IF NOT EXISTS idx_supplier_prices_item
ON supplier_prices(item_id, supplier);

CREATE TABLE IF NOT EXISTS heca_warehouses (
    code INTEGER PRIMARY KEY,
    planta TEXT,
    name TEXT,
    address TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS heca_stock (
    item_code TEXT NOT NULL,
    normalized_code TEXT NOT NULL,
    warehouse_code INTEGER NOT NULL,
    quantity REAL DEFAULT 0,
    quantity_requested REAL DEFAULT 0,
    quantity_reserved REAL DEFAULT 0,
    quantity_supplier_ordered REAL DEFAULT 0,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(normalized_code, warehouse_code)
);

CREATE INDEX IF NOT EXISTS idx_heca_stock_code
ON heca_stock(normalized_code);

CREATE TABLE IF NOT EXISTS supplier_pending_order_items (
    provider TEXT NOT NULL,
    order_file TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    quantity REAL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(provider, order_file, item_id)
);

CREATE INDEX IF NOT EXISTS idx_supplier_pending_order_item
ON supplier_pending_order_items(item_id);

CREATE TABLE IF NOT EXISTS supplier_orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    order_file TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pendiente',
    total_items REAL DEFAULT 0,
    total_cost REAL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, order_file)
);

CREATE TABLE IF NOT EXISTS supplier_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    item_name TEXT,
    quantity_ordered REAL DEFAULT 0,
    quantity_received REAL DEFAULT 0,
    unit_cost REAL DEFAULT 0,
    line_cost REAL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(order_id) REFERENCES supplier_orders(order_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_supplier_order_items_order
ON supplier_order_items(order_id);

CREATE INDEX IF NOT EXISTS idx_supplier_order_items_item
ON supplier_order_items(item_id);


CREATE TABLE IF NOT EXISTS inventory_change_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_source TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(item_id) REFERENCES inventory_items(item_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_history_item
ON inventory_change_history(item_id, created_at);

CREATE INDEX IF NOT EXISTS idx_inventory_history_field
ON inventory_change_history(field_name);
"""


@dataclass(frozen=True)
class InventoryImportResult:
    rows_read: int
    stored: int
    source: Path


class InventoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(INVENTORY_SCHEMA)
            self._ensure_master_columns(connection)
            self._migrate_legacy_supplier_prices(connection)

    def _ensure_master_columns(self, connection: sqlite3.Connection) -> None:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(inventory_items)")}
        for column, column_type in MASTER_EXTRA_COLUMNS.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE inventory_items ADD COLUMN {column} {column_type}")

    def _infer_primary_supplier(self, item: dict[str, object] | sqlite3.Row) -> str:
        text = " ".join(
            str(item.get(key) if hasattr(item, "get") else item[key] if key in item.keys() else "")
            for key in ("family", "name", "materials", "woo_categories")
        ).lower()
        if "tatami" in text:
            return "Hemei"
        if "cama" in text or "sofa" in text or "sofá" in text:
            return "Cipta"
        return "Ekomat"

    def _upsert_supplier_price(
        self,
        connection: sqlite3.Connection,
        item_id: int,
        supplier: str,
        price: object,
        source: str,
        currency: str = "EUR",
    ) -> None:
        clean_price = self._clean_price(price)
        if clean_price in (None, "", "NO ESTA"):
            return
        if supplier not in SUPPLIERS:
            return
        connection.execute(
            """
            INSERT INTO supplier_prices (item_id, supplier, price, currency, source, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(item_id, supplier) DO UPDATE SET
                price = excluded.price,
                currency = excluded.currency,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(item_id), supplier, str(clean_price), currency, source),
        )

    def _migrate_legacy_supplier_prices(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT item_id, name, family, materials, woo_categories,
                   primary_supplier_price, pascal_price
            FROM inventory_items
            """
        ).fetchall()
        for row in rows:
            primary_supplier = self._infer_primary_supplier(dict(row))
            self._upsert_supplier_price(
                connection,
                int(row["item_id"]),
                primary_supplier,
                row["primary_supplier_price"],
                "Migrado desde Precio 1",
            )
            self._upsert_supplier_price(
                connection,
                int(row["item_id"]),
                "Pascal",
                row["pascal_price"],
                "Migrado desde Precio 2",
            )

    def get_supplier_prices(self, item_id: int) -> dict[str, str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT supplier, price FROM supplier_prices WHERE item_id = ?",
                (int(item_id),),
            ).fetchall()
        return {str(row["supplier"]): str(row["price"] or "") for row in rows}

    def get_supplier_price(self, item_id: int, supplier: str) -> str:
        if supplier not in SUPPLIERS:
            return ""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT price FROM supplier_prices WHERE item_id = ? AND supplier = ?",
                (int(item_id), supplier),
            ).fetchone()
        return str(row["price"] or "") if row else ""

    def update_supplier_prices(self, item_id: int, prices: dict[str, object], source: str = "manual") -> None:
        with self.connect() as connection:
            for supplier, price in prices.items():
                clean_price = self._clean_price(price)
                if clean_price in (None, "", "NO ESTA"):
                    connection.execute(
                        "DELETE FROM supplier_prices WHERE item_id = ? AND supplier = ?",
                        (int(item_id), supplier),
                    )
                else:
                    self._upsert_supplier_price(connection, int(item_id), supplier, clean_price, source)

    def confirm_supplier_reception(self, item_id: int) -> dict[str, object]:
        """Confirma la recepción del pedido pendiente de un artículo.

        Actualiza solo el Mapa Maestro local:
        - añade unidades recibidas al stock de almacenes,
        - recalcula coste promedio ponderado,
        - limpia el pedido proveedor pendiente del artículo.
        """
        with self.connect() as connection:
            self._ensure_master_columns(connection)
            row = self._get_item(connection, int(item_id))
            if row is None:
                raise ValueError("No se encontró el artículo en el Mapa Maestro.")
            qty = self._to_float(row["supplier_order_qty"] if "supplier_order_qty" in row.keys() else 0)
            last_cost = self._to_float(row["order_calculated_price"] if "order_calculated_price" in row.keys() else 0)
            if qty <= 0:
                raise ValueError("El artículo no tiene pedido proveedor pendiente.")
            if last_cost <= 0:
                raise ValueError("El artículo no tiene Último coste pedido válido.")
            store_stock = self._to_float(row["store_stock"] if "store_stock" in row.keys() else 0)
            warehouse_stock = self._to_float(row["warehouse_stock"] if "warehouse_stock" in row.keys() else 0)
            old_stock = store_stock + warehouse_stock
            old_average = self._to_float(row["weighted_average_cost"] if "weighted_average_cost" in row.keys() else 0)
            if old_stock > 0 and old_average > 0:
                new_average = ((old_stock * old_average) + (qty * last_cost)) / (old_stock + qty)
            else:
                new_average = last_cost
            new_warehouse_stock = warehouse_stock + qty
            current = dict(row)
            new_values = dict(current)
            new_values.update({
                "warehouse_stock": new_warehouse_stock,
                "weighted_average_cost": new_average,
                "supplier_order_qty": None,
                "supplier_order_provider": None,
                "supplier_order_file": None,
                "supplier_order_updated_at": None,
            })
            connection.execute(
                """
                UPDATE inventory_items
                SET warehouse_stock = ?,
                    weighted_average_cost = ?,
                    weighted_average_cost_updated_at = CURRENT_TIMESTAMP,
                    supplier_order_qty = NULL,
                    supplier_order_provider = NULL,
                    supplier_order_file = NULL,
                    supplier_order_updated_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
                """,
                (new_warehouse_stock, new_average, int(item_id)),
            )
            connection.execute(
                "DELETE FROM supplier_pending_order_items WHERE item_id = ?",
                (int(item_id),),
            )
            self._record_history(
                connection,
                current=current,
                new_values=new_values,
                source="recepcion proveedor",
                notes="Recepción confirmada desde Mapa Maestro",
            )
            connection.commit()
        _safe_security_log(
            self.db_path,
            module="Mapa Maestro",
            action="Confirmar recepción de proveedor",
            status="OK",
            entity_type="Articulo",
            entity_id=str(item_id),
            details=(
                f"Recepción confirmada. Unidades recibidas: {qty}. "
                f"Coste pedido: {last_cost:.4f}. Nuevo coste promedio: {new_average:.4f}."
            ),
            context={
                "item_id": int(item_id),
                "unidades_recibidas": qty,
                "stock_anterior": old_stock,
                "stock_almacenes_anterior": warehouse_stock,
                "stock_almacenes_nuevo": new_warehouse_stock,
                "coste_pedido": last_cost,
                "coste_promedio_anterior": old_average,
                "coste_promedio_nuevo": new_average,
            },
            category="Mapa Maestro",
        )
        return {
            "item_id": int(item_id),
            "quantity": qty,
            "old_stock": old_stock,
            "new_warehouse_stock": new_warehouse_stock,
            "old_average": old_average,
            "new_average": new_average,
        }



    def _ensure_supplier_order_tables(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS supplier_orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                order_file TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pendiente',
                total_items REAL DEFAULT 0,
                total_cost REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, order_file)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS supplier_order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
                item_name TEXT,
                quantity_ordered REAL DEFAULT 0,
                quantity_received REAL DEFAULT 0,
                unit_cost REAL DEFAULT 0,
                line_cost REAL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(order_id) REFERENCES supplier_orders(order_id) ON DELETE CASCADE
            )
            """
        )

    def recalc_supplier_order_totals(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        if connection is None:
            connection = self.connect()
        try:
            self._ensure_master_columns(connection)
            self._ensure_supplier_order_tables(connection)
            connection.execute(
                """
                UPDATE inventory_items
                SET supplier_order_qty = NULL,
                    supplier_order_provider = NULL,
                    supplier_order_file = NULL,
                    supplier_order_updated_at = NULL
                """
            )
            rows = connection.execute(
                """
                SELECT
                    soi.item_id,
                    SUM(MAX(soi.quantity_ordered - COALESCE(soi.quantity_received, 0), 0)) AS pending_qty,
                    GROUP_CONCAT(DISTINCT so.provider) AS providers,
                    GROUP_CONCAT(DISTINCT so.order_file) AS files
                FROM supplier_order_items AS soi
                JOIN supplier_orders AS so ON so.order_id = soi.order_id
                WHERE so.status NOT IN ('Recibido', 'Cancelado')
                GROUP BY soi.item_id
                """
            ).fetchall()
            for row in rows:
                pending_qty = self._to_float(row["pending_qty"])
                if pending_qty <= 0:
                    continue
                connection.execute(
                    """
                    UPDATE inventory_items
                    SET supplier_order_qty = ?,
                        supplier_order_provider = ?,
                        supplier_order_file = ?,
                        supplier_order_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (pending_qty, row["providers"], row["files"], int(row["item_id"])),
                )
            if owns_connection:
                connection.commit()
        finally:
            if owns_connection:
                connection.close()

    def list_supplier_orders(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            return list(connection.execute(
                """
                SELECT
                    so.order_id,
                    so.provider,
                    so.order_file,
                    so.status,
                    so.total_items,
                    so.total_cost,
                    so.notes,
                    so.created_at,
                    so.updated_at,
                    COALESCE(SUM(MAX(soi.quantity_ordered - COALESCE(soi.quantity_received, 0), 0)), 0) AS pending_qty,
                    COUNT(soi.id) AS lines
                FROM supplier_orders AS so
                LEFT JOIN supplier_order_items AS soi ON soi.order_id = so.order_id
                GROUP BY so.order_id
                ORDER BY so.updated_at DESC, so.order_id DESC
                """
            ))

    def list_supplier_order_items(self, order_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            return list(connection.execute(
                """
                SELECT
                    soi.id,
                    soi.order_id,
                    soi.item_id,
                    soi.item_code,
                    soi.item_name,
                    soi.quantity_ordered,
                    soi.quantity_received,
                    MAX(soi.quantity_ordered - COALESCE(soi.quantity_received, 0), 0) AS pending_qty,
                    soi.unit_cost,
                    soi.line_cost,
                    inv.store_stock,
                    inv.warehouse_stock,
                    inv.weighted_average_cost,
                    inv.order_calculated_price
                FROM supplier_order_items AS soi
                LEFT JOIN inventory_items AS inv ON inv.item_id = soi.item_id
                WHERE soi.order_id = ?
                ORDER BY soi.item_id
                """,
                (int(order_id),),
            ))

    def update_supplier_order_line(self, line_id: int, quantity_ordered: float, unit_cost: float) -> None:
        quantity_ordered = max(self._to_float(quantity_ordered), 0.0)
        unit_cost = max(self._to_float(unit_cost), 0.0)
        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            row = connection.execute(
                "SELECT order_id, quantity_received FROM supplier_order_items WHERE id = ?",
                (int(line_id),),
            ).fetchone()
            if row is None:
                raise ValueError("No se encontró la línea del pedido.")
            received = min(self._to_float(row["quantity_received"]), quantity_ordered)
            connection.execute(
                """
                UPDATE supplier_order_items
                SET quantity_ordered = ?,
                    quantity_received = ?,
                    unit_cost = ?,
                    line_cost = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (quantity_ordered, received, unit_cost, round(quantity_ordered * unit_cost, 4), int(line_id)),
            )
            order_id_for_log = int(row["order_id"])
            old_received_for_log = self._to_float(row["quantity_received"])
            self._refresh_supplier_order_header(connection, order_id_for_log)
            self.recalc_supplier_order_totals(connection)
            connection.commit()
        _safe_security_log(
            self.db_path,
            module="Pedidos de Proveedor",
            action="Modificar línea de pedido",
            status="OK",
            entity_type="Pedido proveedor",
            entity_id=str(order_id_for_log),
            details=f"Línea modificada. Cantidad pedida: {quantity_ordered:g}. Coste unitario: {unit_cost:.4f}.",
            context={
                "order_id": order_id_for_log,
                "line_id": int(line_id),
                "quantity_ordered": quantity_ordered,
                "quantity_received": old_received_for_log,
                "unit_cost": unit_cost,
                "line_cost": round(quantity_ordered * unit_cost, 4),
            },
            category="Pedidos de Proveedores",
        )

    def _refresh_supplier_order_header(self, connection: sqlite3.Connection, order_id: int) -> None:
        totals = connection.execute(
            """
            SELECT SUM(quantity_ordered) AS total_items, SUM(line_cost) AS total_cost
            FROM supplier_order_items
            WHERE order_id = ?
            """,
            (int(order_id),),
        ).fetchone()
        pending = connection.execute(
            """
            SELECT SUM(MAX(quantity_ordered - COALESCE(quantity_received, 0), 0)) AS pending_qty
            FROM supplier_order_items
            WHERE order_id = ?
            """,
            (int(order_id),),
        ).fetchone()
        pending_qty = self._to_float(pending["pending_qty"] if pending else 0)
        status = "Recibido" if pending_qty <= 0 else "Pendiente"
        connection.execute(
            """
            UPDATE supplier_orders
            SET total_items = ?, total_cost = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            (self._to_float(totals["total_items"] if totals else 0), self._to_float(totals["total_cost"] if totals else 0), status, int(order_id)),
        )

    def confirm_supplier_order_receipt(self, order_id: int) -> dict[str, object]:
        """Confirma la recepción total pendiente de un pedido de proveedor."""
        received_lines: list[dict[str, object]] = []
        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            order = connection.execute(
                "SELECT * FROM supplier_orders WHERE order_id = ?",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("No se encontró el pedido de proveedor.")
            if order["status"] in ("Recibido", "Cancelado"):
                raise ValueError(f"El pedido ya está en estado {order['status']}.")
            rows = connection.execute(
                """
                SELECT soi.*, inv.name, inv.store_stock, inv.warehouse_stock, inv.weighted_average_cost, inv.order_calculated_price
                FROM supplier_order_items AS soi
                LEFT JOIN inventory_items AS inv ON inv.item_id = soi.item_id
                WHERE soi.order_id = ?
                """,
                (int(order_id),),
            ).fetchall()
            for row in rows:
                pending_qty = max(self._to_float(row["quantity_ordered"]) - self._to_float(row["quantity_received"]), 0.0)
                if pending_qty <= 0:
                    continue
                unit_cost = self._to_float(row["unit_cost"])
                if unit_cost <= 0:
                    unit_cost = self._to_float(row["order_calculated_price"])
                if unit_cost <= 0:
                    raise ValueError(f"La línea {row['item_code']} no tiene coste válido para ponderar.")
                stock_store = self._to_float(row["store_stock"])
                stock_wh = self._to_float(row["warehouse_stock"])
                old_stock = stock_store + stock_wh
                old_avg = self._to_float(row["weighted_average_cost"])
                if old_stock > 0 and old_avg > 0:
                    new_avg = ((old_stock * old_avg) + (pending_qty * unit_cost)) / (old_stock + pending_qty)
                else:
                    new_avg = unit_cost
                new_wh = stock_wh + pending_qty
                item_current = self._get_item(connection, int(row["item_id"]))
                current_dict = dict(item_current) if item_current is not None else {}
                new_values = dict(current_dict)
                new_values.update({
                    "warehouse_stock": new_wh,
                    "weighted_average_cost": new_avg,
                    "supplier_order_qty": None,
                })
                connection.execute(
                    """
                    UPDATE inventory_items
                    SET warehouse_stock = ?,
                        weighted_average_cost = ?,
                        weighted_average_cost_updated_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (new_wh, new_avg, int(row["item_id"])),
                )
                connection.execute(
                    "UPDATE supplier_order_items SET quantity_received = quantity_ordered, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (int(row["id"]),),
                )
                if current_dict:
                    self._record_history(
                        connection,
                        current=current_dict,
                        new_values=new_values,
                        source="recepcion pedido proveedor",
                        notes=f"Recepción del pedido {order['provider']} · {order['order_file']}",
                    )
                received_lines.append({
                    "codigo": row["item_code"],
                    "nombre": row["item_name"] or row["name"],
                    "recibido": pending_qty,
                    "coste_unitario": unit_cost,
                    "stock_anterior": old_stock,
                    "stock_nuevo": old_stock + pending_qty,
                    "coste_promedio_anterior": old_avg,
                    "coste_promedio_nuevo": new_avg,
                })
            if not received_lines:
                raise ValueError("El pedido no tiene unidades pendientes por recibir.")
            connection.execute(
                "UPDATE supplier_orders SET status = 'Recibido', updated_at = CURRENT_TIMESTAMP WHERE order_id = ?",
                (int(order_id),),
            )
            self.recalc_supplier_order_totals(connection)
            connection.commit()
        _safe_security_log(
            self.db_path,
            module="Pedidos de Proveedor",
            action="Confirmar recepción de pedido",
            status="OK",
            entity_type="Pedido proveedor",
            entity_id=str(order_id),
            details=f"Recepción confirmada. Líneas recibidas: {len(received_lines)}.",
            context={"order_id": int(order_id), "items": received_lines},
            category="Pedidos de Proveedores",
        )
        return {"order_id": int(order_id), "received_lines": received_lines}


    def confirm_supplier_order_line_receipt(self, line_id: int, quantity_received_now: float) -> dict[str, object]:
        """Confirma una recepción parcial de una línea de pedido proveedor.

        Solo suma la cantidad indicada al stock local y recalcula el coste promedio
        ponderado para esa cantidad recibida. No toca WooCommerce ni Heca.
        """
        received_info: dict[str, object] = {}
        qty_now = self._to_float(quantity_received_now)
        if qty_now <= 0:
            raise ValueError("La cantidad recibida debe ser mayor que 0.")

        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            row = connection.execute(
                """
                SELECT
                    soi.*,
                    so.provider,
                    so.order_file,
                    so.status AS order_status,
                    inv.name,
                    inv.store_stock,
                    inv.warehouse_stock,
                    inv.weighted_average_cost,
                    inv.order_calculated_price
                FROM supplier_order_items AS soi
                JOIN supplier_orders AS so ON so.order_id = soi.order_id
                LEFT JOIN inventory_items AS inv ON inv.item_id = soi.item_id
                WHERE soi.id = ?
                """,
                (int(line_id),),
            ).fetchone()
            if row is None:
                raise ValueError("No se encontró la línea del pedido.")
            if row["order_status"] in ("Recibido", "Cancelado"):
                raise ValueError(f"El pedido ya está en estado {row['order_status']}.")

            ordered = self._to_float(row["quantity_ordered"])
            previously_received = self._to_float(row["quantity_received"])
            pending = max(ordered - previously_received, 0.0)
            if pending <= 0:
                raise ValueError("Esta línea no tiene unidades pendientes por recibir.")
            if qty_now > pending:
                raise ValueError(f"No puedes recibir {qty_now:g}; solo quedan pendientes {pending:g}.")

            unit_cost = self._to_float(row["unit_cost"])
            if unit_cost <= 0:
                unit_cost = self._to_float(row["order_calculated_price"])
            if unit_cost <= 0:
                raise ValueError(f"La línea {row['item_code']} no tiene coste válido para ponderar.")

            stock_store = self._to_float(row["store_stock"])
            stock_wh = self._to_float(row["warehouse_stock"])
            old_stock = stock_store + stock_wh
            old_avg = self._to_float(row["weighted_average_cost"])
            if old_stock > 0 and old_avg > 0:
                new_avg = ((old_stock * old_avg) + (qty_now * unit_cost)) / (old_stock + qty_now)
            else:
                new_avg = unit_cost
            new_wh = stock_wh + qty_now
            new_received_total = previously_received + qty_now

            item_current = self._get_item(connection, int(row["item_id"]))
            current_dict = dict(item_current) if item_current is not None else {}
            new_values = dict(current_dict)
            new_values.update({
                "warehouse_stock": new_wh,
                "weighted_average_cost": new_avg,
            })

            connection.execute(
                """
                UPDATE inventory_items
                SET warehouse_stock = ?,
                    weighted_average_cost = ?,
                    weighted_average_cost_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
                """,
                (new_wh, new_avg, int(row["item_id"])),
            )
            connection.execute(
                """
                UPDATE supplier_order_items
                SET quantity_received = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_received_total, int(line_id)),
            )
            self._refresh_supplier_order_header(connection, int(row["order_id"]))
            self.recalc_supplier_order_totals(connection)

            if current_dict:
                self._record_history(
                    connection,
                    current=current_dict,
                    new_values=new_values,
                    source="recepcion parcial pedido proveedor",
                    notes=f"Recepción parcial del pedido {row['provider']} · {row['order_file']}",
                )
            connection.commit()

            received_info = {
                "order_id": int(row["order_id"]),
                "line_id": int(line_id),
                "codigo": row["item_code"],
                "nombre": row["item_name"] or row["name"],
                "proveedor": row["provider"],
                "archivo": row["order_file"],
                "pedido": ordered,
                "recibido_anterior": previously_received,
                "recibido_ahora": qty_now,
                "recibido_total": new_received_total,
                "pendiente_anterior": pending,
                "pendiente_nuevo": max(ordered - new_received_total, 0.0),
                "coste_unitario": unit_cost,
                "stock_anterior": old_stock,
                "stock_nuevo": old_stock + qty_now,
                "coste_promedio_anterior": old_avg,
                "coste_promedio_nuevo": new_avg,
            }

        _safe_security_log(
            self.db_path,
            module="Pedidos de Proveedor",
            action="Confirmar recepción parcial",
            status="OK",
            entity_type="Pedido proveedor",
            entity_id=str(received_info.get("order_id", "")),
            details=(
                f"Recepción parcial. Código {received_info.get('codigo')}: "
                f"{received_info.get('recibido_ahora')} unidades recibidas."
            ),
            context={"items": [received_info]},
            category="Pedidos de Proveedores",
        )
        return received_info

    def cancel_supplier_order(self, order_id: int) -> None:
        order_summary: dict[str, object] = {"order_id": int(order_id)}
        with self.connect() as connection:
            self._ensure_supplier_order_tables(connection)
            order = connection.execute("SELECT * FROM supplier_orders WHERE order_id = ?", (int(order_id),)).fetchone()
            if order is not None:
                order_summary.update(dict(order))
            connection.execute(
                "UPDATE supplier_orders SET status = 'Cancelado', updated_at = CURRENT_TIMESTAMP WHERE order_id = ?",
                (int(order_id),),
            )
            self.recalc_supplier_order_totals(connection)
            connection.commit()
        _safe_security_log(
            self.db_path,
            module="Pedidos de Proveedor",
            action="Cancelar pedido",
            status="OK",
            entity_type="Pedido proveedor",
            entity_id=str(order_id),
            details=f"Pedido de proveedor cancelado: {order_summary.get('provider', '')} · {order_summary.get('order_file', '')}",
            context=order_summary,
            category="Pedidos de Proveedores",
        )

    HECA_INACTIVE_WAREHOUSES = {
        "nadal",
        "amazon logistica",
        "amazon-logistica",
        "eduardo ruiz",
        "etasagrup",
        "flotante fabricante",
        "flotante zona franca",
    }

    def _normalize_heca_warehouse_label(self, *values: object) -> str:
        raw = " ".join(str(v or "") for v in values).strip().lower()
        raw = raw.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        raw = raw.replace("_", " ").replace("-", " ")
        return re.sub(r"\s+", " ", raw).strip()

    def _is_active_heca_warehouse(self, planta: object = "", name: object = "") -> bool:
        label = self._normalize_heca_warehouse_label(planta, name)
        compact = label.replace(" ", "")
        for inactive in self.HECA_INACTIVE_WAREHOUSES:
            norm = self._normalize_heca_warehouse_label(inactive)
            if norm in label or norm.replace(" ", "") in compact:
                return False
        return True

    def _display_heca_warehouse(self, planta: object = "", name: object = "", code: object = "") -> str:
        label = self._normalize_heca_warehouse_label(planta, name)
        if "almacen logistica" in label or "almacen logistica" in label.replace("á", "a"):
            return "TransNatur"
        clean_planta = self._clean_heca_text(planta)
        clean_name = self._clean_heca_text(name)
        return clean_planta or clean_name or str(code or "")

    def import_heca_zip(self, path: Path) -> HecaImportResult:
        """Importa almacenes y disponibilidad desde una exportacion Heca en .zip.

        Solo actualiza el Mapa Maestro local. No escribe nada en Heca ni WooCommerce.
        """
        payloads = self._read_heca_payloads(path)
        warehouses = self._parse_heca_dat(payloads["almacen"])
        stock_rows = self._parse_heca_dat(payloads["articulo_almacen"])

        with self.connect() as connection:
            connection.execute("DELETE FROM heca_warehouses")
            connection.execute("DELETE FROM heca_stock")

            warehouse_records = []
            for row in warehouses:
                code = self._to_int(row.get("Codigo"))
                if code is None:
                    continue
                warehouse_records.append(
                    {
                        "code": code,
                        "planta": self._clean_heca_text(row.get("Planta")),
                        "name": self._clean_heca_text(row.get("Nombre")),
                        "address": self._clean_heca_text(row.get("Direccion")),
                    }
                )
            if warehouse_records:
                connection.executemany(
                    """
                    INSERT INTO heca_warehouses (code, planta, name, address, updated_at)
                    VALUES (:code, :planta, :name, :address, CURRENT_TIMESTAMP)
                    """,
                    warehouse_records,
                )

            stock_records = []
            nonzero = 0
            for row in stock_rows:
                raw_code = self._clean_heca_text(row.get("Codigo"))
                normalized = self._normalize_code(raw_code)
                warehouse_code = self._to_int(row.get("Almacen"))
                if not raw_code or not normalized or warehouse_code is None:
                    continue
                quantity = self._to_float(row.get("Cantidad"))
                requested = self._to_float(row.get("CantidadPedida"))
                reserved = self._to_float(row.get("CantidadReservada"))
                supplier_ordered = self._to_float(row.get("CantidadPedidaProveedor"))
                if abs(quantity) > 1e-9:
                    nonzero += 1
                stock_records.append(
                    {
                        "item_code": raw_code,
                        "normalized_code": normalized,
                        "warehouse_code": warehouse_code,
                        "quantity": quantity,
                        "quantity_requested": requested,
                        "quantity_reserved": reserved,
                        "quantity_supplier_ordered": supplier_ordered,
                    }
                )
            if stock_records:
                connection.executemany(
                    """
                    INSERT INTO heca_stock (
                        item_code,
                        normalized_code,
                        warehouse_code,
                        quantity,
                        quantity_requested,
                        quantity_reserved,
                        quantity_supplier_ordered,
                        imported_at
                    )
                    VALUES (
                        :item_code,
                        :normalized_code,
                        :warehouse_code,
                        :quantity,
                        :quantity_requested,
                        :quantity_reserved,
                        :quantity_supplier_ordered,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(normalized_code, warehouse_code) DO UPDATE SET
                        item_code = excluded.item_code,
                        quantity = excluded.quantity,
                        quantity_requested = excluded.quantity_requested,
                        quantity_reserved = excluded.quantity_reserved,
                        quantity_supplier_ordered = excluded.quantity_supplier_ordered,
                        imported_at = CURRENT_TIMESTAMP
                    """,
                    stock_records,
                )

            active_warehouse_by_code = {
                int(record["code"]): record
                for record in warehouse_records
                if self._is_active_heca_warehouse(record.get("planta"), record.get("name"))
            }

            # Actualiza la lectura rapida del Mapa Maestro: tienda/exposicion frente a otros almacenes activos.
            inventory_rows = connection.execute("SELECT item_id, name FROM inventory_items").fetchall()
            matched_inventory = 0
            total_store = 0.0
            total_warehouse = 0.0
            heca_codes = {record["normalized_code"] for record in stock_records}
            matched_codes: set[str] = set()
            for item in inventory_rows:
                normalized = self._normalize_code(item["item_id"])
                rows = connection.execute(
                    "SELECT warehouse_code, quantity, item_code FROM heca_stock WHERE normalized_code = ?",
                    (normalized,),
                ).fetchall()
                if not rows:
                    continue
                matched_inventory += 1
                matched_codes.add(normalized)
                store_stock = 0.0
                warehouse_stock = 0.0
                reference = ""
                for stock in rows:
                    warehouse_code = int(stock["warehouse_code"])
                    if warehouse_code not in active_warehouse_by_code:
                        continue
                    quantity = self._to_float(stock["quantity"])
                    reference = str(stock["item_code"] or reference)
                    warehouse_info = active_warehouse_by_code.get(warehouse_code, {})
                    display_name = self._display_heca_warehouse(warehouse_info.get("planta"), warehouse_info.get("name"), warehouse_code).lower()
                    if "tienda" in display_name or "expos" in display_name:
                        store_stock += quantity
                    else:
                        warehouse_stock += quantity
                total_store += store_stock
                total_warehouse += warehouse_stock
                connection.execute(
                    """
                    UPDATE inventory_items
                    SET store_stock = ?,
                        warehouse_stock = ?,
                        heca_reference = COALESCE(NULLIF(heca_reference, ''), ?),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (store_stock, warehouse_stock, reference, int(item["item_id"])),
                )

            return HecaImportResult(
                warehouses=len(warehouse_records),
                stock_rows=len(stock_records),
                stock_rows_nonzero=nonzero,
                matched_inventory=matched_inventory,
                unmatched_heca_codes=len(heca_codes - matched_codes),
                total_store_stock=total_store,
                total_warehouse_stock=total_warehouse,
            )

    def get_heca_availability(self, item_id: int) -> list[dict[str, object]]:
        normalized = self._normalize_code(item_id)
        with self.connect() as connection:
            warehouses = connection.execute(
                "SELECT code, planta, name, address FROM heca_warehouses ORDER BY code"
            ).fetchall()
            stocks = {
                int(row["warehouse_code"]): row
                for row in connection.execute(
                    "SELECT * FROM heca_stock WHERE normalized_code = ?",
                    (normalized,),
                ).fetchall()
            }
        result: list[dict[str, object]] = []
        for warehouse in warehouses:
            code = int(warehouse["code"])
            if not self._is_active_heca_warehouse(warehouse["planta"], warehouse["name"]):
                continue
            stock = stocks.get(code)
            result.append(
                {
                    "warehouse_code": code,
                    "warehouse": self._display_heca_warehouse(warehouse["planta"], warehouse["name"], code),
                    "warehouse_name": self._clean_heca_text(warehouse["name"]),
                    "quantity": self._to_float(stock["quantity"]) if stock else 0.0,
                    "quantity_requested": self._to_float(stock["quantity_requested"]) if stock else 0.0,
                    "quantity_reserved": self._to_float(stock["quantity_reserved"]) if stock else 0.0,
                    "quantity_supplier_ordered": self._to_float(stock["quantity_supplier_ordered"]) if stock else 0.0,
                }
            )
        return result

    def _read_heca_payloads(self, path: Path) -> dict[str, bytes]:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                almacen = self._find_heca_member(names, "Almacen")
                articulo_almacen = self._find_heca_member(names, "ArticuloAlmacen")
                if almacen is None or articulo_almacen is None:
                    raise ValueError(
                        "El ZIP de Heca debe contener Almacen#...dat y ArticuloAlmacen#...dat."
                    )
                return {
                    "almacen": archive.read(almacen),
                    "articulo_almacen": archive.read(articulo_almacen),
                }
        if path.is_dir():
            files = list(path.glob("*.dat"))
            almacen = next((f for f in files if f.name.lower().startswith("almacen#")), None)
            articulo_almacen = next(
                (f for f in files if f.name.lower().startswith("articuloalmacen#")), None
            )
            if almacen is None or articulo_almacen is None:
                raise ValueError(
                    "La carpeta de Heca debe contener Almacen#...dat y ArticuloAlmacen#...dat."
                )
            return {
                "almacen": almacen.read_bytes(),
                "articulo_almacen": articulo_almacen.read_bytes(),
            }
        raise ValueError("Selecciona un .zip de Heca o una carpeta con archivos .dat.")

    def _find_heca_member(self, names: list[str], prefix: str) -> str | None:
        target = prefix.lower() + "#"
        for name in names:
            if Path(name).name.lower().startswith(target) and name.lower().endswith(".dat"):
                return name
        return None

    def _parse_heca_dat(self, payload: bytes) -> list[dict[str, str]]:
        parts = payload.split(b"\x19")
        if not parts:
            return []
        fields = self._heca_fields_from_schema(parts[0])
        rows: list[dict[str, str]] = []
        for part in parts[1:]:
            if not part.strip() or part.startswith(b"CREATE"):
                continue
            text = part.decode("latin1")
            values = next(csv.reader([text], delimiter=",", quotechar="'", skipinitialspace=True))
            rows.append({fields[index]: values[index] if index < len(values) else "" for index in range(len(fields))})
        return rows

    def _heca_fields_from_schema(self, payload: bytes) -> list[str]:
        schema = payload.decode("latin1")
        fields: list[str] = []
        current = ""
        depth = 0
        for char in schema:
            if char == "," and depth == 0:
                fields.append(current.strip())
                current = ""
                continue
            current += char
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
        if current.strip():
            fields.append(current.strip())
        names: list[str] = []
        for field in fields:
            match = re.match(
                r"(.+?)\s+(Texto|Entero|Fecha|Booleano|Memo|Real|Contador|Hora|Imagen|Binario)\b",
                field,
                re.IGNORECASE,
            )
            names.append(match.group(1).strip() if match else field)
        return names

    def _normalize_code(self, value: object) -> str:
        text = str(value or "").strip().strip("'")
        if not text:
            return ""
        if re.fullmatch(r"\d+(?:\.0+)?", text):
            text = text.split(".", 1)[0]
        if text.isdigit():
            return str(int(text))
        return text.upper()

    def _clean_heca_text(self, value: object) -> str:
        return str(value or "").replace("\r", " ").replace("\n", " ").strip()

    def _to_float(self, value: object) -> float:
        if value in (None, "", "Null"):
            return 0.0
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def _to_int(self, value: object) -> int | None:
        try:
            return int(float(str(value).replace(",", ".")))
        except (TypeError, ValueError):
            return None

    def count_items(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0])

    def list_items(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        inv.item_id,
                        inv.name,
                        inv.cubic_meters,
                        inv.rotation_c,
                        inv.packages,
                        inv.primary_supplier_price,
                        inv.pascal_price,
                        inv.order_calculated_price,
                        inv.weighted_average_cost,
                        inv.weighted_average_cost_updated_at,
                        COALESCE(NULLIF(inv.family, ''), cls.family, '') AS family,
                        COALESCE(NULLIF(inv.subgroup, ''), cls.subgroup, '') AS subgroup,
                        COALESCE(NULLIF(inv.size, ''), cls.size, '') AS size,
                        COALESCE(NULLIF(inv.materials, ''), cls.materials, '') AS materials,
                        COALESCE(NULLIF(inv.commercial_status, ''), cls.commercial_status, 'Normal') AS commercial_status,
                        COALESCE(inv.is_pack, cls.is_pack, 0) AS is_pack,
                        inv.store_stock,
                        inv.warehouse_stock,
                        inv.supplier_order_qty,
                        inv.supplier_order_provider,
                        inv.supplier_order_file,
                        inv.supplier_order_updated_at,
                        inv.heca_reference,
                        inv.notes,
                        inv.woo_item_kind,
                        inv.woo_id,
                        inv.woo_parent_id,
                        inv.woo_sku,
                        inv.woo_name,
                        inv.woo_type,
                        inv.woo_price,
                        inv.woo_categories,
                        inv.woo_link_status,
                        inv.woo_link_notes,
                        inv.woo_synced_at,
                        inv.source,
                        inv.updated_at
                    FROM inventory_items AS inv
                    LEFT JOIN product_classifications AS cls
                        ON cls.item_kind = inv.woo_item_kind
                       AND cls.item_woo_id = inv.woo_id
                    ORDER BY inv.item_id
                    """
                )
            )

    def get_item(self, item_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT
                    inv.item_id,
                    inv.name,
                    inv.cubic_meters,
                    inv.rotation_c,
                    inv.packages,
                    inv.primary_supplier_price,
                    inv.pascal_price,
                    inv.order_calculated_price,
                    inv.weighted_average_cost,
                    inv.weighted_average_cost_updated_at,
                    COALESCE(NULLIF(inv.family, ''), cls.family, '') AS family,
                    COALESCE(NULLIF(inv.subgroup, ''), cls.subgroup, '') AS subgroup,
                    COALESCE(NULLIF(inv.size, ''), cls.size, '') AS size,
                    COALESCE(NULLIF(inv.materials, ''), cls.materials, '') AS materials,
                    COALESCE(NULLIF(inv.commercial_status, ''), cls.commercial_status, 'Normal') AS commercial_status,
                    COALESCE(inv.is_pack, cls.is_pack, 0) AS is_pack,
                    inv.store_stock,
                    inv.warehouse_stock,
                    inv.supplier_order_qty,
                    inv.supplier_order_provider,
                    inv.supplier_order_file,
                    inv.supplier_order_updated_at,
                    inv.heca_reference,
                    inv.notes,
                    inv.woo_link_status,
                    inv.woo_id,
                    inv.woo_sku,
                    inv.woo_name,
                    inv.woo_price,
                    inv.woo_categories,
                    inv.source,
                    inv.updated_at
                FROM inventory_items AS inv
                LEFT JOIN product_classifications AS cls
                    ON cls.item_kind = inv.woo_item_kind
                   AND cls.item_woo_id = inv.woo_id
                WHERE inv.item_id = ?
                """,
                (item_id,),
            ).fetchone()

    def update_item(self, item: dict[str, object]) -> None:
        changes_for_log: list[dict[str, object]] = []
        item_name_for_log = str(item.get("name") or item.get("item_id") or "")
        with self.connect() as connection:
            current = self._get_item(connection, int(item["item_id"]))
            if current is None:
                return
            for readonly_field in (
                "supplier_order_qty",
                "supplier_order_provider",
                "supplier_order_file",
                "supplier_order_updated_at",
            ):
                item.setdefault(readonly_field, current[readonly_field] if readonly_field in current.keys() else None)
            changes_for_log = self._change_rows_for_log(dict(current), item)
            connection.execute(
                """
                UPDATE inventory_items
                SET
                    name = :name,
                    cubic_meters = :cubic_meters,
                    rotation_c = :rotation_c,
                    packages = :packages,
                    primary_supplier_price = :primary_supplier_price,
                    pascal_price = :pascal_price,
                    order_calculated_price = :order_calculated_price,
                    weighted_average_cost = :weighted_average_cost,
                    family = :family,
                    subgroup = :subgroup,
                    size = :size,
                    materials = :materials,
                    commercial_status = :commercial_status,
                    is_pack = :is_pack,
                    store_stock = :store_stock,
                    warehouse_stock = :warehouse_stock,
                    heca_reference = :heca_reference,
                    notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_id = :item_id
                """,
                item,
            )
            self._record_history(
                connection,
                current=dict(current),
                new_values=item,
                source="manual",
                notes="Cambio manual desde Gestion de Inventario",
            )
        if changes_for_log:
            _safe_security_log(
                self.db_path,
                module="Mapa Maestro",
                action="Modificar ficha del item",
                status="OK",
                entity_type="Articulo",
                entity_id=str(item.get("item_id", "")),
                details=f"Se modificaron {len(changes_for_log)} campos del item {item_name_for_log}.",
                context={
                    "item_id": item.get("item_id"),
                    "item_name": item_name_for_log,
                    "changes": changes_for_log,
                },
                category="Mapa Maestro",
            )

    def import_excel(self, path: Path) -> InventoryImportResult:
        workbook = openpyxl.load_workbook(path, data_only=True)
        sheet = workbook.active

        rows: list[dict[str, Any]] = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            item_id = row[0]
            name = row[1]
            if item_id is None or not name:
                continue
            rows.append(
                {
                    "item_id": int(item_id),
                    "name": str(name).strip(),
                    "cubic_meters": row[2],
                    "rotation_c": row[3],
                    "packages": row[4],
                    "primary_supplier_price": self._clean_price(row[5]),
                    "pascal_price": self._clean_price(row[6]),
                    "family": "",
                    "subgroup": "",
                    "size": "",
                    "materials": "",
                    "commercial_status": "Normal",
                    "is_pack": 0,
                    "store_stock": None,
                    "warehouse_stock": None,
                    "heca_reference": "",
                    "notes": "",
                    "source": str(path),
                }
            )

        with self.connect() as connection:
            for row in rows:
                current = self._get_item(connection, int(row["item_id"]))
                connection.execute(
                    """
                    INSERT INTO inventory_items (
                        item_id,
                        name,
                        cubic_meters,
                        rotation_c,
                        packages,
                        primary_supplier_price,
                        pascal_price,
                        family,
                        subgroup,
                        size,
                        materials,
                        commercial_status,
                        is_pack,
                        store_stock,
                        heca_reference,
                        notes,
                        source,
                        updated_at
                    )
                    VALUES (
                        :item_id,
                        :name,
                        :cubic_meters,
                        :rotation_c,
                        :packages,
                        :primary_supplier_price,
                        :pascal_price,
                        :family,
                        :subgroup,
                        :size,
                        :materials,
                        :commercial_status,
                        :is_pack,
                        :store_stock,
                        :heca_reference,
                        :notes,
                        :source,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(item_id) DO UPDATE SET
                        name = excluded.name,
                        cubic_meters = excluded.cubic_meters,
                        rotation_c = excluded.rotation_c,
                        packages = excluded.packages,
                        primary_supplier_price = excluded.primary_supplier_price,
                        pascal_price = excluded.pascal_price,
                        -- Los campos de Mapa Maestro se preservan en importaciones para no pisar trabajo manual.
                        source = excluded.source,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    row,
                )
                # Nueva capa de motor: precios por proveedor real.
                # Mantiene Precio 1/Precio 2 como compatibilidad, pero el cálculo
                # usará supplier_prices siempre que sea posible.
                primary_supplier = self._infer_primary_supplier(row)
                self._upsert_supplier_price(
                    connection,
                    int(row["item_id"]),
                    primary_supplier,
                    row.get("primary_supplier_price"),
                    f"Importado desde {path.name}",
                )
                self._upsert_supplier_price(
                    connection,
                    int(row["item_id"]),
                    "Pascal",
                    row.get("pascal_price"),
                    f"Importado desde {path.name}",
                )

                history_values = dict(row)
                if current is not None:
                    for field in MASTER_EXTRA_COLUMNS:
                        history_values[field] = current[field]
                self._record_history(
                    connection,
                    current=dict(current) if current is not None else None,
                    new_values=history_values,
                    source="excel_import",
                    notes=f"Importado desde {path.name}",
                )

        result = InventoryImportResult(
            rows_read=len(rows),
            stored=self.count_items(),
            source=path,
        )
        _safe_security_log(
            self.db_path,
            module="Mapa Maestro",
            action="Importar data.xlsx",
            status="OK",
            entity_type="Archivo",
            entity_id=path.name,
            details=f"Importación de data.xlsx completada. Filas leídas: {result.rows_read}. Artículos en Mapa Maestro: {result.stored}.",
            context={"archivo": str(path), "filas_leidas": result.rows_read, "articulos_guardados": result.stored},
            category="Mapa Maestro",
        )
        return result

    def link_with_woocommerce(self) -> WooLinkResult:
        """Enlaza el Mapa Maestro con productos/variaciones WooCommerce por SKU/codigo.

        No modifica WooCommerce. Solo guarda en inventory_items los datos de enlace local.
        """
        with self.connect() as connection:
            woo_items = self._load_woo_items(connection)
            by_key: dict[str, list[dict[str, object]]] = {}
            for woo in woo_items:
                for key in self._sku_keys(woo.get("sku")):
                    by_key.setdefault(key, []).append(woo)

            inventory_rows = list(connection.execute("SELECT item_id, name FROM inventory_items ORDER BY item_id"))
            used_woo_ids: set[tuple[str, int]] = set()
            result = WooLinkResult(total_inventory=len(inventory_rows))
            details: list[str] = []

            for row in inventory_rows:
                item_id = int(row["item_id"])
                keys = self._sku_keys(item_id)
                matches: list[dict[str, object]] = []
                seen: set[tuple[str, int]] = set()
                for key in keys:
                    for match in by_key.get(key, []):
                        identity = (str(match["item_kind"]), int(match["woo_id"]))
                        if identity not in seen:
                            seen.add(identity)
                            matches.append(match)

                if len(matches) == 1:
                    match = matches[0]
                    derived = self._derive_master_fields_from_woo(match)
                    used_woo_ids.add((str(match["item_kind"]), int(match["woo_id"])))
                    connection.execute(
                        """
                        UPDATE inventory_items
                        SET
                            woo_item_kind = :item_kind,
                            woo_id = :woo_id,
                            woo_parent_id = :parent_woo_id,
                            woo_sku = :sku,
                            woo_name = :name,
                            woo_type = :woo_type,
                            woo_price = :price,
                            woo_categories = :categories,
                            family = COALESCE(NULLIF(family, ''), :derived_family),
                            size = COALESCE(NULLIF(size, ''), :derived_size),
                            materials = COALESCE(NULLIF(materials, ''), :derived_materials),
                            commercial_status = CASE
                                WHEN commercial_status IS NULL OR commercial_status = '' OR commercial_status = 'Normal'
                                THEN :derived_commercial_status
                                ELSE commercial_status
                            END,
                            is_pack = CASE
                                WHEN COALESCE(is_pack, 0) = 1 THEN 1
                                ELSE :derived_is_pack
                            END,
                            woo_link_status = 'Enlazado',
                            woo_link_notes = '',
                            woo_synced_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE item_id = :item_id
                        """,
                        {**match, **derived, "item_id": item_id},
                    )
                    result = self._replace_result(result, linked=result.linked + 1)
                elif len(matches) > 1:
                    names = "; ".join(f"{m['item_kind']} #{m['woo_id']} {m.get('sku') or ''} {m.get('name') or ''}" for m in matches[:5])
                    connection.execute(
                        """
                        UPDATE inventory_items
                        SET
                            woo_item_kind = NULL,
                            woo_id = NULL,
                            woo_parent_id = NULL,
                            woo_sku = NULL,
                            woo_name = NULL,
                            woo_type = NULL,
                            woo_price = NULL,
                            woo_categories = NULL,
                            woo_link_status = 'Conflicto',
                            woo_link_notes = :notes,
                            woo_synced_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE item_id = :item_id
                        """,
                        {"item_id": item_id, "notes": names},
                    )
                    details.append(f"Conflicto {item_id}: {names}")
                    result = self._replace_result(result, conflicts=result.conflicts + 1)
                else:
                    connection.execute(
                        """
                        UPDATE inventory_items
                        SET
                            woo_item_kind = NULL,
                            woo_id = NULL,
                            woo_parent_id = NULL,
                            woo_sku = NULL,
                            woo_name = NULL,
                            woo_type = NULL,
                            woo_price = NULL,
                            woo_categories = NULL,
                            woo_link_status = 'Sin Woo',
                            woo_link_notes = 'No se encontro producto o variacion WooCommerce con este SKU/codigo.',
                            woo_synced_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE item_id = :item_id
                        """,
                        {"item_id": item_id},
                    )
                    result = self._replace_result(result, missing=result.missing + 1)

            woo_without_inventory = 0
            inventory_keys = {key for row in inventory_rows for key in self._sku_keys(row["item_id"])}
            for woo in woo_items:
                identity = (str(woo["item_kind"]), int(woo["woo_id"]))
                if identity in used_woo_ids:
                    continue
                if not any(key in inventory_keys for key in self._sku_keys(woo.get("sku"))):
                    woo_without_inventory += 1
            result = self._replace_result(
                result,
                woo_without_inventory=woo_without_inventory,
                details=details[:20],
            )
            return result

    def _derive_master_fields_from_woo(self, woo: dict[str, object]) -> dict[str, object]:
        """Extrae una clasificacion local compacta desde datos Woo ya sincronizados.

        No modifica WooCommerce. Solo ayuda a rellenar el Mapa Maestro cuando los
        campos locales estan vacios.
        """
        text = self._normalize_text(
            " ".join(
                str(woo.get(key) or "")
                for key in ("name", "sku", "categories", "woo_type")
            )
        )

        status = "Normal"
        if "outlet" in text:
            status = "Outlet"
        elif "oferta" in text or "rebaja" in text:
            status = "Oferta"

        is_pack = 1 if any(token in text for token in ("pack", "combo", "conjunto")) else 0

        family = "Otros / Sin clasificar"
        is_futon_cover = any(
            re.search(pattern, text)
            for pattern in (
                r"\bfundas?\s+(?:de\s+|para\s+)?futones?\b",
                r"\bcovers?\s+(?:de\s+|para\s+)?futones?\b",
            )
        )
        if is_futon_cover:
            family = "Complementos"
        elif "futon" in text:
            family = "Futones"
        elif "tatami" in text:
            family = "Tatamis"
        elif "sofa cama" in text or "sofacama" in text:
            family = "Sofás Cama"
        elif "cama japonesa" in text or "camas japonesas" in text:
            family = "Camas Japonesas"
        elif any(token in text for token in ("mesita", "funda", "cover", "topper", "almohada", "almohadas", "cojin", "cojines", "complemento")):
            family = "Complementos"
        elif "oferta" in text or "pack" in text:
            family = "Ofertas / Packs"

        materials: list[str] = []
        material_rules = [
            ("Algodón", ("algodon", "cotton")),
            ("Látex", ("latex",)),
            ("Lana", ("lana", "wool")),
            ("Coco", ("coco", "coir")),
        ]
        for label, tokens in material_rules:
            if any(token in text for token in tokens):
                materials.append(label)

        size = self._extract_size_from_text(text)

        return {
            "derived_family": family,
            "derived_size": size,
            "derived_materials": ", ".join(materials),
            "derived_commercial_status": status,
            "derived_is_pack": is_pack,
        }

    def _normalize_text(self, value: str) -> str:
        text = value.lower()
        replacements = {
            "á": "a", "à": "a", "ä": "a", "â": "a",
            "é": "e", "è": "e", "ë": "e", "ê": "e",
            "í": "i", "ì": "i", "ï": "i", "î": "i",
            "ó": "o", "ò": "o", "ö": "o", "ô": "o",
            "ú": "u", "ù": "u", "ü": "u", "û": "u",
            "ñ": "n",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _extract_size_from_text(self, text: str) -> str:
        normalized = text.replace(",", ".")
        full = re.search(
            r"(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{1,2}(?:\.\d+)?)",
            normalized,
        )
        if full:
            return "x".join(self._clean_dimension(part) for part in full.groups())

        base = re.search(
            r"(\d{2,3}(?:\.\d+)?)\s*[x*×]\s*(\d{2,3}(?:\.\d+)?)",
            normalized,
        )
        thickness = re.search(
            r"(?:grosor|espesor|altura)\s*[:\-]?\s*(\d{1,2}(?:\.\d+)?)",
            normalized,
        )
        if base and thickness:
            return "x".join(
                [
                    self._clean_dimension(base.group(1)),
                    self._clean_dimension(base.group(2)),
                    self._clean_dimension(thickness.group(1)),
                ]
            )
        if base:
            return "x".join(self._clean_dimension(part) for part in base.groups())
        return ""

    def _clean_dimension(self, value: str) -> str:
        value = value.strip().replace(",", ".")
        try:
            number = float(value)
        except ValueError:
            return value
        if number.is_integer():
            return str(int(number))
        return (f"{number:.2f}".rstrip("0").rstrip("."))

    def _replace_result(self, result: WooLinkResult, **changes: object) -> WooLinkResult:
        data = {
            "total_inventory": result.total_inventory,
            "linked": result.linked,
            "missing": result.missing,
            "conflicts": result.conflicts,
            "woo_without_inventory": result.woo_without_inventory,
            "details": result.details,
        }
        data.update(changes)
        return WooLinkResult(**data)

    def _load_woo_items(self, connection: sqlite3.Connection) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        if not self._table_exists(connection, "products"):
            return items
        products = list(
            connection.execute(
                """
                SELECT
                    p.woo_id,
                    p.name,
                    p.sku,
                    p.type,
                    p.price,
                    p.regular_price,
                    p.sale_price,
                    p.categories_json
                FROM products p
                ORDER BY p.woo_id
                """
            )
        )
        category_by_product = self._product_categories(connection)
        for row in products:
            categories = category_by_product.get(int(row["woo_id"]), self._categories_from_json(row["categories_json"]))
            items.append(
                {
                    "item_kind": "product",
                    "woo_id": int(row["woo_id"]),
                    "parent_woo_id": None,
                    "sku": row["sku"] or "",
                    "name": row["name"] or "",
                    "woo_type": row["type"] or "product",
                    "price": self._first_text(row["price"], row["regular_price"], row["sale_price"]),
                    "categories": ", ".join(categories),
                }
            )

        if self._table_exists(connection, "product_variations"):
            variations = list(
                connection.execute(
                    """
                    SELECT
                        v.woo_id,
                        v.parent_woo_id,
                        v.parent_name,
                        v.sku,
                        v.price,
                        v.regular_price,
                        v.sale_price,
                        v.attributes_label,
                        p.type AS parent_type
                    FROM product_variations v
                    LEFT JOIN products p ON p.woo_id = v.parent_woo_id
                    ORDER BY v.parent_woo_id, v.woo_id
                    """
                )
            )
            for row in variations:
                parent_id = int(row["parent_woo_id"])
                categories = category_by_product.get(parent_id, [])
                label = row["attributes_label"] or ""
                name = f"{row['parent_name'] or ''} - {label}".strip(" -")
                items.append(
                    {
                        "item_kind": "variation",
                        "woo_id": int(row["woo_id"]),
                        "parent_woo_id": parent_id,
                        "sku": row["sku"] or "",
                        "name": name,
                        "woo_type": "variation",
                        "price": self._first_text(row["price"], row["regular_price"], row["sale_price"]),
                        "categories": ", ".join(categories),
                    }
                )
        return items

    def _product_categories(self, connection: sqlite3.Connection) -> dict[int, list[str]]:
        if not self._table_exists(connection, "product_categories"):
            return {}
        data: dict[int, list[str]] = {}
        for row in connection.execute(
            """
            SELECT product_woo_id, category_name
            FROM product_categories
            ORDER BY product_woo_id, category_name
            """
        ):
            data.setdefault(int(row["product_woo_id"]), []).append(str(row["category_name"]))
        return data

    def _categories_from_json(self, value: object) -> list[str]:
        if not value:
            return []
        try:
            parsed = json.loads(str(value))
        except Exception:
            return []
        return [str(item.get("name") or "") for item in parsed if isinstance(item, dict) and item.get("name")]

    def _table_exists(self, connection: sqlite3.Connection, name: str) -> bool:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def _sku_keys(self, value: object) -> set[str]:
        if value in (None, ""):
            return set()
        text = str(value).strip().upper()
        if not text:
            return set()
        compact = re.sub(r"[^0-9A-Z]", "", text)
        keys = {compact} if compact else set()
        if compact.isdigit():
            stripped = compact.lstrip("0") or "0"
            keys.add(stripped)
            keys.add(stripped.zfill(7))
        return {key for key in keys if key}

    def _first_text(self, *values: object) -> str:
        for value in values:
            if value not in (None, ""):
                return str(value)
        return ""

    def list_history(self, item_id: int | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT
                id,
                item_id,
                item_name,
                field_name,
                old_value,
                new_value,
                change_source,
                notes,
                created_at
            FROM inventory_change_history
        """
        params: tuple[object, ...] = ()
        if item_id is not None:
            query += " WHERE item_id = ?"
            params = (item_id,)
        query += " ORDER BY created_at DESC, id DESC LIMIT 500"
        with self.connect() as connection:
            return list(connection.execute(query, params))

    def _get_item(self, connection: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT
                item_id,
                name,
                cubic_meters,
                rotation_c,
                packages,
                primary_supplier_price,
                pascal_price,
                order_calculated_price,
                weighted_average_cost,
                weighted_average_cost_updated_at,
                family,
                subgroup,
                size,
                materials,
                commercial_status,
                is_pack,
                store_stock,
                warehouse_stock,
                supplier_order_qty,
                supplier_order_provider,
                supplier_order_file,
                supplier_order_updated_at,
                heca_reference,
                notes,
                woo_item_kind,
                woo_id,
                woo_parent_id,
                woo_sku,
                woo_name,
                woo_type,
                woo_price,
                woo_categories,
                woo_link_status,
                woo_link_notes,
                woo_synced_at,
                source,
                updated_at
            FROM inventory_items
            WHERE item_id = ?
            """,
            (item_id,),
        ).fetchone()

    def _change_rows_for_log(
        self,
        current: dict[str, object] | None,
        new_values: dict[str, object],
    ) -> list[dict[str, object]]:
        tracked_fields = {
            "name": "Articulo",
            "cubic_meters": "M3",
            "rotation_c": "Rotacion C",
            "packages": "Bultos",
            "primary_supplier_price": "Precio Ekomat/Hemei/Cipta",
            "pascal_price": "Precio Pascal",
            "order_calculated_price": "Precio Calculado de Pedido",
            "weighted_average_cost": "Coste Promedio Ponderado",
            "family": "Familia interna",
            "subgroup": "Subgrupo",
            "size": "Medida A x L x H",
            "materials": "Materiales",
            "commercial_status": "Estado comercial",
            "is_pack": "Es pack",
            "store_stock": "Stock tienda",
            "warehouse_stock": "Stock almacenes",
            "supplier_order_qty": "Pedido proveedor",
            "supplier_order_provider": "Proveedor pedido",
            "supplier_order_file": "Archivo pedido proveedor",
            "heca_reference": "Referencia Heca",
            "notes": "Notas",
            "woo_link_status": "Estado enlace Woo",
            "woo_id": "ID Woo",
            "woo_sku": "SKU Woo",
            "woo_name": "Nombre Woo",
        }
        rows: list[dict[str, object]] = []
        for field, label in tracked_fields.items():
            old_value = "" if current is None else self._history_value(current.get(field))
            new_value = self._history_value(new_values.get(field))
            if old_value == new_value:
                continue
            rows.append({
                "campo": label,
                "field": field,
                "valor_anterior": old_value,
                "valor_nuevo": new_value,
            })
        return rows

    def _record_history(
        self,
        connection: sqlite3.Connection,
        current: dict[str, object] | None,
        new_values: dict[str, object],
        source: str,
        notes: str,
    ) -> None:
        tracked_fields = {
            "name": "Articulo",
            "cubic_meters": "M3",
            "rotation_c": "Rotacion C",
            "packages": "Bultos",
            "primary_supplier_price": "Precio Ekomat/Hemei/Cipta",
            "pascal_price": "Precio Pascal",
            "order_calculated_price": "Precio Calculado de Pedido",
            "weighted_average_cost": "Coste Promedio Ponderado",
            "family": "Familia interna",
            "subgroup": "Subgrupo",
            "size": "Medida A x L x H",
            "materials": "Materiales",
            "commercial_status": "Estado comercial",
            "is_pack": "Es pack",
            "store_stock": "Stock tienda",
            "warehouse_stock": "Stock almacenes",
            "supplier_order_qty": "Pedido proveedor",
            "supplier_order_provider": "Proveedor pedido",
            "supplier_order_file": "Archivo pedido proveedor",
            "heca_reference": "Referencia Heca",
            "notes": "Notas",
            "woo_link_status": "Estado enlace Woo",
            "woo_id": "ID Woo",
            "woo_sku": "SKU Woo",
            "woo_name": "Nombre Woo",
        }
        rows = []
        item_name = str(new_values.get("name") or "")
        for field, label in tracked_fields.items():
            old_value = "" if current is None else self._history_value(current.get(field))
            new_value = self._history_value(new_values.get(field))
            if old_value == new_value:
                continue
            rows.append(
                {
                    "item_id": new_values["item_id"],
                    "item_name": item_name,
                    "field_name": label,
                    "old_value": old_value,
                    "new_value": new_value,
                    "change_source": source,
                    "notes": notes,
                }
            )

        if rows:
            connection.executemany(
                """
                INSERT INTO inventory_change_history (
                    item_id,
                    item_name,
                    field_name,
                    old_value,
                    new_value,
                    change_source,
                    notes
                )
                VALUES (
                    :item_id,
                    :item_name,
                    :field_name,
                    :old_value,
                    :new_value,
                    :change_source,
                    :notes
                )
                """,
                rows,
            )

    def _clean_price(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _history_value(self, value: object) -> str:
        if value in (None, ""):
            return ""
        return str(value)


class InventoryApp(tk.Tk):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.store = InventoryStore(settings.db_path)
        self.store.init_schema()

        self.title("Futon Espai - Mapa Maestro de Productos")
        self.geometry("1120x680")
        self.minsize(920, 520)
        self.configure(bg=C_BG)
        apply_theme(self)

        self.search_text = tk.StringVar()
        self.family_filter = tk.StringVar(value="Todas")
        self.status_filter = tk.StringVar(value="Todos")
        self.woo_link_filter = tk.StringVar(value="Todos")
        self.status_text = tk.StringVar(value="Cargando mapa maestro de productos...")
        self.items: list[dict[str, object]] = []
        self._work_overlay: tk.Frame | None = None
        self._work_message = tk.StringVar(value="")

        self._build_layout()
        if self.store.count_items() == 0 and DEFAULT_EXCEL_PATH.exists():
            self._import_excel(DEFAULT_EXCEL_PATH, silent=True)
        self._load_items()

    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill=tk.X)

        ttk.Label(header, text="Mapa Maestro de Productos", style="Title.TLabel").pack(
            side=tk.LEFT
        )

        toolbar = ttk.Frame(self, padding=(14, 8, 14, 10), style="Toolbar.TFrame")
        toolbar.pack(fill=tk.X)

        ttk.Button(
            toolbar,
            text="Importar data.xlsx",
            style="Secondary.TButton",
            command=self._choose_excel,
        ).pack(side=tk.LEFT)

        ttk.Button(
            toolbar,
            text="Importar Heca",
            style="Secondary.TButton",
            command=self._choose_heca_zip,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            toolbar,
            text="Enlazar WooCommerce",
            command=self._link_with_woocommerce,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            toolbar,
            text="Modificar ficha",
            command=self._open_edit_dialog,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            toolbar,
            text="Ver historico",
            command=self._open_history_dialog,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            toolbar,
            text="Pedidos",
            command=self._open_supplier_orders_dialog,
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(toolbar, text="Familia:").pack(side=tk.LEFT, padx=(18, 6))
        self.family_combo = ttk.Combobox(
            toolbar,
            textvariable=self.family_filter,
            values=["Todas"],
            width=18,
            state="readonly",
        )
        self.family_combo.pack(side=tk.LEFT)
        self.family_combo.bind("<<ComboboxSelected>>", lambda _event: self._render_items())

        ttk.Label(toolbar, text="Estado:").pack(side=tk.LEFT, padx=(10, 6))
        self.status_combo = ttk.Combobox(
            toolbar,
            textvariable=self.status_filter,
            values=["Todos", "Normal", "Outlet", "Oferta", "Pendientes"],
            width=14,
            state="readonly",
        )
        self.status_combo.pack(side=tk.LEFT)
        self.status_combo.bind("<<ComboboxSelected>>", lambda _event: self._render_items())

        ttk.Label(toolbar, text="Woo:").pack(side=tk.LEFT, padx=(10, 6))
        self.woo_link_combo = ttk.Combobox(
            toolbar,
            textvariable=self.woo_link_filter,
            values=["Todos", "Enlazado", "Sin Woo", "Conflicto", "Sin enlazar"],
            width=12,
            state="readonly",
        )
        self.woo_link_combo.pack(side=tk.LEFT)
        self.woo_link_combo.bind("<<ComboboxSelected>>", lambda _event: self._render_items())

        ttk.Label(toolbar, text="Buscar:").pack(side=tk.LEFT, padx=(18, 6))
        search_entry = ttk.Entry(toolbar, textvariable=self.search_text, width=40)
        search_entry.pack(side=tk.LEFT)
        search_entry.bind("<KeyRelease>", lambda _event: self._render_items())

        ttk.Button(toolbar, text="Limpiar", command=self._clear_search).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        outer_table = tk.Frame(
            self,
            bg=C_PANEL,
            highlightbackground=C_PANEL_LINE,
            highlightthickness=1,
            bd=0,
        )
        outer_table.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        table_frame = ttk.Frame(outer_table, padding=(10, 10, 10, 8), style="Panel.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = (
            "item_id",
            "name",
            "family",
            "size",
            "materials",
            "suppliers",
            "supplier_prices_visible",
            "order_calculated_price",
            "weighted_average_cost",
            "woo_price",
            "stock_total",
            "supplier_order_qty",
            "commercial_status",
            "is_pack",
            "cubic_meters",
            "rotation_c",
            "packages",
            "woo_link_status",
            "woo_sku",
            "updated_at",
        )
        headings = {
            "item_id": "Codigo",
            "name": "Articulo",
            "family": "Familia",
            "size": "Medida A x L x H",
            "materials": "Materiales",
            "suppliers": "Proveedores",
            "supplier_prices_visible": "Precios proveedores",
            "order_calculated_price": "Precio Calculado de Pedido",
            "weighted_average_cost": "Coste Promedio Ponderado",
            "woo_price": "Precio Woo",
            "stock_total": "Stock",
            "supplier_order_qty": "Pedido proveedor",
            "commercial_status": "Estado",
            "is_pack": "Pack",
            "cubic_meters": "M3",
            "rotation_c": "Rotacion C",
            "packages": "Bultos",
            "woo_link_status": "Enlace Woo",
            "woo_sku": "SKU Woo",
            "updated_at": "Actualizado",
        }
        widths = {
            "item_id": 90,
            "name": 340,
            "family": 135,
            "size": 150,
            "materials": 140,
            "suppliers": 180,
            "supplier_prices_visible": 260,
            "order_calculated_price": 155,
            "weighted_average_cost": 145,
            "woo_price": 100,
            "stock_total": 105,
            "supplier_order_qty": 130,
            "commercial_status": 110,
            "is_pack": 70,
            "cubic_meters": 90,
            "rotation_c": 100,
            "packages": 80,
            "woo_link_status": 120,
            "woo_sku": 120,
            "updated_at": 150,
        }

        self.table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        for column in columns:
            self.table.heading(column, text=headings[column], anchor=tk.CENTER)
            self.table.column(column, width=widths[column], minwidth=60, anchor=tk.CENTER)

        self.table.bind("<Double-1>", lambda _event: self._open_heca_availability_dialog())

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        ttk.Label(
            self,
            textvariable=self.status_text,
            padding=(14, 4),
            anchor=tk.W,
            style="Status.TLabel",
        ).pack(fill=tk.X)

    def _load_items(self) -> None:
        self.items = [dict(row) for row in self.store.list_items()]
        self._refresh_filter_values()
        self._render_items()

    def _refresh_filter_values(self) -> None:
        families = sorted({str(item.get("family") or "Sin familia") for item in self.items})
        self.family_combo.configure(values=["Todas"] + families)
        if self.family_filter.get() not in ["Todas"] + families:
            self.family_filter.set("Todas")

    def _render_items(self) -> None:
        query = self.search_text.get().strip().lower()
        filtered = self.items
        family = self.family_filter.get()
        status = self.status_filter.get()
        woo_status = self.woo_link_filter.get()
        if family != "Todas":
            filtered = [
                item
                for item in filtered
                if str(item.get("family") or "Sin familia") == family
            ]
        if status == "Pendientes":
            filtered = [
                item
                for item in filtered
                if not item.get("family")
                or not item.get("size")
                or not item.get("commercial_status")
            ]
        elif status != "Todos":
            filtered = [
                item
                for item in filtered
                if str(item.get("commercial_status") or "Normal") == status
            ]
        if woo_status != "Todos":
            filtered = [
                item
                for item in filtered
                if str(item.get("woo_link_status") or "Sin enlazar") == woo_status
            ]
        if query:
            filtered = [
                item
                for item in filtered
                if query in str(item["item_id"]).lower()
                or query in str(item["name"]).lower()
                or query in str(item.get("family") or "").lower()
                or query in str(item.get("subgroup") or "").lower()
                or query in str(item.get("materials") or "").lower()
                or query in str(item.get("heca_reference") or "").lower()
                or query in str(item.get("woo_sku") or "").lower()
                or query in str(item.get("woo_name") or "").lower()
                or query in str(item.get("woo_categories") or "").lower()
                or query in str(item.get("woo_link_status") or "").lower()
            ]

        for current in self.table.get_children():
            self.table.delete(current)

        for item in filtered:
            self.table.insert(
                "",
                tk.END,
                values=(
                    item["item_id"],
                    item["name"],
                    item.get("family") or "",
                    item.get("size") or "",
                    item.get("materials") or "",
                    self._suppliers_for_item(item),
                    self._supplier_prices_display_for_item(item),
                    self._format_price(item.get("order_calculated_price")),
                    self._format_price(item.get("weighted_average_cost")),
                    item.get("woo_price") or "",
                    self._format_number(
                        self.store._to_float(item.get("store_stock"))
                        + self.store._to_float(item.get("warehouse_stock"))
                    ),
                    self._format_number(item.get("supplier_order_qty")),
                    item.get("commercial_status") or "Normal",
                    "Si" if item.get("is_pack") else "No",
                    self._format_number(item["cubic_meters"]),
                    self._format_number(item["rotation_c"]),
                    item["packages"] or "",
                    item.get("woo_link_status") or "Sin enlazar",
                    item.get("woo_sku") or "",
                    item["updated_at"] or "",
                ),
            )

        self._auto_fit_table_columns()

        linked = sum(1 for item in self.items if str(item.get("woo_link_status") or "") == "Enlazado")
        missing = sum(1 for item in self.items if str(item.get("woo_link_status") or "") == "Sin Woo")
        conflicts = sum(1 for item in self.items if str(item.get("woo_link_status") or "") == "Conflicto")
        self.status_text.set(
            f"Articulos visibles: {len(filtered)} | Total mapa: {len(self.items)} | "
            f"Woo enlazados: {linked} | Sin Woo: {missing} | Conflictos: {conflicts}"
        )

    def _auto_fit_table_columns(self, *, min_width: int = 70, max_width: int = 360, padding: int = 34) -> None:
        """Ajusta columnas al contenido visible, centrando texto y conservando scroll horizontal."""
        try:
            body_font = tk.font.nametofont("TkDefaultFont")
        except Exception:
            body_font = None
        try:
            heading_font = tk.font.nametofont("TkHeadingFont")
        except Exception:
            heading_font = body_font
        columns = list(self.table["columns"])
        for column in columns:
            heading = str(self.table.heading(column, "text") or column)
            width = (heading_font.measure(heading) if heading_font else len(heading) * 8) + padding
            index = columns.index(column)
            for row_id in self.table.get_children(""):
                values = self.table.item(row_id, "values")
                if index < len(values):
                    text = str(values[index] or "")
                    measured = (body_font.measure(text) if body_font else len(text) * 8) + padding
                    width = max(width, measured)
            self.table.heading(column, anchor=tk.CENTER)
            self.table.column(column, anchor=tk.CENTER, width=max(min_width, min(width, max_width)), minwidth=min_width, stretch=False)

    def _link_with_woocommerce(self) -> None:
        if not messagebox.askyesno(
            "Enlazar con WooCommerce",
            (
                "El HUB enlazara el Mapa Maestro con los productos y variaciones "
                "sincronizados desde WooCommerce usando SKU/codigo.\n\n"
                "No se modificara WooCommerce. Solo se guardaran enlaces locales.\n\n"
                "¿Continuar?"
            ),
        ):
            return
        self._show_work_overlay(
            "Enlazando Mapa Maestro con WooCommerce...\n"
            "Buscando coincidencias por SKU/codigo. Esto no modifica la tienda online."
        )

        def worker() -> None:
            try:
                result = self.store.link_with_woocommerce()
            except Exception as exc:  # pragma: no cover - UI guard
                self.after(0, lambda: self._finish_woo_link(error=exc))
                return
            self.after(0, lambda: self._finish_woo_link(result=result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_woo_link(
        self,
        result: WooLinkResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._hide_work_overlay()
        if error is not None:
            messagebox.showerror("Enlace fallido", str(error))
            return
        self._load_items()
        if result is None:
            return
        detail_text = ""
        if result.details:
            detail_text = "\n\nPrimeros conflictos detectados:\n" + "\n".join(result.details[:8])
        messagebox.showinfo(
            "Enlace WooCommerce terminado",
            (
                f"Articulos en Mapa Maestro: {result.total_inventory}\n"
                f"Enlazados: {result.linked}\n"
                f"Sin producto Woo: {result.missing}\n"
                f"Conflictos: {result.conflicts}\n"
                f"Productos/variaciones Woo sin Mapa Maestro: {result.woo_without_inventory}"
                f"{detail_text}"
            ),
        )
        _safe_security_log(
            self.settings.db_path,
            module="Mapa Maestro",
            action="Enlazar WooCommerce",
            status="OK",
            entity_type="WooCommerce",
            entity_id="SKU/código",
            details=(
                f"Enlace WooCommerce terminado. Enlazados: {result.linked}. "
                f"Sin Woo: {result.missing}. Conflictos: {result.conflicts}."
            ),
            context={
                "total_inventory": result.total_inventory,
                "linked": result.linked,
                "missing": result.missing,
                "conflicts": result.conflicts,
                "woo_without_inventory": result.woo_without_inventory,
                "details": list(result.details[:20]),
            },
            category="Mapa Maestro",
        )

    def _show_work_overlay(self, message: str) -> None:
        if self._work_overlay is not None:
            self._work_message.set(message)
            return
        self._work_message.set(message)
        overlay = tk.Frame(self, bg="#E5E7EB", bd=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()
        card = tk.Frame(
            overlay,
            bg=C_PANEL,
            highlightbackground=C_PANEL_LINE,
            highlightthickness=1,
            bd=0,
        )
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=560, height=170)
        ttk.Label(card, text="HUB trabajando", style="Section.TLabel").pack(pady=(22, 8))
        ttk.Label(
            card,
            textvariable=self._work_message,
            justify=tk.CENTER,
            anchor=tk.CENTER,
            wraplength=500,
        ).pack(fill=tk.X, padx=24)
        progress = ttk.Progressbar(card, mode="indeterminate", length=430)
        progress.pack(pady=(18, 0))
        progress.start(12)
        self._work_overlay = overlay
        self.update_idletasks()

    def _hide_work_overlay(self) -> None:
        if self._work_overlay is not None:
            self._work_overlay.destroy()
            self._work_overlay = None

    def _choose_excel(self) -> None:
        initial_dir = DEFAULT_EXCEL_PATH.parent if DEFAULT_EXCEL_PATH.exists() else ROOT.parent
        selected = filedialog.askopenfilename(
            title="Selecciona el Excel inicial de inventario",
            initialdir=initial_dir,
            filetypes=[("Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        self._import_excel(Path(selected), silent=False)
        self._load_items()

    def _import_excel(self, path: Path, silent: bool) -> None:
        try:
            result = self.store.import_excel(path)
        except Exception as exc:
            if silent:
                self.status_text.set(f"No se pudo importar el Excel inicial: {exc}")
                return
            messagebox.showerror("Importacion fallida", str(exc))
            return

        if not silent:
            messagebox.showinfo(
                "Inventario importado",
                (
                    f"Filas leidas: {result.rows_read}\n"
                    f"Articulos guardados: {result.stored}"
                ),
            )

    def _choose_heca_zip(self) -> None:
        initial_dir = ROOT.parent
        selected = filedialog.askopenfilename(
            title="Selecciona exportacion Heca (.zip)",
            initialdir=initial_dir,
            filetypes=[("ZIP Heca", "*.zip"), ("Todos los archivos", "*.*")],
        )
        if not selected:
            return
        if not messagebox.askyesno(
            "Importar Heca",
            (
                "El HUB leera almacenes y disponibilidad desde la exportacion de Heca.\n\n"
                "No se modificara Heca ni WooCommerce. Solo se actualizaran datos locales "
                "del Mapa Maestro: stock tienda, stock almacenes y detalle por almacen.\n\n"
                "¿Continuar?"
            ),
        ):
            return
        self._show_work_overlay(
            "Importando disponibilidad desde Heca...\n"
            "Leyendo almacenes y stock por articulo. Esto solo actualiza el Mapa Maestro local."
        )

        def worker() -> None:
            try:
                result = self.store.import_heca_zip(Path(selected))
            except Exception as exc:  # pragma: no cover - UI guard
                self.after(0, lambda: self._finish_heca_import(error=exc))
                return
            self.after(0, lambda: self._finish_heca_import(result=result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_heca_import(
        self,
        result: HecaImportResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._hide_work_overlay()
        if error is not None:
            messagebox.showerror("Importacion Heca fallida", str(error))
            return
        self._load_items()
        if result is None:
            return
        messagebox.showinfo(
            "Importacion Heca terminada",
            (
                f"Almacenes detectados: {result.warehouses}\n"
                f"Registros de stock leidos: {result.stock_rows}\n"
                f"Registros con stock distinto de 0: {result.stock_rows_nonzero}\n"
                f"Articulos del Mapa Maestro enlazados con stock Heca: {result.matched_inventory}\n"
                f"Codigos Heca sin articulo en Mapa Maestro: {result.unmatched_heca_codes}\n"
                f"Stock tienda/exposicion: {self._format_number(result.total_store_stock)}\n"
                f"Stock almacenes: {self._format_number(result.total_warehouse_stock)}"
            ),
        )
        _safe_security_log(
            self.settings.db_path,
            module="Mapa Maestro",
            action="Importar Heca",
            status="OK",
            entity_type="Archivo Heca",
            entity_id="ZIP",
            details=(
                f"Importación Heca terminada. Artículos enlazados: {result.matched_inventory}. "
                f"Stock tienda/exposición: {self._format_number(result.total_store_stock)}. "
                f"Stock almacenes: {self._format_number(result.total_warehouse_stock)}."
            ),
            context={
                "warehouses": result.warehouses,
                "stock_rows": result.stock_rows,
                "stock_rows_nonzero": result.stock_rows_nonzero,
                "matched_inventory": result.matched_inventory,
                "unmatched_heca_codes": result.unmatched_heca_codes,
                "total_store_stock": result.total_store_stock,
                "total_warehouse_stock": result.total_warehouse_stock,
            },
            category="Mapa Maestro",
        )

    def _clear_search(self) -> None:
        self.search_text.set("")
        self.family_filter.set("Todas")
        self.status_filter.set("Todos")
        self.woo_link_filter.set("Todos")
        self._render_items()

    def _open_edit_dialog(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showwarning(
                "Seleccion requerida",
                "Selecciona un articulo del inventario para modificarlo.",
            )
            return
        InventoryEditDialog(self, self.store, item, self._load_items)

    def _open_supplier_orders_dialog(self) -> None:
        SupplierOrdersDialog(self, self.store, self._load_items)

    def _open_history_dialog(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showwarning(
                "Seleccion requerida",
                "Selecciona un articulo del inventario para ver su historico.",
            )
            return
        InventoryHistoryDialog(self, self.store, item)

    def _open_heca_availability_dialog(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showwarning(
                "Seleccion requerida",
                "Selecciona un articulo del Mapa Maestro para ver su disponibilidad.",
            )
            return
        HecaAvailabilityDialog(self, self.store, item)

    def _confirm_supplier_reception(self) -> None:
        item = self._selected_item()
        if item is None:
            messagebox.showwarning(
                "Seleccion requerida",
                "Selecciona un articulo con pedido proveedor pendiente.",
            )
            return
        qty = self.store._to_float(item.get("supplier_order_qty"))
        last_cost = self.store._to_float(item.get("order_calculated_price"))
        if qty <= 0:
            messagebox.showwarning(
                "Sin pedido pendiente",
                "Este articulo no tiene unidades pendientes en Pedido proveedor.",
            )
            return
        if last_cost <= 0:
            messagebox.showwarning(
                "Sin coste calculado",
                "Este articulo no tiene Precio Calculado de Pedido válido para actualizar el promedio.",
            )
            return
        stock_tienda = self.store._to_float(item.get("store_stock"))
        stock_almacenes = self.store._to_float(item.get("warehouse_stock"))
        stock_actual = stock_tienda + stock_almacenes
        avg_actual = self.store._to_float(item.get("weighted_average_cost"))
        if avg_actual <= 0 and self.store._to_float(item.get("order_calculated_price")) > 0 and stock_actual > 0:
            avg_actual = last_cost
        if stock_actual > 0 and avg_actual > 0:
            nuevo_promedio = ((stock_actual * avg_actual) + (qty * last_cost)) / (stock_actual + qty)
        else:
            nuevo_promedio = last_cost
        mensaje = (
            f"Articulo: {item.get('item_id')} | {item.get('name')}\n\n"
            f"Stock actual total: {self._format_number(stock_actual)}\n"
            f"  - Tienda/exposición: {self._format_number(stock_tienda)}\n"
            f"  - Almacenes: {self._format_number(stock_almacenes)}\n"
            f"Pedido proveedor a recibir: {self._format_number(qty)}\n"
            f"Último coste pedido: {self._format_price(last_cost)}\n"
            f"Coste promedio actual: {self._format_price(avg_actual) if avg_actual > 0 else 'Sin promedio'}\n"
            f"Nuevo coste promedio: {self._format_price(nuevo_promedio)}\n\n"
            "Si confirmas, se añadirá el pedido al stock, se actualizará "
            "el Coste Promedio Ponderado y se limpiará el Pedido proveedor pendiente de este articulo.\n\n"
            "No se modifica WooCommerce ni Heca."
        )
        if not messagebox.askyesno("Confirmar recepción de proveedor", mensaje):
            return
        try:
            self.store.confirm_supplier_reception(int(item["item_id"]))
        except Exception as exc:
            messagebox.showerror("Recepción no guardada", str(exc))
            return
        self._load_items()
        messagebox.showinfo("Recepción confirmada", "Se actualizó stock, coste promedio y pedido pendiente del articulo.")

    def _selected_item(self) -> dict[str, object] | None:
        selected = self.table.selection()
        if not selected:
            return None
        values = self.table.item(selected[0], "values")
        if not values:
            return None
        item_id = int(values[0])
        row = self.store.get_item(item_id)
        if row is None:
            return None
        return dict(row)

    def _primary_supplier_for_item(self, item: dict[str, object]) -> str:
        item_id = int(item.get("item_id") or 0)
        prices = self.store.get_supplier_prices(item_id) if item_id else {}
        preferred = self.store._infer_primary_supplier(item)
        if prices.get(preferred):
            return preferred
        for supplier in ("Ekomat", "Pascal", "Hemei", "Cipta"):
            if prices.get(supplier):
                return supplier
        # Compatibilidad con bases antiguas sin supplier_prices.
        if str(item.get("primary_supplier_price") or "").strip():
            return preferred
        if str(item.get("pascal_price") or "").strip():
            return "Pascal"
        return ""

    def _primary_supplier_price_for_item(self, item: dict[str, object]) -> str:
        supplier = self._primary_supplier_for_item(item)
        if supplier:
            price = self.store.get_supplier_price(int(item.get("item_id") or 0), supplier)
            if price:
                return price
        # Compatibilidad visual.
        if supplier == "Pascal":
            return str(item.get("pascal_price") or "")
        if supplier:
            return str(item.get("primary_supplier_price") or "")
        return ""

    def _suppliers_for_item(self, item: dict[str, object]) -> str:
        """Lista proveedores con precio disponible para mostrar en la tabla principal."""
        try:
            item_id = int(item.get("item_id") or 0)
        except Exception:
            item_id = 0
        prices = self.store.get_supplier_prices(item_id) if item_id else {}

        # Compatibilidad visual con columnas antiguas si supplier_prices aún no está completo.
        if str(item.get("primary_supplier_price") or "").strip():
            preferred = self.store._infer_primary_supplier(item)
            prices.setdefault(preferred, str(item.get("primary_supplier_price") or ""))
        if str(item.get("pascal_price") or "").strip():
            prices.setdefault("Pascal", str(item.get("pascal_price") or ""))

        ordered = []
        for supplier in ("Ekomat", "Pascal", "Hemei", "Cipta"):
            value = str(prices.get(supplier) or "").strip()
            if value and value.upper() != "NO ESTA":
                ordered.append(supplier)
        return " / ".join(ordered)

    def _supplier_prices_display_for_item(self, item: dict[str, object]) -> str:
        """Muestra precios por proveedor sin obligar a abrir la ficha."""
        try:
            item_id = int(item.get("item_id") or 0)
        except Exception:
            item_id = 0
        prices = self.store.get_supplier_prices(item_id) if item_id else {}

        if str(item.get("primary_supplier_price") or "").strip():
            preferred = self.store._infer_primary_supplier(item)
            prices.setdefault(preferred, str(item.get("primary_supplier_price") or ""))
        if str(item.get("pascal_price") or "").strip():
            prices.setdefault("Pascal", str(item.get("pascal_price") or ""))

        parts = []
        for supplier in ("Ekomat", "Pascal", "Hemei", "Cipta"):
            value = str(prices.get(supplier) or "").strip()
            if value and value.upper() != "NO ESTA":
                parts.append(f"{supplier}: {self._format_price(value)}")
        return " | ".join(parts)

    def _format_number(self, value: object) -> str:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:.6f}".rstrip("0").rstrip(".")

    def _format_price(self, value: object) -> str:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:.2f} €"


class HecaAvailabilityDialog(tk.Toplevel):
    def __init__(
        self,
        parent: InventoryApp,
        store: InventoryStore,
        item: dict[str, object],
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.item = item
        self.title(f"Disponibilidad Heca {item['item_id']}")
        self.geometry("980x560")
        self.minsize(840, 440)
        self.configure(bg=C_BG)
        self.transient(parent)
        self.grab_set()
        self._build_layout()
        self._load_availability()

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text=f"{self.item['item_id']} | {self.item['name']}",
            style="Section.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            container,
            text=(
                "Disponibilidad leida desde la ultima exportacion importada de Heca. "
                "No modifica Heca ni WooCommerce."
            ),
            style="Status.TLabel",
            wraplength=880,
        ).pack(anchor=tk.W, pady=(4, 12))

        summary = ttk.Frame(container, style="Panel.TFrame", padding=(10, 8))
        summary.pack(fill=tk.X, pady=(0, 10))
        self.summary_text = tk.StringVar(value="Cargando disponibilidad...")
        ttk.Label(summary, textvariable=self.summary_text, style="Section.TLabel").pack(anchor=tk.W)

        table_frame = ttk.Frame(container, style="Panel.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = (
            "warehouse_code",
            "warehouse",
            "quantity",
            "quantity_reserved",
            "quantity_requested",
            "quantity_supplier_ordered",
        )
        headings = {
            "warehouse_code": "Codigo",
            "warehouse": "Almacen",
            "quantity": "Disponible",
            "quantity_reserved": "Reservado",
            "quantity_requested": "Pedido cliente",
            "quantity_supplier_ordered": "Pedido proveedor",
        }
        widths = {
            "warehouse_code": 80,
            "warehouse": 260,
            "quantity": 120,
            "quantity_reserved": 120,
            "quantity_requested": 140,
            "quantity_supplier_ordered": 150,
        }
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings")
        for column in columns:
            self.table.heading(column, text=headings[column], anchor=tk.CENTER)
            self.table.column(column, width=widths[column], minwidth=70, anchor=tk.CENTER)
        self.table.tag_configure("nonzero", background="#ECFDF5")
        self.table.tag_configure("zero", background="#F9FAFB")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        button_row = ttk.Frame(container)
        button_row.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(button_row, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def _load_availability(self) -> None:
        rows = self.store.get_heca_availability(int(self.item["item_id"]))
        for current in self.table.get_children():
            self.table.delete(current)
        total = 0.0
        store_total = 0.0
        warehouse_total = 0.0
        for row in rows:
            quantity = float(row.get("quantity") or 0)
            total += quantity
            warehouse_code = int(row.get("warehouse_code") or 0)
            if warehouse_code in (2, 9):
                store_total += quantity
            else:
                warehouse_total += quantity
            tag = "nonzero" if abs(quantity) > 1e-9 else "zero"
            self.table.insert(
                "",
                tk.END,
                values=(
                    row.get("warehouse_code") or "",
                    row.get("warehouse") or "",
                    self._format_number(row.get("quantity")),
                    self._format_number(row.get("quantity_reserved")),
                    self._format_number(row.get("quantity_requested")),
                    self._format_number(row.get("quantity_supplier_ordered")),
                ),
                tags=(tag,),
            )
        if rows:
            self.summary_text.set(
                f"Total Heca: {self._format_number(total)} | "
                f"Tienda/exposicion: {self._format_number(store_total)} | "
                f"Almacenes: {self._format_number(warehouse_total)}"
            )
        else:
            self.summary_text.set(
                "No hay datos de Heca importados para este articulo. Usa 'Importar Heca' primero."
            )

    def _format_number(self, value: object) -> str:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:.6f}".rstrip("0").rstrip(".")


class InventoryEditDialog(tk.Toplevel):
    def __init__(
        self,
        parent: InventoryApp,
        store: InventoryStore,
        item: dict[str, object],
        on_saved: object,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.item = item
        self.on_saved = on_saved
        self.title(f"Modificar articulo {item['item_id']}")
        self.geometry("800x720")
        self.minsize(700, 620)
        self.configure(bg=C_BG)
        self.transient(parent)
        self.grab_set()

        self.vars = {
            "name": tk.StringVar(value=str(item["name"] or "")),
            "cubic_meters": tk.StringVar(value=self._value(item["cubic_meters"])),
            "rotation_c": tk.StringVar(value=self._value(item["rotation_c"])),
            "packages": tk.StringVar(value=self._value(item["packages"])),
            "primary_supplier_price": tk.StringVar(
                value=str(item["primary_supplier_price"] or "")
            ),
            "pascal_price": tk.StringVar(value=str(item["pascal_price"] or "")),
            "supplier_ekomat": tk.StringVar(value=str(self.store.get_supplier_price(int(item["item_id"]), "Ekomat") or "")),
            "supplier_pascal": tk.StringVar(value=str(self.store.get_supplier_price(int(item["item_id"]), "Pascal") or item["pascal_price"] or "")),
            "supplier_hemei": tk.StringVar(value=str(self.store.get_supplier_price(int(item["item_id"]), "Hemei") or "")),
            "supplier_cipta": tk.StringVar(value=str(self.store.get_supplier_price(int(item["item_id"]), "Cipta") or "")),
            "order_calculated_price": tk.StringVar(value=self._value(item.get("order_calculated_price"))),
            "family": tk.StringVar(value=str(item.get("family") or "")),
            "subgroup": tk.StringVar(value=str(item.get("subgroup") or "")),
            "size": tk.StringVar(value=str(item.get("size") or "")),
            "materials": tk.StringVar(value=str(item.get("materials") or "")),
            "commercial_status": tk.StringVar(value=str(item.get("commercial_status") or "Normal")),
            "is_pack": tk.BooleanVar(value=bool(item.get("is_pack"))),
            "store_stock": tk.StringVar(value=self._value(item.get("store_stock"))),
            "warehouse_stock": tk.StringVar(value=self._value(item.get("warehouse_stock"))),
            "heca_reference": tk.StringVar(value=str(item.get("heca_reference") or "")),
            "notes": tk.StringVar(value=str(item.get("notes") or "")),
            "woo_link_status": tk.StringVar(value=str(item.get("woo_link_status") or "Sin enlazar")),
            "woo_id": tk.StringVar(value=self._value(item.get("woo_id"))),
            "woo_sku": tk.StringVar(value=str(item.get("woo_sku") or "")),
            "woo_name": tk.StringVar(value=str(item.get("woo_name") or "")),
            "woo_price": tk.StringVar(value=str(item.get("woo_price") or "")),
            "woo_categories": tk.StringVar(value=str(item.get("woo_categories") or "")),
        }

        self._build_layout()

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text=f"Codigo {self.item['item_id']}",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))

        body = ttk.Frame(container)
        body.pack(fill=tk.BOTH, expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        canvas = tk.Canvas(body, bg=C_BG, highlightthickness=0, bd=0, takefocus=1)
        y_scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=y_scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")

        form_host = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=form_host, anchor="nw")

        def _sync_scroll_region(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        def _on_mousewheel(event) -> None:
            # El binding queda ligado al canvas vivo, no a toda la app. Así evitamos
            # callbacks fantasma cuando se cierra esta ventana y se destruye el canvas.
            try:
                if canvas.winfo_exists():
                    delta = int(-1 * (event.delta / 120))
                    if delta:
                        canvas.yview_scroll(delta, "units")
            except tk.TclError:
                return

        form_host.bind("<Configure>", _sync_scroll_region)
        canvas.bind("<Configure>", _sync_width)
        canvas.bind("<Enter>", lambda _event: canvas.focus_set())
        canvas.bind("<MouseWheel>", _on_mousewheel)

        form = ttk.Frame(form_host)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)

        fields = [
            ("Articulo", "name", "editable"),
            ("Familia", "family", "editable"),
            ("Subgrupo", "subgroup", "editable"),
            ("Medida A x L x H", "size", "editable"),
            ("Materiales", "materials", "editable"),
            ("Estado comercial", "commercial_status", "combo"),
            ("Stock tienda", "store_stock", "editable"),
            ("Stock almacenes", "warehouse_stock", "editable"),
            ("M3", "cubic_meters", "editable"),
            ("Rotacion C", "rotation_c", "editable"),
            ("Bultos", "packages", "editable"),
            ("Precio Ekomat", "supplier_ekomat", "editable"),
            ("Precio Pascal", "supplier_pascal", "editable"),
            ("Precio Hemei", "supplier_hemei", "editable"),
            ("Precio Cipta", "supplier_cipta", "editable"),
            ("Último coste pedido", "order_calculated_price", "readonly"),
            ("Coste Promedio Ponderado", "weighted_average_cost", "readonly"),
            ("Referencia Heca", "heca_reference", "editable"),
            ("Notas", "notes", "editable"),
        ]
        for row, (label, key, mode) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if mode == "combo":
                widget = ttk.Combobox(
                    form,
                    textvariable=self.vars[key],
                    values=["Normal", "Outlet", "Oferta", "Revisar"],
                    state="readonly",
                )
            else:
                widget = ttk.Entry(
                    form,
                    textvariable=self.vars[key],
                    state="readonly" if mode == "readonly" else "normal",
                )
            widget.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)

        ttk.Label(form, text="Es pack").grid(row=len(fields), column=0, sticky="w", pady=4)
        ttk.Checkbutton(form, variable=self.vars["is_pack"]).grid(
            row=len(fields), column=1, sticky="w", padx=(12, 0), pady=4
        )

        woo_start = len(fields) + 1
        ttk.Separator(form).grid(row=woo_start, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        ttk.Label(form, text="Datos enlazados desde WooCommerce", style="Section.TLabel").grid(
            row=woo_start + 1, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        woo_fields = [
            ("Estado enlace Woo", "woo_link_status"),
            ("SKU Woo", "woo_sku"),
            ("Precio Woo", "woo_price"),
        ]
        for offset, (label, key) in enumerate(woo_fields, start=woo_start + 2):
            ttk.Label(form, text=label).grid(row=offset, column=0, sticky="w", pady=3)
            widget = ttk.Entry(form, textvariable=self.vars[key], state="readonly")
            widget.grid(row=offset, column=1, sticky="ew", padx=(12, 0), pady=3)

        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(16, 0))

        ttk.Button(actions, text="Aceptar", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(
            side=tk.RIGHT,
            padx=(0, 8),
        )

    def _save(self) -> None:
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showerror("Dato requerido", "El articulo necesita un nombre.")
            return

        try:
            item = {
                "item_id": self.item["item_id"],
                "name": name,
                "cubic_meters": self._optional_float("cubic_meters"),
                "rotation_c": self._optional_float("rotation_c"),
                "packages": self._optional_int("packages"),
                "primary_supplier_price": (
                    self.vars["supplier_ekomat"].get().strip()
                    or self.vars["supplier_hemei"].get().strip()
                    or self.vars["supplier_cipta"].get().strip()
                ),
                "pascal_price": self.vars["supplier_pascal"].get().strip(),
                "order_calculated_price": self._optional_float("order_calculated_price"),
                "weighted_average_cost": self._optional_float("weighted_average_cost"),
                "family": self.vars["family"].get().strip(),
                "subgroup": self.vars["subgroup"].get().strip(),
                "size": self.vars["size"].get().strip(),
                "materials": self.vars["materials"].get().strip(),
                "commercial_status": self.vars["commercial_status"].get().strip() or "Normal",
                "is_pack": 1 if self.vars["is_pack"].get() else 0,
                "store_stock": self._optional_float("store_stock"),
                "warehouse_stock": self._optional_float("warehouse_stock"),
                "heca_reference": self.vars["heca_reference"].get().strip(),
                "notes": self.vars["notes"].get().strip(),
            }
        except ValueError as exc:
            messagebox.showerror("Dato no valido", str(exc))
            return

        self.store.update_item(item)
        self.store.update_supplier_prices(
            int(self.item["item_id"]),
            {
                "Ekomat": self.vars["supplier_ekomat"].get().strip(),
                "Pascal": self.vars["supplier_pascal"].get().strip(),
                "Hemei": self.vars["supplier_hemei"].get().strip(),
                "Cipta": self.vars["supplier_cipta"].get().strip(),
            },
            source="manual",
        )
        self.on_saved()
        self.destroy()

    def _optional_float(self, key: str) -> float | None:
        value = self.vars[key].get().strip().replace(",", ".")
        if not value:
            return None
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{key} debe ser numerico.") from exc

    def _optional_int(self, key: str) -> int | None:
        value = self.vars[key].get().strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError("Bultos debe ser un numero entero.") from exc

    def _value(self, value: object) -> str:
        if value in (None, ""):
            return ""
        return str(value)


class InventoryHistoryDialog(tk.Toplevel):
    def __init__(
        self,
        parent: InventoryApp,
        store: InventoryStore,
        item: dict[str, object],
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.item = item
        self.title(f"Historico articulo {item['item_id']}")
        self.geometry("980x520")
        self.minsize(840, 420)
        self.configure(bg=C_BG)
        self.transient(parent)
        self.grab_set()
        self._build_layout()
        self._load_history()

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text=f"{self.item['item_id']} | {self.item['name']}",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))

        table_frame = ttk.Frame(container, style="Panel.TFrame")
        table_frame.pack(fill=tk.BOTH, expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = (
            "created_at",
            "field_name",
            "old_value",
            "new_value",
            "change_source",
            "notes",
        )
        headings = {
            "created_at": "Fecha",
            "field_name": "Campo",
            "old_value": "Valor anterior",
            "new_value": "Valor nuevo",
            "change_source": "Origen",
            "notes": "Notas",
            "woo_link_status": "Estado enlace Woo",
            "woo_id": "ID Woo",
            "woo_sku": "SKU Woo",
            "woo_name": "Nombre Woo",
        }
        widths = {
            "created_at": 145,
            "field_name": 160,
            "old_value": 150,
            "new_value": 150,
            "change_source": 120,
            "notes": 260,
        }

        self.table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        for column in columns:
            self.table.heading(column, text=headings[column], anchor=tk.CENTER)
            self.table.column(column, width=widths[column], minwidth=80, anchor=tk.CENTER)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        footer = ttk.Frame(container, padding=(0, 12, 0, 0))
        footer.pack(fill=tk.X)
        self.status_text = tk.StringVar()
        ttk.Label(footer, textvariable=self.status_text, style="Status.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Button(footer, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def _load_history(self) -> None:
        rows = self.store.list_history(int(self.item["item_id"]))
        for row in rows:
            self.table.insert(
                "",
                tk.END,
                values=(
                    row["created_at"],
                    row["field_name"],
                    row["old_value"] or "",
                    row["new_value"] or "",
                    self._source_label(str(row["change_source"])),
                    row["notes"] or "",
                ),
            )
        self.status_text.set(f"Movimientos registrados: {len(rows)}")

    def _source_label(self, value: str) -> str:
        labels = {
            "manual": "Manual",
            "excel_import": "Importacion Excel",
        }
        return labels.get(value, value)



class SupplierOrdersDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, store: InventoryStore, on_change) -> None:
        super().__init__(master)
        self.store = store
        self.on_change = on_change
        self.title("Pedidos de Proveedor")
        self.geometry("980x560")
        self.minsize(850, 460)
        self.configure(bg=C_BG)
        apply_theme(self)
        self._build()
        self._load()
        self.transient(master)
        self.lift()
        self.focus_force()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(container, text="Pedidos de Proveedor", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            container,
            text="Aquí se guardan los pedidos calculados. Solo al confirmar recepción se actualiza stock y coste promedio ponderado.",
            style="Status.TLabel",
        ).pack(anchor=tk.W, pady=(4, 10))
        table_frame = ttk.Frame(container)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("order_id", "provider", "order_file", "status", "lines", "total_items", "pending_qty", "total_cost", "updated_at")
        headings = {
            "order_id": "ID",
            "provider": "Proveedor",
            "order_file": "Pedido / Archivo",
            "status": "Estado",
            "lines": "Líneas",
            "total_items": "Unidades pedidas",
            "pending_qty": "Pendientes",
            "total_cost": "Coste total",
            "updated_at": "Actualizado",
        }
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.table.heading(col, text=headings[col], anchor=tk.CENTER)
            self.table.column(col, width=130, minwidth=70, anchor=tk.CENTER)
        self.table.column("order_id", width=60)
        self.table.column("order_file", width=230)
        y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind("<Double-1>", lambda _e: self._open_detail())
        footer = ttk.Frame(container, padding=(0, 10, 0, 0))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Abrir detalle", command=self._open_detail).pack(side=tk.LEFT)
        ttk.Button(footer, text="Actualizar", command=self._load).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(footer, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def _load(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        self.rows = [dict(r) for r in self.store.list_supplier_orders()]
        for row in self.rows:
            self.table.insert("", tk.END, values=(
                row["order_id"], row["provider"], row["order_file"], row["status"], row["lines"],
                self._fmt(row["total_items"]), self._fmt(row["pending_qty"]), self._money(row["total_cost"]), row["updated_at"] or "",
            ))

    def _selected_order_id(self) -> int | None:
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("Selección requerida", "Selecciona un pedido de proveedor.", parent=self)
            return None
        return int(self.table.item(selected[0], "values")[0])

    def _open_detail(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        SupplierOrderDetailDialog(self, self.store, order_id, self._after_change)

    def _after_change(self) -> None:
        self._load()
        self.on_change()

    def _fmt(self, value: object) -> str:
        try:
            val = float(value or 0)
            return str(int(val)) if val.is_integer() else f"{val:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return "0"

    def _money(self, value: object) -> str:
        try:
            return f"{float(value or 0):.2f} €"
        except Exception:
            return "—"


class SupplierOrderDetailDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, store: InventoryStore, order_id: int, on_change) -> None:
        super().__init__(master)
        self.store = store
        self.order_id = int(order_id)
        self.on_change = on_change
        self.title(f"Detalle pedido proveedor #{order_id}")
        self.geometry("1080x600")
        self.minsize(920, 480)
        self.configure(bg=C_BG)
        apply_theme(self)
        self._build()
        self._load()
        self.transient(master)
        self.lift()
        self.focus_force()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        ttk.Label(container, text="Detalle del Pedido de Proveedor", style="Title.TLabel").pack(anchor=tk.W)
        self.summary = tk.StringVar(value="")
        ttk.Label(container, textvariable=self.summary, style="Status.TLabel").pack(anchor=tk.W, pady=(4, 10))
        table_frame = ttk.Frame(container)
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("line_id", "code", "name", "ordered", "received", "pending", "unit_cost", "line_cost", "avg_cost")
        headings = {
            "line_id": "Línea",
            "code": "Código",
            "name": "Artículo",
            "ordered": "Pedido",
            "received": "Recibido",
            "pending": "Pendiente",
            "unit_cost": "Coste pedido",
            "line_cost": "Coste línea",
            "avg_cost": "Coste promedio actual",
        }
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        for col in columns:
            self.table.heading(col, text=headings[col], anchor=tk.CENTER)
            self.table.column(col, width=130, minwidth=70, anchor=tk.CENTER)
        self.table.column("name", width=260)
        y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        footer = ttk.Frame(container, padding=(0, 10, 0, 0))
        footer.pack(fill=tk.X)
        ttk.Button(footer, text="Modificar línea", command=self._edit_line).pack(side=tk.LEFT)
        ttk.Button(footer, text="Recepción parcial", command=self._partial_receipt).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(footer, text="Confirmar recepción total", command=self._confirm_receipt).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(footer, text="Cancelar pedido", command=self._cancel_order).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(footer, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def _load(self) -> None:
        for row in self.table.get_children():
            self.table.delete(row)
        self.rows = [dict(r) for r in self.store.list_supplier_order_items(self.order_id)]
        total_ordered = sum(float(r.get("quantity_ordered") or 0) for r in self.rows)
        total_received = sum(float(r.get("quantity_received") or 0) for r in self.rows)
        total_pending = sum(float(r.get("pending_qty") or 0) for r in self.rows)
        total_cost = sum(float(r.get("line_cost") or 0) for r in self.rows)
        self.summary.set(
            f"Recibidos {self._fmt(total_received)} / {self._fmt(total_ordered)} · "
            f"Pendientes: {self._fmt(total_pending)} · Coste total: {self._money(total_cost)}"
        )
        for row in self.rows:
            self.table.insert("", tk.END, values=(
                row["id"], row["item_code"], row["item_name"] or "", self._fmt(row["quantity_ordered"]),
                self._fmt(row["quantity_received"]), self._fmt(row["pending_qty"]), self._money(row["unit_cost"]),
                self._money(row["line_cost"]), self._money(row["weighted_average_cost"]),
            ))

    def _selected_line(self) -> dict[str, object] | None:
        selected = self.table.selection()
        if not selected:
            messagebox.showwarning("Selección requerida", "Selecciona una línea del pedido.", parent=self)
            return None
        line_id = int(self.table.item(selected[0], "values")[0])
        for row in self.rows:
            if int(row["id"]) == line_id:
                return row
        return None

    def _edit_line(self) -> None:
        row = self._selected_line()
        if row is None:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Modificar línea del pedido")
        dialog.geometry("420x240")
        dialog.configure(bg=C_BG)
        apply_theme(dialog)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=str(row.get("item_name") or row.get("item_code")), style="Section.TLabel", wraplength=360).pack(anchor=tk.W, pady=(0, 12))
        qty_var = tk.StringVar(value=self._fmt(row["quantity_ordered"]))
        cost_var = tk.StringVar(value=str(row["unit_cost"] or ""))
        ttk.Label(frame, text="Cantidad pedida:").pack(anchor=tk.W)
        ttk.Entry(frame, textvariable=qty_var).pack(fill=tk.X, pady=(2, 8))
        ttk.Label(frame, text="Coste unitario pedido:").pack(anchor=tk.W)
        ttk.Entry(frame, textvariable=cost_var).pack(fill=tk.X, pady=(2, 12))
        def accept() -> None:
            try:
                qty = float(qty_var.get().replace(",", "."))
                cost = float(cost_var.get().replace(",", "."))
                self.store.update_supplier_order_line(int(row["id"]), qty, cost)
            except Exception as exc:
                messagebox.showerror("No se pudo modificar", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._load()
            self.on_change()
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Aceptar", command=accept).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _partial_receipt(self) -> None:
        row = self._selected_line()
        if row is None:
            return
        pending = float(row.get("pending_qty") or 0)
        if pending <= 0:
            messagebox.showinfo("Recepción parcial", "Esta línea no tiene unidades pendientes por recibir.", parent=self)
            return

        dialog = tk.Toplevel(self)
        dialog.title("Recepción parcial")
        dialog.geometry("460x300")
        dialog.minsize(420, 280)
        dialog.configure(bg=C_BG)
        apply_theme(dialog)
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=str(row.get("item_name") or row.get("item_code")), style="Section.TLabel", wraplength=400).pack(anchor=tk.W, pady=(0, 12))
        ttk.Label(
            frame,
            text=(
                f"Pedido: {self._fmt(row.get('quantity_ordered'))} · "
                f"Recibido: {self._fmt(row.get('quantity_received'))} · "
                f"Pendiente: {self._fmt(row.get('pending_qty'))}"
            ),
            style="Status.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))

        qty_var = tk.StringVar(value=self._fmt(pending))
        ttk.Label(frame, text="Cantidad recibida ahora:").pack(anchor=tk.W)
        qty_entry = ttk.Entry(frame, textvariable=qty_var)
        qty_entry.pack(fill=tk.X, pady=(2, 10))
        ttk.Label(
            frame,
            text="Al aceptar se sumará esta cantidad al stock y se recalculará el Coste Promedio Ponderado solo para esta línea.",
            style="Status.TLabel",
            wraplength=400,
        ).pack(anchor=tk.W, pady=(0, 12))

        def accept() -> None:
            try:
                qty = float(qty_var.get().strip().replace(",", "."))
                result = self.store.confirm_supplier_order_line_receipt(int(row["id"]), qty)
            except Exception as exc:
                messagebox.showerror("No se pudo recibir", str(exc), parent=dialog)
                return
            dialog.destroy()
            messagebox.showinfo(
                "Recepción parcial guardada",
                (
                    f"Código: {result.get('codigo')}\n"
                    f"Recibido ahora: {self._fmt(result.get('recibido_ahora'))}\n"
                    f"Pendiente nuevo: {self._fmt(result.get('pendiente_nuevo'))}\n"
                    f"Nuevo coste promedio: {self._money(result.get('coste_promedio_nuevo'))}"
                ),
                parent=self,
            )
            self._load()
            self.on_change()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(buttons, text="Aceptar", command=accept).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 8))
        qty_entry.focus_set()

    def _confirm_receipt(self) -> None:
        if not messagebox.askyesno(
            "Confirmar recepción",
            "Se sumarán las unidades pendientes al stock de almacenes y se recalculará el Coste Promedio Ponderado.\n\nNo se modifica WooCommerce ni Heca. ¿Continuar?",
            parent=self,
        ):
            return
        try:
            result = self.store.confirm_supplier_order_receipt(self.order_id)
        except Exception as exc:
            messagebox.showerror("Recepción no confirmada", str(exc), parent=self)
            return
        messagebox.showinfo("Recepción confirmada", f"Líneas recibidas: {len(result['received_lines'])}", parent=self)
        self._load()
        self.on_change()

    def _cancel_order(self) -> None:
        if not messagebox.askyesno("Cancelar pedido", "El pedido dejará de contar como pendiente. No se modifica stock. ¿Continuar?", parent=self):
            return
        try:
            self.store.cancel_supplier_order(self.order_id)
        except Exception as exc:
            messagebox.showerror("No se pudo cancelar", str(exc), parent=self)
            return
        self._load()
        self.on_change()

    def _fmt(self, value: object) -> str:
        try:
            val = float(value or 0)
            return str(int(val)) if val.is_integer() else f"{val:.2f}".rstrip("0").rstrip(".")
        except Exception:
            return "0"

    def _money(self, value: object) -> str:
        try:
            return f"{float(value or 0):.2f} €"
        except Exception:
            return "—"


def run_inventory_app(settings: Settings) -> None:
    app = InventoryApp(settings)
    app.mainloop()

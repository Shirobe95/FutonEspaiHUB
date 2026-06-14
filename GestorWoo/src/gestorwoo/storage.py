from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    woo_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sku TEXT,
    type TEXT,
    status TEXT,
    regular_price TEXT,
    sale_price TEXT,
    price TEXT,
    stock_status TEXT,
    stock_quantity REAL,
    categories_json TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_type ON products(type);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);

CREATE TABLE IF NOT EXISTS categories (
    woo_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT,
    parent_woo_id INTEGER,
    count INTEGER,
    raw_json TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories(parent_woo_id);
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);

CREATE TABLE IF NOT EXISTS product_categories (
    product_woo_id INTEGER NOT NULL,
    category_woo_id INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    PRIMARY KEY(product_woo_id, category_woo_id),
    FOREIGN KEY(product_woo_id) REFERENCES products(woo_id),
    FOREIGN KEY(category_woo_id) REFERENCES categories(woo_id)
);

CREATE INDEX IF NOT EXISTS idx_product_categories_product
ON product_categories(product_woo_id);

CREATE INDEX IF NOT EXISTS idx_product_categories_category
ON product_categories(category_woo_id);

CREATE TABLE IF NOT EXISTS product_variations (
    woo_id INTEGER PRIMARY KEY,
    parent_woo_id INTEGER NOT NULL,
    parent_name TEXT NOT NULL,
    sku TEXT,
    status TEXT,
    regular_price TEXT,
    sale_price TEXT,
    price TEXT,
    stock_status TEXT,
    stock_quantity REAL,
    attributes_json TEXT NOT NULL,
    attributes_label TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_woo_id) REFERENCES products(woo_id)
);

CREATE INDEX IF NOT EXISTS idx_variations_parent ON product_variations(parent_woo_id);
CREATE INDEX IF NOT EXISTS idx_variations_sku ON product_variations(sku);
CREATE INDEX IF NOT EXISTS idx_variations_status ON product_variations(status);

CREATE TABLE IF NOT EXISTS manual_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_woo_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    components_total REAL NOT NULL DEFAULT 0,
    pricing_mode TEXT NOT NULL DEFAULT 'current',
    discount_percent REAL,
    discount_amount REAL,
    final_price REAL NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(pack_woo_id) REFERENCES products(woo_id)
);

CREATE TABLE IF NOT EXISTS manual_pack_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    item_kind TEXT NOT NULL CHECK(item_kind IN ('product', 'variation')),
    item_woo_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(pack_id) REFERENCES manual_packs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pack_items_pack ON manual_pack_items(pack_id);
CREATE INDEX IF NOT EXISTS idx_pack_items_item ON manual_pack_items(item_kind, item_woo_id);

CREATE TABLE IF NOT EXISTS price_change_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_kind TEXT NOT NULL CHECK(item_kind IN ('product', 'variation')),
    item_woo_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    old_price REAL NOT NULL,
    new_price REAL NOT NULL,
    delta REAL NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    published_at TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_price_change_item
ON price_change_proposals(item_kind, item_woo_id);

CREATE TABLE IF NOT EXISTS product_classifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_kind TEXT NOT NULL CHECK(item_kind IN ('product', 'variation')),
    item_woo_id INTEGER NOT NULL,
    sku TEXT,
    family TEXT NOT NULL DEFAULT 'Otros / Sin clasificar',
    subgroup TEXT NOT NULL DEFAULT 'Sin subgrupo',
    size TEXT NOT NULL DEFAULT 'Sin medida',
    materials TEXT NOT NULL DEFAULT '',
    colors TEXT NOT NULL DEFAULT '',
    commercial_status TEXT NOT NULL DEFAULT 'Normal',
    is_pack INTEGER NOT NULL DEFAULT 0,
    reviewed INTEGER NOT NULL DEFAULT 0,
    classification_source TEXT NOT NULL DEFAULT 'auto',
    needs_review INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(item_kind, item_woo_id)
);

CREATE INDEX IF NOT EXISTS idx_product_classifications_family
ON product_classifications(family);

CREATE INDEX IF NOT EXISTS idx_product_classifications_subgroup
ON product_classifications(subgroup);

CREATE INDEX IF NOT EXISTS idx_product_classifications_status
ON product_classifications(commercial_status);

"""


class ProductStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_manual_pack_columns(connection)
            self._ensure_price_proposal_columns(connection)
            self._ensure_product_classification_columns(connection)

    def upsert_products(self, products: Iterable[dict[str, Any]]) -> int:
        product_list = list(products)
        rows = [self._product_to_row(product) for product in product_list]
        category_rows = [
            {
                "product_woo_id": product["id"],
                "category_woo_id": category.get("id"),
                "category_name": category.get("name") or "",
            }
            for product in product_list
            for category in product.get("categories", [])
            if category.get("id") is not None
        ]
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO products (
                    woo_id, name, sku, type, status, regular_price, sale_price, price,
                    stock_status, stock_quantity, categories_json, raw_json, synced_at
                )
                VALUES (
                    :woo_id, :name, :sku, :type, :status, :regular_price, :sale_price,
                    :price, :stock_status, :stock_quantity, :categories_json,
                    :raw_json, CURRENT_TIMESTAMP
                )
                ON CONFLICT(woo_id) DO UPDATE SET
                    name = excluded.name,
                    sku = excluded.sku,
                    type = excluded.type,
                    status = excluded.status,
                    regular_price = excluded.regular_price,
                    sale_price = excluded.sale_price,
                    price = excluded.price,
                    stock_status = excluded.stock_status,
                    stock_quantity = excluded.stock_quantity,
                    categories_json = excluded.categories_json,
                    raw_json = excluded.raw_json,
                    synced_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
            connection.executemany(
                "DELETE FROM product_categories WHERE product_woo_id = ?",
                [(row["woo_id"],) for row in rows],
            )
            if category_rows:
                connection.executemany(
                    """
                    INSERT INTO product_categories (
                        product_woo_id, category_woo_id, category_name
                    )
                    VALUES (:product_woo_id, :category_woo_id, :category_name)
                    ON CONFLICT(product_woo_id, category_woo_id) DO UPDATE SET
                        category_name = excluded.category_name
                    """,
                    category_rows,
                )
        return len(rows)

    def upsert_categories(self, categories: Iterable[dict[str, Any]]) -> int:
        rows = [self._category_to_row(category) for category in categories]
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO categories (
                    woo_id, name, slug, parent_woo_id, count, raw_json, synced_at
                )
                VALUES (
                    :woo_id, :name, :slug, :parent_woo_id, :count,
                    :raw_json, CURRENT_TIMESTAMP
                )
                ON CONFLICT(woo_id) DO UPDATE SET
                    name = excluded.name,
                    slug = excluded.slug,
                    parent_woo_id = excluded.parent_woo_id,
                    count = excluded.count,
                    raw_json = excluded.raw_json,
                    synced_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def upsert_variations(
        self,
        parent_product: dict[str, Any],
        variations: Iterable[dict[str, Any]],
    ) -> int:
        rows = [
            self._variation_to_row(parent_product, variation)
            for variation in variations
        ]
        if not rows:
            return 0

        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO product_variations (
                    woo_id, parent_woo_id, parent_name, sku, status, regular_price,
                    sale_price, price, stock_status, stock_quantity, attributes_json,
                    attributes_label, raw_json, synced_at
                )
                VALUES (
                    :woo_id, :parent_woo_id, :parent_name, :sku, :status,
                    :regular_price, :sale_price, :price, :stock_status,
                    :stock_quantity, :attributes_json, :attributes_label,
                    :raw_json, CURRENT_TIMESTAMP
                )
                ON CONFLICT(woo_id) DO UPDATE SET
                    parent_woo_id = excluded.parent_woo_id,
                    parent_name = excluded.parent_name,
                    sku = excluded.sku,
                    status = excluded.status,
                    regular_price = excluded.regular_price,
                    sale_price = excluded.sale_price,
                    price = excluded.price,
                    stock_status = excluded.stock_status,
                    stock_quantity = excluded.stock_quantity,
                    attributes_json = excluded.attributes_json,
                    attributes_label = excluded.attributes_label,
                    raw_json = excluded.raw_json,
                    synced_at = CURRENT_TIMESTAMP
                """,
                rows,
            )
        return len(rows)

    def list_products(self, limit: int = 25) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT woo_id, name, sku, type, status, price, stock_status, synced_at
                    FROM products
                    ORDER BY name COLLATE NOCASE
                    LIMIT ?
                    """,
                    (limit,),
                )
            )

    def list_all_products(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        woo_id,
                        name,
                        sku,
                        type,
                        status,
                        regular_price,
                        sale_price,
                        price,
                        stock_status,
                        stock_quantity,
                        synced_at
                    FROM products
                    ORDER BY name COLLATE NOCASE
                    """
                )
            )

    def list_catalog_items(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        base.*,
                        COALESCE(cls.family, 'Otros / Sin clasificar') AS family,
                        COALESCE(cls.subgroup, 'Sin subgrupo') AS subgroup,
                        COALESCE(cls.size, 'Sin medida') AS size,
                        COALESCE(cls.materials, '') AS materials,
                        COALESCE(cls.colors, '') AS colors,
                        COALESCE(cls.commercial_status, 'Normal') AS commercial_status,
                        COALESCE(cls.is_pack, 0) AS is_pack,
                        COALESCE(cls.reviewed, 0) AS reviewed,
                        COALESCE(cls.classification_source, 'pendiente') AS classification_source,
                        COALESCE(cls.needs_review, 1) AS needs_review,
                        COALESCE(cls.notes, '') AS classification_notes
                    FROM (
                        SELECT
                            'product' AS item_kind,
                            woo_id,
                            NULL AS parent_woo_id,
                            name,
                            sku,
                            type,
                            status,
                            regular_price,
                            sale_price,
                            price,
                            stock_status,
                            stock_quantity,
                            '' AS attributes_label,
                            COALESCE((
                                SELECT GROUP_CONCAT(category_name, ' / ')
                                FROM product_categories
                                WHERE product_woo_id = products.woo_id
                            ), '') AS categories_label,
                            raw_json,
                            NULL AS parent_raw_json,
                            synced_at
                        FROM products
                        UNION ALL
                        SELECT
                            'variation' AS item_kind,
                            woo_id,
                            parent_woo_id,
                            parent_name AS name,
                            sku,
                            'variation' AS type,
                            status,
                            regular_price,
                            sale_price,
                            price,
                            stock_status,
                            stock_quantity,
                            attributes_label,
                            COALESCE((
                                SELECT GROUP_CONCAT(category_name, ' / ')
                                FROM product_categories
                                WHERE product_woo_id = product_variations.parent_woo_id
                            ), '') AS categories_label,
                            raw_json,
                            (
                                SELECT raw_json
                                FROM products
                                WHERE products.woo_id = product_variations.parent_woo_id
                            ) AS parent_raw_json,
                            synced_at
                        FROM product_variations
                    ) AS base
                    LEFT JOIN product_classifications AS cls
                        ON cls.item_kind = base.item_kind
                       AND cls.item_woo_id = base.woo_id
                    ORDER BY base.name COLLATE NOCASE,
                        base.item_kind,
                        base.attributes_label COLLATE NOCASE
                    """
                )
            )

    def list_pack_candidates(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        woo_id,
                        name,
                        sku,
                        price,
                        COALESCE((
                            SELECT GROUP_CONCAT(category_name, ' / ')
                            FROM product_categories
                            WHERE product_woo_id = products.woo_id
                        ), '') AS categories_label
                    FROM products
                    ORDER BY name COLLATE NOCASE
                    """
                )
            )

    def save_manual_pack(
        self,
        pack: dict[str, Any],
        items: Iterable[dict[str, Any]],
    ) -> int:
        item_rows = list(items)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM manual_packs WHERE pack_woo_id = ?",
                (pack["pack_woo_id"],),
            ).fetchone()
            if row:
                pack_id = int(row["id"])
                connection.execute(
                    """
                    UPDATE manual_packs
                    SET
                        name = :name,
                        components_total = :components_total,
                        pricing_mode = :pricing_mode,
                        discount_percent = :discount_percent,
                        discount_amount = :discount_amount,
                        final_price = :final_price,
                        notes = :notes,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """,
                    {**pack, "id": pack_id},
                )
                connection.execute(
                    "DELETE FROM manual_pack_items WHERE pack_id = ?",
                    (pack_id,),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO manual_packs (
                        pack_woo_id, name, components_total, pricing_mode,
                        discount_percent, discount_amount, final_price, notes
                    )
                    VALUES (
                        :pack_woo_id, :name, :components_total, :pricing_mode,
                        :discount_percent, :discount_amount, :final_price, :notes
                    )
                    """,
                    pack,
                )
                pack_id = int(cursor.lastrowid)

            connection.executemany(
                """
                INSERT INTO manual_pack_items (
                    pack_id, item_kind, item_woo_id, quantity, notes
                )
                VALUES (
                    :pack_id, :item_kind, :item_woo_id, :quantity, :notes
                )
                """,
                [{**item, "pack_id": pack_id} for item in item_rows],
            )
        return pack_id

    def list_variations_for_product(self, product_woo_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        woo_id,
                        parent_woo_id,
                        parent_name AS name,
                        sku,
                        price,
                        regular_price,
                        sale_price,
                        stock_status,
                        attributes_label
                    FROM product_variations
                    WHERE parent_woo_id = ?
                    ORDER BY attributes_label COLLATE NOCASE
                    """,
                    (product_woo_id,),
                )
            )

    def list_manual_pack_impacts(
        self,
        item_kind: str,
        item_woo_id: int,
        new_price: float,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    manual_packs.id AS pack_id,
                    manual_packs.pack_woo_id,
                    manual_packs.name,
                    manual_packs.pricing_mode,
                    manual_packs.discount_percent,
                    manual_packs.discount_amount,
                    manual_packs.final_price AS stored_final_price,
                    manual_pack_items.quantity,
                    manual_pack_items.item_kind,
                    manual_pack_items.item_woo_id
                FROM manual_packs
                JOIN manual_pack_items ON manual_pack_items.pack_id = manual_packs.id
                WHERE manual_pack_items.item_kind = ?
                  AND manual_pack_items.item_woo_id = ?
                ORDER BY manual_packs.name COLLATE NOCASE
                """,
                (item_kind, item_woo_id),
            ).fetchall()

            impacts = []
            for row in rows:
                current_total = self._pack_components_total(connection, int(row["pack_id"]))
                quantity = float(row["quantity"] or 0)
                old_component_price = self._item_price(
                    connection,
                    str(row["item_kind"]),
                    int(row["item_woo_id"]),
                )
                new_total = current_total - (old_component_price * quantity) + (
                    new_price * quantity
                )
                impacts.append(
                    {
                        "pack_id": row["pack_id"],
                        "pack_woo_id": row["pack_woo_id"],
                        "name": row["name"],
                        "quantity": quantity,
                        "current_components_total": current_total,
                        "new_components_total": new_total,
                        "current_final_price": self._pack_final_price(row, current_total),
                        "new_final_price": self._pack_final_price(row, new_total),
                        "pricing_mode": row["pricing_mode"],
                    }
                )
            return impacts

    def list_related_variation_impacts(
        self,
        item_kind: str,
        item_woo_id: int,
        new_price: float,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            source = self._catalog_item(connection, item_kind, item_woo_id)
            if not source:
                return []

            source_text = " ".join(
                str(source.get(key) or "")
                for key in ("name", "attributes_label", "categories_label")
            ).lower()
            dimensions = self._dimension_tokens(source_text)
            keywords = self._relation_keywords(source_text)
            source_price = self._to_float(source.get("price"))
            delta = new_price - source_price

            rows = connection.execute(
                """
                SELECT
                    'variation' AS item_kind,
                    product_variations.woo_id,
                    product_variations.parent_woo_id,
                    product_variations.parent_name AS name,
                    product_variations.price,
                    product_variations.attributes_label,
                    COALESCE((
                        SELECT GROUP_CONCAT(category_name, ' / ')
                        FROM product_categories
                        WHERE product_woo_id = product_variations.parent_woo_id
                    ), '') AS categories_label
                FROM product_variations
                ORDER BY product_variations.parent_name COLLATE NOCASE,
                    product_variations.attributes_label COLLATE NOCASE
                """
            ).fetchall()

            impacts = []
            for row in rows:
                if int(row["woo_id"]) == item_woo_id and item_kind == "variation":
                    continue
                target_text = " ".join(
                    str(row[key] or "")
                    for key in ("name", "attributes_label", "categories_label")
                ).lower()
                reason = self._related_reason(source_text, target_text, dimensions, keywords)
                if not reason:
                    continue
                quantity_factor = self._relation_quantity(target_text)
                current_price = self._to_float(row["price"])
                proposed_price = max(current_price + (delta * quantity_factor), 0)
                displayed_reason = reason
                if quantity_factor != 1:
                    displayed_reason = f"{reason} x{quantity_factor:g}"
                impacts.append(
                    {
                        "item_kind": "variation",
                        "woo_id": row["woo_id"],
                        "parent_woo_id": row["parent_woo_id"],
                        "name": row["name"],
                        "attributes_label": row["attributes_label"],
                        "categories_label": row["categories_label"],
                        "current_price": current_price,
                        "proposed_price": proposed_price,
                        "delta": proposed_price - current_price,
                        "quantity_factor": quantity_factor,
                        "reason": displayed_reason,
                    }
                )
            return impacts

    def save_price_change_proposal(
        self,
        proposal: dict[str, Any],
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO price_change_proposals (
                    item_kind, item_woo_id, name, old_price, new_price, delta, notes
                )
                VALUES (
                    :item_kind, :item_woo_id, :name, :old_price, :new_price, :delta, :notes
                )
                """,
                proposal,
            )
            return int(cursor.lastrowid)

    def save_price_change_proposals(
        self,
        proposals: Iterable[dict[str, Any]],
    ) -> int:
        rows = list(proposals)
        if not rows:
            return 0
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO price_change_proposals (
                    item_kind, item_woo_id, name, old_price, new_price, delta, notes
                )
                VALUES (
                    :item_kind, :item_woo_id, :name, :old_price, :new_price, :delta, :notes
                )
                """,
                rows,
            )
        return len(rows)

    def upsert_pending_price_change_proposals(
        self,
        proposals: Iterable[dict[str, Any]],
    ) -> int:
        """Crea o actualiza propuestas pendientes evitando duplicados por item."""
        rows = list(proposals)
        if not rows:
            return 0
        with self.connect() as connection:
            for proposal in rows:
                existing = connection.execute(
                    """
                    SELECT id
                    FROM price_change_proposals
                    WHERE status = 'pending'
                      AND item_kind = ?
                      AND item_woo_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (proposal["item_kind"], proposal["item_woo_id"]),
                ).fetchone()
                old_price = float(proposal["old_price"])
                new_price = float(proposal["new_price"])
                delta = new_price - old_price
                payload = {**proposal, "delta": delta}
                if existing is None:
                    connection.execute(
                        """
                        INSERT INTO price_change_proposals (
                            item_kind, item_woo_id, name, old_price, new_price, delta, notes
                        )
                        VALUES (
                            :item_kind, :item_woo_id, :name, :old_price, :new_price, :delta, :notes
                        )
                        """,
                        payload,
                    )
                else:
                    connection.execute(
                        """
                        UPDATE price_change_proposals
                        SET name = ?, old_price = ?, new_price = ?, delta = ?, notes = ?
                        WHERE id = ?
                        """,
                        (
                            proposal["name"],
                            old_price,
                            new_price,
                            delta,
                            proposal.get("notes"),
                            int(existing["id"]),
                        ),
                    )
        return len(rows)

    def list_pending_price_changes(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT
                        id,
                        item_kind,
                        item_woo_id,
                        name,
                        old_price,
                        new_price,
                        delta,
                        notes,
                        created_at,
                        CASE
                            WHEN item_kind = 'variation' THEN (
                                SELECT parent_woo_id
                                FROM product_variations
                                WHERE product_variations.woo_id = price_change_proposals.item_woo_id
                            )
                            ELSE NULL
                        END AS parent_woo_id
                    FROM price_change_proposals
                    WHERE status = 'pending'
                    ORDER BY created_at, id
                    """
                )
            )


    def update_price_change_proposal_review(
        self,
        proposal_id: int,
        new_price: float | None = None,
        notes: str | None = None,
        status: str | None = None,
    ) -> None:
        assignments: list[str] = []
        params: list[Any] = []
        if new_price is not None:
            row = None
            with self.connect() as connection:
                row = connection.execute(
                    "SELECT old_price FROM price_change_proposals WHERE id = ?",
                    (proposal_id,),
                ).fetchone()
            if row is None:
                return
            old_price = float(row["old_price"] or 0)
            assignments.extend(["new_price = ?", "delta = ?"])
            params.extend([float(new_price), float(new_price) - old_price])
        if notes is not None:
            assignments.append("notes = ?")
            params.append(notes[:1000])
        if status is not None:
            assignments.append("status = ?")
            params.append(status)
        if not assignments:
            return
        params.append(proposal_id)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE price_change_proposals SET {', '.join(assignments)} WHERE id = ?",
                params,
            )

    def mark_price_change_published(self, proposal_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE price_change_proposals
                SET status = 'published', published_at = CURRENT_TIMESTAMP, error_message = NULL
                WHERE id = ?
                """,
                (proposal_id,),
            )

    def mark_price_change_failed(self, proposal_id: int, error_message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE price_change_proposals
                SET status = 'failed', error_message = ?
                WHERE id = ?
                """,
                (error_message[:1000], proposal_id),
            )

    def apply_local_price_change(self, item_kind: str, item_woo_id: int, price: float) -> None:
        table = "products" if item_kind == "product" else "product_variations"
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE {table}
                SET price = ?, regular_price = ?, synced_at = CURRENT_TIMESTAMP
                WHERE woo_id = ?
                """,
                (f"{price:.2f}", f"{price:.2f}", item_woo_id),
            )

    def upsert_product_classification(self, classification: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO product_classifications (
                    item_kind, item_woo_id, sku, family, subgroup, size, materials, colors,
                    commercial_status, is_pack, reviewed, classification_source,
                    needs_review, notes, updated_at
                )
                VALUES (
                    :item_kind, :item_woo_id, :sku, :family, :subgroup, :size,
                    :materials, :colors, :commercial_status, :is_pack, :reviewed,
                    :classification_source, :needs_review, :notes, CURRENT_TIMESTAMP
                )
                ON CONFLICT(item_kind, item_woo_id) DO UPDATE SET
                    sku = excluded.sku,
                    family = excluded.family,
                    subgroup = excluded.subgroup,
                    size = excluded.size,
                    materials = excluded.materials,
                    colors = excluded.colors,
                    commercial_status = excluded.commercial_status,
                    is_pack = excluded.is_pack,
                    reviewed = excluded.reviewed,
                    classification_source = excluded.classification_source,
                    needs_review = excluded.needs_review,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                classification,
            )

    def mark_classification_reviewed(self, item_kind: str, item_woo_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE product_classifications
                SET reviewed = 1,
                    needs_review = 0,
                    classification_source = CASE
                        WHEN classification_source = 'auto' THEN 'manual'
                        ELSE classification_source
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE item_kind = ? AND item_woo_id = ?
                """,
                (item_kind, item_woo_id),
            )

    def existing_reviewed_classification_keys(self) -> set[tuple[str, int]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT item_kind, item_woo_id
                FROM product_classifications
                WHERE reviewed = 1
                """
            ).fetchall()
        return {(str(row["item_kind"]), int(row["item_woo_id"])) for row in rows}

    def classification_filter_values(self) -> dict[str, list[str]]:
        with self.connect() as connection:
            values: dict[str, list[str]] = {}
            for column in ("family", "subgroup", "commercial_status"):
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT {column} AS value
                    FROM product_classifications
                    WHERE TRIM(COALESCE({column}, '')) <> ''
                    ORDER BY {column} COLLATE NOCASE
                    """
                ).fetchall()
                values[column] = [str(row["value"]) for row in rows]
        return values

    def count_products(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM products").fetchone()
            return int(row["total"])

    def count_variations(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM product_variations"
            ).fetchone()
            return int(row["total"])

    def count_categories(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM categories").fetchone()
            return int(row["total"])

    def list_categories(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT woo_id, name, parent_woo_id, count
                    FROM categories
                    ORDER BY name COLLATE NOCASE
                    """
                )
            )

    def product_type_counts(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute(
                    """
                    SELECT type, COUNT(*) AS total
                    FROM products
                    GROUP BY type
                    ORDER BY total DESC
                    """
                )
            )

    def _ensure_product_classification_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(product_classifications)").fetchall()
        }
        columns = {
            "sku": "TEXT",
            "family": "TEXT NOT NULL DEFAULT 'Otros / Sin clasificar'",
            "subgroup": "TEXT NOT NULL DEFAULT 'Sin subgrupo'",
            "size": "TEXT NOT NULL DEFAULT 'Sin medida'",
            "materials": "TEXT NOT NULL DEFAULT ''",
            "colors": "TEXT NOT NULL DEFAULT ''",
            "commercial_status": "TEXT NOT NULL DEFAULT 'Normal'",
            "is_pack": "INTEGER NOT NULL DEFAULT 0",
            "reviewed": "INTEGER NOT NULL DEFAULT 0",
            "classification_source": "TEXT NOT NULL DEFAULT 'auto'",
            "needs_review": "INTEGER NOT NULL DEFAULT 1",
            "notes": "TEXT",
            "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE product_classifications ADD COLUMN {name} {definition}"
                )

    def _ensure_manual_pack_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(manual_packs)").fetchall()
        }
        columns = {
            "components_total": "REAL NOT NULL DEFAULT 0",
            "pricing_mode": "TEXT NOT NULL DEFAULT 'current'",
            "discount_percent": "REAL",
            "discount_amount": "REAL",
            "final_price": "REAL NOT NULL DEFAULT 0",
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE manual_packs ADD COLUMN {name} {definition}")

    def _ensure_price_proposal_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(price_change_proposals)").fetchall()
        }
        columns = {
            "status": "TEXT NOT NULL DEFAULT 'pending'",
            "published_at": "TEXT",
            "error_message": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE price_change_proposals ADD COLUMN {name} {definition}"
                )

    def _item_price(
        self,
        connection: sqlite3.Connection,
        item_kind: str,
        item_woo_id: int,
    ) -> float:
        table = "products" if item_kind == "product" else "product_variations"
        row = connection.execute(
            f"SELECT price FROM {table} WHERE woo_id = ?",
            (item_woo_id,),
        ).fetchone()
        return self._to_float(row["price"] if row else None)

    def _catalog_item(
        self,
        connection: sqlite3.Connection,
        item_kind: str,
        item_woo_id: int,
    ) -> dict[str, Any] | None:
        if item_kind == "product":
            row = connection.execute(
                """
                SELECT
                    'product' AS item_kind,
                    woo_id,
                    NULL AS parent_woo_id,
                    name,
                    price,
                    '' AS attributes_label,
                    COALESCE((
                        SELECT GROUP_CONCAT(category_name, ' / ')
                        FROM product_categories
                        WHERE product_woo_id = products.woo_id
                    ), '') AS categories_label
                FROM products
                WHERE woo_id = ?
                """,
                (item_woo_id,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT
                    'variation' AS item_kind,
                    woo_id,
                    parent_woo_id,
                    parent_name AS name,
                    price,
                    attributes_label,
                    COALESCE((
                        SELECT GROUP_CONCAT(category_name, ' / ')
                        FROM product_categories
                        WHERE product_woo_id = product_variations.parent_woo_id
                    ), '') AS categories_label
                FROM product_variations
                WHERE woo_id = ?
                """,
                (item_woo_id,),
            ).fetchone()
        return dict(row) if row else None

    def _pack_components_total(
        self,
        connection: sqlite3.Connection,
        pack_id: int,
    ) -> float:
        total = 0.0
        rows = connection.execute(
            """
            SELECT item_kind, item_woo_id, quantity
            FROM manual_pack_items
            WHERE pack_id = ?
            """,
            (pack_id,),
        ).fetchall()
        for row in rows:
            total += self._item_price(
                connection,
                str(row["item_kind"]),
                int(row["item_woo_id"]),
            ) * float(row["quantity"] or 0)
        return total

    def _pack_final_price(self, pack: sqlite3.Row, components_total: float) -> float:
        mode = pack["pricing_mode"]
        if mode == "percent":
            return max(
                components_total * (1 - self._to_float(pack["discount_percent"]) / 100),
                0,
            )
        if mode == "amount":
            return max(components_total - self._to_float(pack["discount_amount"]), 0)
        return self._to_float(pack["stored_final_price"])

    def _to_float(self, value: object) -> float:
        if value is None:
            return 0.0
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return 0.0

    def _dimension_tokens(self, text: str) -> set[str]:
        tokens = set()
        for match in re.finditer(r"(\d{2,3})\s*x\s*(\d{2,3})(?:\s*x\s*[\d,.]+)?", text):
            width, length = match.group(1), match.group(2)
            tokens.add(f"{width}x{length}")
        return tokens

    def _relation_keywords(self, text: str) -> set[str]:
        candidates = {
            "tatami",
            "tatamis",
            "futon",
            "futón",
            "macao",
            "tokio",
            "provence",
        }
        return {keyword for keyword in candidates if keyword in text}

    def _related_reason(
        self,
        source_text: str,
        target_text: str,
        dimensions: set[str],
        keywords: set[str],
    ) -> str:
        matching_dimensions = sorted(
            dimension
            for dimension in dimensions
            if self._dimension_is_tatami_related(target_text, dimension)
        )
        matching_keywords = sorted(keyword for keyword in keywords if keyword in target_text)
        if dimensions:
            if matching_dimensions and ("tatami" in target_text or "tatamis" in target_text):
                return "dimension " + ", ".join(matching_dimensions)
            return ""
        if matching_dimensions and ("tatami" in target_text or "tatamis" in target_text):
            return "dimension " + ", ".join(matching_dimensions)
        if "tatami" in source_text and "tatami" in target_text and matching_keywords:
            return "termino " + ", ".join(matching_keywords)
        if "futon" in source_text and ("futon" in target_text or "futón" in target_text):
            return "termino futon"
        if "futón" in source_text and ("futon" in target_text or "futón" in target_text):
            return "termino futon"
        return ""

    def _relation_quantity(self, target_text: str) -> float:
        match = re.search(r"con\s+(\d+)\s+tatamis?", target_text)
        if match:
            return float(match.group(1))
        return 1.0

    def _dimension_is_tatami_related(self, target_text: str, dimension: str) -> bool:
        escaped = re.escape(dimension)
        patterns = [
            rf"tatamis?\s+de\s+{escaped}",
            rf"medidas?\s+estructura\s*:\s*{escaped}",
            rf"medida\s+estructura\s*:\s*{escaped}",
        ]
        return any(re.search(pattern, target_text) for pattern in patterns)

    def _product_to_row(self, product: dict[str, Any]) -> dict[str, Any]:
        categories = [
            {"id": category.get("id"), "name": category.get("name")}
            for category in product.get("categories", [])
        ]
        return {
            "woo_id": product["id"],
            "name": product.get("name") or "",
            "sku": product.get("sku") or None,
            "type": product.get("type") or None,
            "status": product.get("status") or None,
            "regular_price": product.get("regular_price") or None,
            "sale_price": product.get("sale_price") or None,
            "price": product.get("price") or None,
            "stock_status": product.get("stock_status") or None,
            "stock_quantity": product.get("stock_quantity"),
            "categories_json": json.dumps(categories, ensure_ascii=False),
            "raw_json": json.dumps(product, ensure_ascii=False),
        }

    def _category_to_row(self, category: dict[str, Any]) -> dict[str, Any]:
        return {
            "woo_id": category["id"],
            "name": category.get("name") or "",
            "slug": category.get("slug") or None,
            "parent_woo_id": category.get("parent") or None,
            "count": category.get("count"),
            "raw_json": json.dumps(category, ensure_ascii=False),
        }

    def _variation_to_row(
        self,
        parent_product: dict[str, Any],
        variation: dict[str, Any],
    ) -> dict[str, Any]:
        attributes = [
            {
                "id": attribute.get("id"),
                "name": attribute.get("name"),
                "option": attribute.get("option"),
            }
            for attribute in variation.get("attributes", [])
        ]
        label_parts = [
            f"{attribute['name']}: {attribute['option']}"
            for attribute in attributes
            if attribute.get("name") and attribute.get("option")
        ]
        return {
            "woo_id": variation["id"],
            "parent_woo_id": parent_product["id"],
            "parent_name": parent_product.get("name") or "",
            "sku": variation.get("sku") or None,
            "status": variation.get("status") or None,
            "regular_price": variation.get("regular_price") or None,
            "sale_price": variation.get("sale_price") or None,
            "price": variation.get("price") or None,
            "stock_status": variation.get("stock_status") or None,
            "stock_quantity": variation.get("stock_quantity"),
            "attributes_json": json.dumps(attributes, ensure_ascii=False),
            "attributes_label": " / ".join(label_parts),
            "raw_json": json.dumps(variation, ensure_ascii=False),
        }

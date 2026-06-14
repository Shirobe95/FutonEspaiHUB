# UI ERP Pedidos v14 - Fix Inventario detalle y revisión supplier_prices

## Fix Inventario

Se corrigió el error `AttributeError: 'tuple' object has no attribute 'name'`.

Causa: el parche anterior guardaba `(index, item)` en `item_by_iid`, pero el detalle de Inventario espera recibir directamente un `InventoryItem`.

Solución: `item_by_iid[iid] = item`.

## Filas de cálculo de pedido

Se mantiene la lógica reforzada de Pedidos v13 para colorear filas con errores/warnings.

## Precios de proveedor en base local

Revisión SQLite encontrada:

```json
[
  {
    "path": "GestorWoo/data/gestorwoo.sqlite3",
    "tables": [
      "price_change_proposals",
      "supplier_prices",
      "supplier_pending_order_items",
      "supplier_orders",
      "supplier_order_items"
    ],
    "counts": {
      "price_change_proposals": 7,
      "supplier_prices": 435,
      "supplier_pending_order_items": 0,
      "supplier_orders": 0,
      "supplier_order_items": 0
    },
    "schemas": {
      "price_change_proposals": [
        "id",
        "item_kind",
        "item_woo_id",
        "name",
        "old_price",
        "new_price",
        "delta",
        "notes",
        "created_at",
        "status",
        "published_at",
        "error_message"
      ],
      "supplier_prices": [
        "item_id",
        "supplier",
        "price",
        "currency",
        "source",
        "updated_at"
      ],
      "supplier_pending_order_items": [
        "provider",
        "order_file",
        "item_id",
        "item_code",
        "quantity",
        "updated_at"
      ],
      "supplier_orders": [
        "order_id",
        "provider",
        "order_file",
        "status",
        "total_items",
        "total_cost",
        "notes",
        "created_at",
        "updated_at"
      ],
      "supplier_order_items": [
        "id",
        "order_id",
        "item_id",
        "item_code",
        "item_name",
        "quantity_ordered",
        "quantity_received",
        "unit_cost",
        "line_cost",
        "updated_at"
      ]
    },
    "samples": {
      "price_change_proposals": [
        [
          1,
          "product",
          12087,
          "Testing 1",
          100.0,
          125.0,
          25.0,
          null,
          "2026-04-27 16:23:03",
          "published",
          "2026-04-27 16:25:04",
          null
        ],
        [
          2,
          "product",
          12088,
          "Testing 2",
          150.0,
          187.5,
          37.5,
          null,
          "2026-04-27 16:23:30",
          "published",
          "2026-04-27 16:25:05",
          null
        ],
        [
          3,
          "product",
          12055,
          "Prodcut Test",
          100.0,
          120.0,
          20.0,
          null,
          "2026-04-27 16:24:11",
          "failed",
          null,
          "Error WooCommerce 400: {\"code\":\"woocommerce_rest_product_invalid_id\",\"message\":\"ID no v\\u00e1lido.\",\"data\":{\"status\":400}}"
        ]
      ],
      "supplier_prices": [
        [
          302002,
          "Hemei",
          "93",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 15:34:07"
        ],
        [
          302009,
          "Hemei",
          "83.41",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 15:34:07"
        ],
        [
          302018,
          "Hemei",
          "107.5",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 15:34:07"
        ]
      ]
    }
  },
  {
    "path": "GestorWoo/data/backups/gestorwoo-20260428-164836-manual.sqlite3",
    "tables": [
      "price_change_proposals"
    ],
    "counts": {
      "price_change_proposals": 7
    },
    "schemas": {
      "price_change_proposals": [
        "id",
        "item_kind",
        "item_woo_id",
        "name",
        "old_price",
        "new_price",
        "delta",
        "notes",
        "created_at",
        "status",
        "published_at",
        "error_message"
      ]
    },
    "samples": {
      "price_change_proposals": [
        [
          1,
          "product",
          12087,
          "Testing 1",
          100.0,
          125.0,
          25.0,
          null,
          "2026-04-27 16:23:03",
          "published",
          "2026-04-27 16:25:04",
          null
        ],
        [
          2,
          "product",
          12088,
          "Testing 2",
          150.0,
          187.5,
          37.5,
          null,
          "2026-04-27 16:23:30",
          "published",
          "2026-04-27 16:25:05",
          null
        ],
        [
          3,
          "product",
          12055,
          "Prodcut Test",
          100.0,
          120.0,
          20.0,
          null,
          "2026-04-27 16:24:11",
          "failed",
          null,
          "Error WooCommerce 400: {\"code\":\"woocommerce_rest_product_invalid_id\",\"message\":\"ID no v\\u00e1lido.\",\"data\":{\"status\":400}}"
        ]
      ]
    }
  },
  {
    "path": "GestorWoo/data/backups/gestorwoo-20260428-164919-pre-restore.sqlite3",
    "tables": [
      "price_change_proposals"
    ],
    "counts": {
      "price_change_proposals": 7
    },
    "schemas": {
      "price_change_proposals": [
        "id",
        "item_kind",
        "item_woo_id",
        "name",
        "old_price",
        "new_price",
        "delta",
        "notes",
        "created_at",
        "status",
        "published_at",
        "error_message"
      ]
    },
    "samples": {
      "price_change_proposals": [
        [
          1,
          "product",
          12087,
          "Testing 1",
          100.0,
          125.0,
          25.0,
          null,
          "2026-04-27 16:23:03",
          "published",
          "2026-04-27 16:25:04",
          null
        ],
        [
          2,
          "product",
          12088,
          "Testing 2",
          150.0,
          187.5,
          37.5,
          null,
          "2026-04-27 16:23:30",
          "published",
          "2026-04-27 16:25:05",
          null
        ],
        [
          3,
          "product",
          12055,
          "Prodcut Test",
          100.0,
          120.0,
          20.0,
          null,
          "2026-04-27 16:24:11",
          "failed",
          null,
          "Error WooCommerce 400: {\"code\":\"woocommerce_rest_product_invalid_id\",\"message\":\"ID no v\\u00e1lido.\",\"data\":{\"status\":400}}"
        ]
      ]
    }
  },
  {
    "path": "GestorWoo/data/backups/gestorwoo-20260527-121643-pre-sync-woocommerce.sqlite3",
    "tables": [
      "price_change_proposals",
      "supplier_prices",
      "supplier_pending_order_items",
      "supplier_orders",
      "supplier_order_items"
    ],
    "counts": {
      "price_change_proposals": 7,
      "supplier_prices": 435,
      "supplier_pending_order_items": 0,
      "supplier_orders": 0,
      "supplier_order_items": 0
    },
    "schemas": {
      "price_change_proposals": [
        "id",
        "item_kind",
        "item_woo_id",
        "name",
        "old_price",
        "new_price",
        "delta",
        "notes",
        "created_at",
        "status",
        "published_at",
        "error_message"
      ],
      "supplier_prices": [
        "item_id",
        "supplier",
        "price",
        "currency",
        "source",
        "updated_at"
      ],
      "supplier_pending_order_items": [
        "provider",
        "order_file",
        "item_id",
        "item_code",
        "quantity",
        "updated_at"
      ],
      "supplier_orders": [
        "order_id",
        "provider",
        "order_file",
        "status",
        "total_items",
        "total_cost",
        "notes",
        "created_at",
        "updated_at"
      ],
      "supplier_order_items": [
        "id",
        "order_id",
        "item_id",
        "item_code",
        "item_name",
        "quantity_ordered",
        "quantity_received",
        "unit_cost",
        "line_cost",
        "updated_at"
      ]
    },
    "samples": {
      "price_change_proposals": [
        [
          1,
          "product",
          12087,
          "Testing 1",
          100.0,
          125.0,
          25.0,
          null,
          "2026-04-27 16:23:03",
          "published",
          "2026-04-27 16:25:04",
          null
        ],
        [
          2,
          "product",
          12088,
          "Testing 2",
          150.0,
          187.5,
          37.5,
          null,
          "2026-04-27 16:23:30",
          "published",
          "2026-04-27 16:25:05",
          null
        ],
        [
          3,
          "product",
          12055,
          "Prodcut Test",
          100.0,
          120.0,
          20.0,
          null,
          "2026-04-27 16:24:11",
          "failed",
          null,
          "Error WooCommerce 400: {\"code\":\"woocommerce_rest_product_invalid_id\",\"message\":\"ID no v\\u00e1lido.\",\"data\":{\"status\":400}}"
        ]
      ],
      "supplier_prices": [
        [
          302002,
          "Hemei",
          "93",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 10:14:21"
        ],
        [
          302009,
          "Hemei",
          "83.41",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 10:14:21"
        ],
        [
          302018,
          "Hemei",
          "107.5",
          "EUR",
          "Migrado desde Precio 1",
          "2026-05-27 10:14:21"
        ]
      ]
    }
  }
]
```

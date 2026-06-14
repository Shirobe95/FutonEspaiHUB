from __future__ import annotations

from dataclasses import dataclass

from gestorwoo.config import Settings
from gestorwoo.guard import guarded_database_operation
from gestorwoo.storage import ProductStore
from gestorwoo.woocommerce import WooCommerceClient


@dataclass(frozen=True)
class SyncResult:
    categories_imported: int
    imported: int
    variations_imported: int
    total_local: int
    total_variations: int
    total_categories: int


def sync_products(settings: Settings) -> SyncResult:
    with guarded_database_operation(
        settings,
        "sync_woocommerce",
        module="Inventario WooCommerce",
        action="Actualizar desde WooCommerce",
        details="Sincronizacion de categorias, productos y variaciones hacia la base local.",
        ttl_minutes=45,
        backup_reason="pre-sync-woocommerce",
    ):
        return _sync_products_unlocked(settings)


def _sync_products_unlocked(settings: Settings) -> SyncResult:
    client = WooCommerceClient(
        settings.woocommerce_url,
        settings.consumer_key,
        settings.consumer_secret,
    )
    store = ProductStore(settings.db_path)
    store.init_schema()

    categories_imported = 0
    category_batch = []
    for category in client.iter_categories():
        category_batch.append(category)
        if len(category_batch) >= 100:
            categories_imported += store.upsert_categories(category_batch)
            category_batch.clear()
    categories_imported += store.upsert_categories(category_batch)

    imported = 0
    variations_imported = 0
    batch = []
    variable_products = []
    for product in client.iter_products():
        batch.append(product)
        if product.get("type") == "variable":
            variable_products.append(product)
        if len(batch) >= 100:
            imported += store.upsert_products(batch)
            batch.clear()

    imported += store.upsert_products(batch)

    for product in variable_products:
        variation_batch = []
        for variation in client.iter_product_variations(product["id"]):
            variation_batch.append(variation)
            if len(variation_batch) >= 100:
                variations_imported += store.upsert_variations(product, variation_batch)
                variation_batch.clear()
        variations_imported += store.upsert_variations(product, variation_batch)

    return SyncResult(
        categories_imported=categories_imported,
        imported=imported,
        variations_imported=variations_imported,
        total_local=store.count_products(),
        total_variations=store.count_variations(),
        total_categories=store.count_categories(),
    )

from __future__ import annotations

from dataclasses import dataclass

from gestorwoo.config import Settings
from gestorwoo.guard import guarded_database_operation
from gestorwoo.storage import ProductStore
from gestorwoo.woocommerce import WooCommerceClient, WooCommerceError


@dataclass(frozen=True)
class PublishResult:
    published: int
    failed: int
    errors: list[str]


def publish_pending_price_changes(settings: Settings) -> PublishResult:
    with guarded_database_operation(
        settings,
        "publish_price_changes",
        module="Cambio de Precios WooCommerce",
        action="Publicar cambios de precio en WooCommerce",
        details="Publicacion de propuestas revisadas hacia WooCommerce real.",
        ttl_minutes=30,
        backup_reason="pre-publish-prices",
    ):
        return _publish_pending_price_changes_unlocked(settings)


def _publish_pending_price_changes_unlocked(settings: Settings) -> PublishResult:
    store = ProductStore(settings.db_path)
    store.init_schema()
    client = WooCommerceClient(
        settings.woocommerce_url,
        settings.consumer_key,
        settings.consumer_secret,
    )

    published = 0
    failed = 0
    errors: list[str] = []

    for change in store.list_pending_price_changes():
        try:
            if change["item_kind"] == "product":
                client.update_product_price(int(change["item_woo_id"]), float(change["new_price"]))
            else:
                parent_id = change["parent_woo_id"]
                if parent_id is None:
                    raise WooCommerceError(
                        f"No se encontro producto padre para variacion {change['item_woo_id']}."
                    )
                client.update_variation_price(
                    int(parent_id),
                    int(change["item_woo_id"]),
                    float(change["new_price"]),
                )
        except WooCommerceError as exc:
            failed += 1
            message = f"{change['name']} ({change['item_kind']} {change['item_woo_id']}): {exc}"
            errors.append(message)
            store.mark_price_change_failed(int(change["id"]), str(exc))
            continue

        store.apply_local_price_change(
            str(change["item_kind"]),
            int(change["item_woo_id"]),
            float(change["new_price"]),
        )
        store.mark_price_change_published(int(change["id"]))
        published += 1

    return PublishResult(published=published, failed=failed, errors=errors)

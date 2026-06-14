from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests


class WooCommerceError(RuntimeError):
    pass


class WooCommerceClient:
    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str) -> None:
        if not base_url:
            raise WooCommerceError("Falta WOOCOMMERCE_URL.")
        if not consumer_key or not consumer_secret:
            raise WooCommerceError("Faltan las credenciales de WooCommerce.")

        self.base_url = base_url.rstrip("/")
        self.auth = (consumer_key, consumer_secret)
        self.session = requests.Session()

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> requests.Response:
        url = f"{self.base_url}/wp-json/wc/v3/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, auth=self.auth, params=params, timeout=30)
        except requests.RequestException as exc:
            raise WooCommerceError(f"No se pudo conectar con WooCommerce: {exc}") from exc
        if response.status_code >= 400:
            raise WooCommerceError(
                f"Error WooCommerce {response.status_code}: {response.text[:500]}"
            )
        return response

    def put(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/wp-json/wc/v3/{endpoint.lstrip('/')}"
        try:
            response = self.session.put(url, auth=self.auth, json=payload, timeout=30)
        except requests.RequestException as exc:
            raise WooCommerceError(f"No se pudo conectar con WooCommerce: {exc}") from exc
        if response.status_code >= 400:
            raise WooCommerceError(
                f"Error WooCommerce {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def iter_products(self, per_page: int = 100) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            response = self.get(
                "products",
                params={
                    "per_page": per_page,
                    "page": page,
                    "status": "any",
                },
            )
            products = response.json()
            if not products:
                return

            yield from products

            total_pages = int(response.headers.get("X-WP-TotalPages", "0") or "0")
            if total_pages and page >= total_pages:
                return
            page += 1

    def iter_categories(self, per_page: int = 100) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            response = self.get(
                "products/categories",
                params={
                    "per_page": per_page,
                    "page": page,
                    "hide_empty": "false",
                },
            )
            categories = response.json()
            if not categories:
                return

            yield from categories

            total_pages = int(response.headers.get("X-WP-TotalPages", "0") or "0")
            if total_pages and page >= total_pages:
                return
            page += 1

    def iter_product_variations(
        self,
        product_id: int,
        per_page: int = 100,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            response = self.get(
                f"products/{product_id}/variations",
                params={
                    "per_page": per_page,
                    "page": page,
                    "status": "any",
                },
            )
            variations = response.json()
            if not variations:
                return

            yield from variations

            total_pages = int(response.headers.get("X-WP-TotalPages", "0") or "0")
            if total_pages and page >= total_pages:
                return
            page += 1

    def update_product_pricing(self, product_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """Actualiza campos de precio explícitos y devuelve la respuesta Woo."""
        return self.put(f"products/{product_id}", payload)

    def update_variation_pricing(
        self,
        product_id: int,
        variation_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Actualiza campos de precio explícitos de una variación."""
        return self.put(f"products/{product_id}/variations/{variation_id}", payload)

    def update_product_price(self, product_id: int, price: float) -> dict[str, Any]:
        return self.update_product_pricing(product_id, {"regular_price": f"{price:.2f}", "sale_price": ""})

    def update_variation_price(
        self,
        product_id: int,
        variation_id: int,
        price: float,
    ) -> dict[str, Any]:
        return self.update_variation_pricing(
            product_id,
            variation_id,
            {"regular_price": f"{price:.2f}", "sale_price": ""},
        )

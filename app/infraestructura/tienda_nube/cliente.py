from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import quote

import httpx

from app.dominio.errores import TiendaNubeHTTPError

logger = logging.getLogger(__name__)


class ClienteTiendaNube:
    """Cliente HTTP de bajo nivel para Tienda Nube.

    Responsabilidades:
    - Encapsular autenticación, timeouts y backoff.
    - Exponer métodos explícitos por recurso: producto, variante, stock y categorías.
    - Enriquecer errores HTTP con request/response para que los 422 no queden como caja negra.
    """

    def __init__(
        self,
        *,
        base_url: str,
        store_id: str,
        access_token: str,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.store_id = store_id
        self.access_token = access_token
        self.timeout = httpx.Timeout(timeout_seconds)

    @property
    def headers(self) -> dict[str, str]:
        """Headers obligatorios de Tienda Nube."""

        return {
            "Authentication": f"bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "Silmar Integrador GBP TN",
        }

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Ejecuta requests a Tienda Nube con backoff defensivo.

        Tienda Nube puede responder 429 Too Many Requests cuando se crean,
        actualizan o eliminan muchas categorías/productos en ráfaga. En ese
        caso no debe fallar la operación completa: se espera y se reintenta.
        """

        max_attempts = 6
        base_delay_seconds = 1.25
        response: httpx.Response | None = None

        for attempt in range(1, max_attempts + 1):
            response = await client.request(method, url, **kwargs)
            if response.status_code != 429:
                return response

            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    delay_seconds = max(float(retry_after), base_delay_seconds)
                except ValueError:
                    delay_seconds = base_delay_seconds * attempt
            else:
                delay_seconds = base_delay_seconds * attempt

            await asyncio.sleep(delay_seconds)

        assert response is not None
        return response

    @staticmethod
    def _safe_json_text(payload: Any) -> str | None:
        if payload is None:
            return None
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            return str(payload)

    def _raise_for_status(
        self,
        response: httpx.Response,
        *,
        request_payload: Any = None,
    ) -> None:
        """Levanta errores HTTP con cuerpo de respuesta y payload.

        httpx.HTTPStatusError oculta el detalle más útil de Tienda Nube si no se
        captura `response.text`. Para 422 necesitamos saber exactamente qué campo
        rechazó la API.
        """

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            request_body = self._safe_json_text(request_payload)
            response_text = response.text or ""
            logger.error(
                "tienda_nube_http_error",
                extra={
                    "method": exc.request.method,
                    "url": str(exc.request.url),
                    "status_code": response.status_code,
                    "response_text": response_text[:4000],
                    "request_body": (request_body or "")[:4000],
                },
            )
            raise TiendaNubeHTTPError(
                status_code=response.status_code,
                url=str(exc.request.url),
                response_text=response_text,
                request_body=request_body,
            ) from exc

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Obtiene una orden por su ID interno; devuelve None ante 404."""

        encoded_order_id = quote(str(order_id), safe="")
        url = f"{self.base_url}/{self.store_id}/orders/{encoded_order_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "GET", url, headers=self.headers
            )
            if response.status_code == 404:
                return None
            self._raise_for_status(response)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Tienda Nube devolvió una orden con formato inválido")
            return data

    async def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Busca producto por SKU."""

        encoded_sku = quote(str(sku), safe="")
        url = f"{self.base_url}/{self.store_id}/products/sku/{encoded_sku}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "GET", url, headers=self.headers
            )
            if response.status_code == 404:
                return None
            self._raise_for_status(response)
            return response.json()

    async def get_product(self, product_id: str) -> dict[str, Any] | None:
        """Obtiene producto por ID; devuelve None si no existe."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "GET", url, headers=self.headers
            )
            if response.status_code == 404:
                return None
            self._raise_for_status(response)
            return response.json()

    async def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Crea producto en Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/products"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "POST", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

    async def update_product(
        self, product_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Actualiza datos de producto. No usar para precio/stock de variantes."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "PUT", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

    async def create_variant(
        self, product_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Crea variante para producto existente."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}/variants"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "POST", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

    async def update_variant(
        self,
        *,
        product_id: str,
        variant_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Actualiza precio/SKU/barcode/stock de una variante."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}/variants/{variant_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "PUT", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

    async def hide_product(self, product_id: str) -> dict[str, Any]:
        """Oculta/despublica un producto en Tienda Nube sin eliminarlo."""

        return await self.update_product(product_id, {"published": False})

    async def delete_product(self, product_id: str) -> dict[str, Any]:
        """Elimina un producto de Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "DELETE", url, headers=self.headers
            )
            if response.status_code == 404:
                return {"id": product_id, "estado": "NO_EXISTE_EN_TIENDA_NUBE"}
            self._raise_for_status(response)
            if not response.content:
                return {"id": product_id, "estado": "ELIMINADO"}
            data = response.json()
            if isinstance(data, dict):
                data.setdefault("estado", "ELIMINADO")
                return data
            return {"id": product_id, "estado": "ELIMINADO"}

    async def list_categories(
        self, *, per_page: int = 200, max_pages: int = 10
    ) -> list[dict[str, Any]]:
        """Lista categorias de Tienda Nube con paginacion defensiva."""

        categories: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/{self.store_id}/categories"
                response = await self._request_with_retries(
                    client,
                    "GET",
                    url,
                    headers=self.headers,
                    params={"page": page, "per_page": per_page},
                )
                if response.status_code == 404 and page > 1:
                    break
                self._raise_for_status(response)
                data = response.json()
                if not isinstance(data, list) or not data:
                    break
                categories.extend(data)
                if len(data) < per_page:
                    break
        return categories

    async def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Crea categoria o subcategoria en Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/categories"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "POST", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

    async def list_products(
        self, *, per_page: int = 200, max_pages: int = 100
    ) -> list[dict[str, Any]]:
        """Lista productos de Tienda Nube con paginacion defensiva."""

        products: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/{self.store_id}/products"
                response = await self._request_with_retries(
                    client,
                    "GET",
                    url,
                    headers=self.headers,
                    params={"page": page, "per_page": per_page},
                )
                if response.status_code == 404 and page > 1:
                    break
                self._raise_for_status(response)
                data = response.json()
                if not isinstance(data, list) or not data:
                    break
                products.extend(data)
                if len(data) < per_page:
                    break
        return products

    async def update_product_categories(
        self, product_id: str, category_ids: list[int]
    ) -> dict[str, Any]:
        """Actualiza solo asignación de categorías de un producto."""

        return await self.update_product(product_id, {"categories": category_ids})

    async def delete_category(self, category_id: str) -> dict[str, Any]:
        """Elimina una categoría de Tienda Nube si existe."""

        url = f"{self.base_url}/{self.store_id}/categories/{category_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "DELETE", url, headers=self.headers
            )
            if response.status_code == 404:
                return {"id": category_id, "estado": "NO_EXISTE_EN_TIENDA_NUBE"}
            self._raise_for_status(response)
            if not response.content:
                return {"id": category_id, "estado": "ELIMINADO"}
            data = response.json()
            if isinstance(data, dict):
                data.setdefault("estado", "ELIMINADO")
                return data
            return {"id": category_id, "estado": "ELIMINADO"}

    async def update_variant_stock(
        self, *, product_id: str, variant_id: str, stock: int
    ) -> dict[str, Any]:
        """Actualiza solo stock de una variante de un producto."""

        payload = {"stock": max(0, int(stock)), "stock_management": True}
        return await self.update_variant(
            product_id=product_id, variant_id=variant_id, payload=payload
        )

    async def update_stock(self, variant_id: str, stock: int) -> dict[str, Any]:
        """Compatibilidad legacy. No usar para flujo nuevo: falta product_id."""

        url = f"{self.base_url}/{self.store_id}/products/variants/{variant_id}"
        payload = {"stock": max(0, int(stock)), "stock_management": True}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await self._request_with_retries(
                client, "PUT", url, headers=self.headers, json=payload
            )
            self._raise_for_status(response, request_payload=payload)
            return response.json()

from typing import Any

import httpx


class TiendaNubeClient:
    """Cliente HTTP de bajo nivel para Tienda Nube."""

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

    async def get_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Busca producto por SKU."""

        url = f"{self.base_url}/{self.store_id}/products/sku/{sku}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Crea producto en Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/products"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def update_product(self, product_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Actualiza producto en Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def hide_product(self, product_id: str) -> dict[str, Any]:
        """Oculta/despublica un producto en Tienda Nube sin eliminarlo."""

        return await self.update_product(product_id, {"published": False})

    async def delete_product(self, product_id: str) -> dict[str, Any]:
        """Elimina un producto en Tienda Nube."""

        url = f"{self.base_url}/{self.store_id}/products/{product_id}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(url, headers=self.headers)
            if response.status_code == 404:
                return {"id": product_id, "estado": "NO_EXISTE_EN_TIENDA_NUBE"}
            response.raise_for_status()
            if not response.content:
                return {"id": product_id, "estado": "ELIMINADO"}
            return response.json()

    async def list_categories(self, *, per_page: int = 200, max_pages: int = 10) -> list[dict[str, Any]]:
        """Lista categorias de Tienda Nube con paginacion defensiva."""

        categories: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/{self.store_id}/categories"
                response = await client.get(
                    url,
                    headers=self.headers,
                    params={"page": page, "per_page": per_page},
                )
                response.raise_for_status()
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
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def update_stock(self, variant_id: str, stock: int) -> dict[str, Any]:
        """Actualiza solo stock de una variante."""

        url = f"{self.base_url}/{self.store_id}/products/variants/{variant_id}"
        payload = {"stock": stock}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

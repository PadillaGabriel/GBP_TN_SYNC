from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Any

from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.domain.models.sync_result import SyncResult
from app.domain.ports.publicador_ecommerce import PublicadorEcommerce
from app.infrastructure.tienda_nube.client import TiendaNubeClient
from app.infrastructure.tienda_nube.category_utils import normalize_category_key
from app.infrastructure.tienda_nube.payload_builder import TiendaNubePayloadBuilder


class TiendaNubeAdapter(PublicadorEcommerce):
    """Adaptador de Tienda Nube hacia contrato interno."""

    _category_lock = asyncio.Lock()

    def __init__(
        self,
        *,
        client: TiendaNubeClient,
        image_normalization_enabled: bool = False,
        image_normalization_base_url: str = "",
        image_normalization_canvas_size: int = 1600,
    ) -> None:
        self.client = client
        self.builder = TiendaNubePayloadBuilder(
            image_normalization_enabled=image_normalization_enabled,
            image_normalization_base_url=image_normalization_base_url,
            image_normalization_canvas_size=image_normalization_canvas_size,
        )

    async def crear_o_actualizar_producto(self, producto: Producto) -> SyncResult:
        """Crea o actualiza producto completo en Tienda Nube."""

        existing = await self.client.get_product_by_sku(producto.sku)
        category_ids = await self._ensure_category_tree(producto)
        payload = self.builder.build_product_payload(producto, category_ids=category_ids)
        if existing is None:
            created = await self.client.create_product(payload)
            return SyncResult(
                exitoso=True,
                accion="crear_producto",
                sku=producto.sku,
                mensaje="Producto creado en Tienda Nube",
                detalles={"tn_product": created, "category_ids": category_ids},
            )

        product_id = str(existing["id"])
        updated = await self.client.update_product(product_id, payload)
        return SyncResult(
            exitoso=True,
            accion="actualizar_producto",
            sku=producto.sku,
            mensaje="Producto actualizado en Tienda Nube",
            detalles={"tn_product": updated, "category_ids": category_ids},
        )

    async def actualizar_stock(self, stock: StockProducto) -> SyncResult:
        """Actualiza únicamente stock en Tienda Nube."""

        existing = await self.client.get_product_by_sku(stock.sku)
        if existing is None:
            return SyncResult(
                exitoso=False,
                accion="actualizar_stock",
                sku=stock.sku,
                mensaje="Producto no encontrado en Tienda Nube",
            )

        variants = existing.get("variants", [])
        if not variants:
            return SyncResult(
                exitoso=False,
                accion="actualizar_stock",
                sku=stock.sku,
                mensaje="Producto sin variantes en Tienda Nube",
            )

        product_id = str(existing["id"])
        variant_id = str(variants[0]["id"])
        updated = await self.client.update_variant_stock(
            product_id=product_id,
            variant_id=variant_id,
            stock=stock.cantidad,
        )
        return SyncResult(
            exitoso=True,
            accion="actualizar_stock",
            sku=stock.sku,
            mensaje="Stock actualizado en Tienda Nube",
            detalles={"tn_variant": updated},
        )

    async def _ensure_category_tree(self, producto: Producto) -> list[int]:
        """Asegura categoria y subcategoria sin duplicar por concurrencia.

        El lock evita que importaciones simultáneas consulten el árbol viejo y creen
        la misma categoría en paralelo. La normalización preventiva ocurre antes
        de cada creación; la función correctiva queda como última instancia.
        """

        async with self._category_lock:
            categoria = self._clean_category_name(producto.categoria_nombre)
            subcategoria = self._clean_category_name(producto.subcategoria_nombre)
            if not categoria:
                return []

            categories = await self.client.list_categories()
            categories = sorted(categories, key=lambda item: int(item.get("id") or 0))
            parent = self._find_category(categories, name=categoria, parent_id=None)
            if parent is None:
                parent = await self.client.create_category({"name": {"es": categoria}})
                categories.append(parent)

            parent_id = self._extract_id(parent)
            if parent_id is None or not subcategoria:
                return [parent_id] if parent_id is not None else []

            child = self._find_category(categories, name=subcategoria, parent_id=parent_id)
            if child is None:
                child = await self.client.create_category({"name": {"es": subcategoria}, "parent": parent_id})

            child_id = self._extract_id(child)
            return [parent_id, child_id] if child_id is not None else [parent_id]

    @classmethod
    def _find_category(
        cls,
        categories: list[dict[str, Any]],
        *,
        name: str,
        parent_id: int | None,
    ) -> dict[str, Any] | None:
        target_name = cls._normalize_name(name)
        for category in categories:
            category_name = cls._category_es_name(category)
            if cls._normalize_name(category_name) != target_name:
                continue
            category_parent = cls._extract_parent_id(category)
            if category_parent == parent_id:
                return category
        return None

    @staticmethod
    def _category_es_name(category: dict[str, Any]) -> str:
        name = category.get("name")
        if isinstance(name, dict):
            return str(name.get("es") or name.get("pt") or name.get("en") or "")
        return str(name or "")

    @staticmethod
    def _extract_id(category: dict[str, Any]) -> int | None:
        value = category.get("id")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_parent_id(cls, category: dict[str, Any]) -> int | None:
        parent = category.get("parent")
        if isinstance(parent, dict):
            return cls._extract_id(parent)
        try:
            return int(parent) if parent not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _clean_category_name(value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _normalize_name(value: str) -> str:
        return normalize_category_key(value)

from __future__ import annotations

import asyncio
from typing import Any

from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.domain.models.sync_result import SyncResult
from app.domain.ports.publicador_ecommerce import PublicadorEcommerce
from app.infrastructure.tienda_nube.category_utils import normalize_category_key
from app.infrastructure.tienda_nube.client import TiendaNubeClient
from app.infrastructure.tienda_nube.payload_builder import TiendaNubePayloadBuilder


class TiendaNubeAdapter(PublicadorEcommerce):
    """Adaptador de Tienda Nube hacia contrato interno.

    La actualización se divide por recurso:
    - producto: nombre, descripción, categorías, publicación;
    - variante: SKU, precio, stock, barcode;
    - imágenes: solo en creación para evitar duplicados y 422 en updates.
    """

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
        """Crea o actualiza producto completo en Tienda Nube de forma segura."""

        existing = await self.client.get_product_by_sku(producto.sku)
        category_ids = await self._ensure_category_tree(producto)

        if existing is None:
            payload = self.builder.build_create_product_payload(producto, category_ids=category_ids)
            created = await self.client.create_product(payload)
            return SyncResult(
                exitoso=True,
                accion="crear_producto",
                sku=producto.sku,
                mensaje="Producto creado en Tienda Nube",
                detalles={
                    "tn_product": created,
                    "category_ids": category_ids,
                    "product_payload": payload,
                },
            )

        product_id = str(existing["id"])
        product_payload = self.builder.build_update_product_payload(producto, category_ids=category_ids)
        updated_product = await self.client.update_product(product_id, product_payload)

        variant_payload = self.builder.build_update_variant_payload(producto)
        target_variant = self._select_variant(existing, sku=producto.sku)
        updated_variant: dict[str, Any] | None = None
        variant_action = "sin_variante"

        if target_variant is not None:
            variant_id = str(target_variant["id"])
            updated_variant = await self.client.update_variant(
                product_id=product_id,
                variant_id=variant_id,
                payload=variant_payload,
            )
            variant_action = "actualizar_variante"
        else:
            # Caso defensivo: un producto existente sin variantes no puede quedar
            # sin variante operativa si queremos sincronizar precio/stock.
            create_variant_payload = self.builder.build_create_variant_payload(producto)
            updated_variant = await self.client.create_variant(product_id, create_variant_payload)
            variant_action = "crear_variante"

        tn_product = self._merge_product_with_variant(updated_product or existing, updated_variant)
        return SyncResult(
            exitoso=True,
            accion="actualizar_producto",
            sku=producto.sku,
            mensaje="Producto y variante actualizados en Tienda Nube",
            detalles={
                "tn_product": tn_product,
                "tn_variant": updated_variant,
                "category_ids": category_ids,
                "product_payload": product_payload,
                "variant_payload": variant_payload,
                "variant_action": variant_action,
            },
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

        variant = self._select_variant(existing, sku=stock.sku)
        if variant is None:
            return SyncResult(
                exitoso=False,
                accion="actualizar_stock",
                sku=stock.sku,
                mensaje="Producto sin variantes en Tienda Nube",
            )

        product_id = str(existing["id"])
        variant_id = str(variant["id"])
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

    @staticmethod
    def _select_variant(product: dict[str, Any], *, sku: str) -> dict[str, Any] | None:
        variants = product.get("variants") or []
        if not isinstance(variants, list) or not variants:
            return None

        sku_target = str(sku or "").strip().casefold()
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            if str(variant.get("sku") or "").strip().casefold() == sku_target:
                return variant

        for variant in variants:
            if isinstance(variant, dict) and variant.get("id") not in (None, ""):
                return variant
        return None

    @staticmethod
    def _merge_product_with_variant(
        product: dict[str, Any] | None,
        variant: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(product or {})
        if variant is not None:
            existing_variants = merged.get("variants")
            if isinstance(existing_variants, list) and existing_variants:
                variant_id = str(variant.get("id") or "")
                replaced = False
                new_variants: list[dict[str, Any]] = []
                for item in existing_variants:
                    if isinstance(item, dict) and str(item.get("id") or "") == variant_id:
                        new_variants.append(variant)
                        replaced = True
                    elif isinstance(item, dict):
                        new_variants.append(item)
                if not replaced:
                    new_variants.insert(0, variant)
                merged["variants"] = new_variants
            else:
                merged["variants"] = [variant]
        return merged

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

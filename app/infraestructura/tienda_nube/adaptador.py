from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from collections.abc import Callable
from typing import Any

from app.infraestructura.tienda_nube.coordinacion_categorias import CoordinadorCategoriasPostgres
from app.infraestructura.tienda_nube.mapeo_categorias import MapeoCategoriasPostgres
from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockProducto
from app.dominio.modelos.resultado_sincronizacion import SyncResult
from app.dominio.puertos.publicador_comercio_electronico import (
    PublicadorComercioElectronico,
)
from app.infraestructura.tienda_nube.utilidades_categorias import normalize_category_key
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube
from app.infraestructura.tienda_nube.construccion_payload import (
    TiendaNubePayloadBuilder,
)


logger = logging.getLogger(__name__)


class AdaptadorTiendaNube(PublicadorComercioElectronico):
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
        client: ClienteTiendaNube,
        image_normalization_enabled: bool = False,
        image_normalization_base_url: str = "",
        image_normalization_canvas_size: int = 1600,
        category_name_resolver: Callable[[str, str | None, str | None], str | None] | None = None,
        category_coordinator: CoordinadorCategoriasPostgres | None = None,
        category_mapping: MapeoCategoriasPostgres | None = None,
    ) -> None:
        self.client = client
        self.category_name_resolver = category_name_resolver
        self.category_coordinator = category_coordinator
        self.category_mapping = category_mapping
        self.builder = TiendaNubePayloadBuilder(
            image_normalization_enabled=image_normalization_enabled,
            image_normalization_base_url=image_normalization_base_url,
            image_normalization_canvas_size=image_normalization_canvas_size,
        )

    async def crear_o_actualizar_producto(self, producto: Producto) -> SyncResult:
        """Crea o actualiza producto completo en Tienda Nube de forma segura."""

        existing = await self.client.get_product_by_sku(producto.sku)
        category_ids = await self._ensure_category_tree(producto)
        advertencias = (
            ["DESCRIPCION_ML_VACIA: se conserva la descripción existente"]
            if not (producto.descripcion_web or "").strip()
            else []
        )

        if existing is None:
            payload = self.builder.build_create_product_payload(
                producto, category_ids=category_ids
            )
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
                    "advertencias": advertencias,
                },
            )

        product_id = str(existing["id"])
        product_payload = self.builder.build_update_product_payload(
            producto, category_ids=category_ids
        )
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
            updated_variant = await self.client.create_variant(
                product_id, create_variant_payload
            )
            variant_action = "crear_variante"

        tn_product = self._merge_product_with_variant(
            updated_product or existing, updated_variant
        )
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
                "advertencias": advertencias,
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
                    if (
                        isinstance(item, dict)
                        and str(item.get("id") or "") == variant_id
                    ):
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

        async with self._category_creation_lock():
            categoria_origen = self._clean_category_name(producto.categoria_nombre)
            categoria = self._resolve_category_name(
                "categoria", categoria_origen, None
            )
            subcategoria_origen = self._clean_category_name(producto.subcategoria_nombre)
            subcategoria = self._resolve_category_name(
                "subcategoria", subcategoria_origen, categoria
            )
            if not categoria:
                return []

            categories = await self.client.list_categories()
            categories = sorted(categories, key=lambda item: int(item.get("id") or 0))
            parent = await self._resolve_persisted_category(
                categories, name=categoria, parent_id=None
            )
            self._warn_duplicated_category(categories, name=categoria, parent_id=None)
            if parent is None:
                parent = await self.client.create_category({"name": {"es": categoria}})
                categories.append(parent)
            parent_id = self._extract_id(parent)
            if parent_id is None:
                raise RuntimeError("Categoría padre sin ID de Tiendanube")
            await self._remember_category(categoria, None, parent_id)
            if not subcategoria:
                return [parent_id]

            child = await self._resolve_persisted_category(
                categories, name=subcategoria, parent_id=parent_id
            )
            self._warn_duplicated_category(categories, name=subcategoria, parent_id=parent_id)
            if child is None:
                child = await self.client.create_category(
                    {"name": {"es": subcategoria}, "parent": parent_id}
                )
            child_id = self._extract_id(child)
            if child_id is None:
                raise RuntimeError("Subcategoría sin ID de Tiendanube")
            await self._remember_category(subcategoria, parent_id, child_id)
            return [parent_id, child_id]

    async def _resolve_persisted_category(
        self, categories: list[dict[str, Any]], *, name: str, parent_id: int | None
    ) -> dict[str, Any] | None:
        """Usa el mapeo solo si el catálogo remoto confirma ID, nombre y padre."""
        if self.category_mapping is not None:
            category_id = await self.category_mapping.buscar(
                self._normalize_name(name), parent_id
            )
            if category_id is not None:
                for category in categories:
                    if (
                        self._extract_id(category) == category_id
                        and self._extract_parent_id(category) == parent_id
                        and self._normalize_name(self._category_es_name(category))
                        == self._normalize_name(name)
                    ):
                        return category
                logger.warning("mapeo_categoria_obsoleto", extra={"id": category_id, "nombre": name})
        return self._find_category(categories, name=name, parent_id=parent_id)

    async def _remember_category(self, name: str, parent_id: int | None, category_id: int) -> None:
        if self.category_mapping is not None:
            await self.category_mapping.guardar(
                self._normalize_name(name), parent_id, category_id
            )


    @asynccontextmanager
    async def _category_creation_lock(self) -> AsyncIterator[None]:
        # El lock local es útil para pruebas y desarrollo de una sola instancia;
        # en producción la fábrica inyecta obligatoriamente coordinación PostgreSQL.
        async with self._category_lock:
            if self.category_coordinator is not None:
                async with self.category_coordinator.proteger():
                    yield
            else:
                yield

    def _resolve_category_name(
        self,
        tipo: str,
        valor: str | None,
        categoria_padre_canonica: str | None,
    ) -> str | None:
        if not valor:
            return None
        if self.category_name_resolver is None:
            return valor
        resolved = self.category_name_resolver(tipo, valor, categoria_padre_canonica)
        return self._clean_category_name(resolved)

    @classmethod
    def _warn_duplicated_category(cls, categories: list[dict[str, Any]], *, name: str, parent_id: int | None) -> None:
        matching = [category for category in categories
                    if cls._normalize_name(cls._category_es_name(category)) == cls._normalize_name(name)
                    and cls._extract_parent_id(category) == parent_id]
        if len(matching) > 1:
            logger.warning("categorias_existentes_duplicadas", extra={
                "nombre": name, "parent_id": parent_id,
                "ids": [cls._extract_id(item) for item in matching],
            })

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

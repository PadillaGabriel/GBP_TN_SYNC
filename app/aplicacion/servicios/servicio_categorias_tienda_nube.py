from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from app.infraestructura.gbp.analizador_xml import normalizar_texto_gbp
from app.infraestructura.tienda_nube.utilidades_categorias import normalize_category_key
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube
from app.infraestructura.persistencia.repositorios import (
    RepositorioAuditoriaSincronizacion,
    RepositorioNormalizacionCategorias,
)
from app.configuracion import ConfiguracionAplicacion

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CategoryNode:
    id: int
    name: str
    normalized_name: str
    parent_id: int | None
    depth: int


class TiendaNubeCategoryService:
    """Mantenimiento defensivo de categorias Tienda Nube.

    Objetivo: evitar y corregir categorias duplicadas creadas por diferencias
    de encoding, mayusculas, acentos, espacios o padres duplicados.
    """

    def __init__(
        self,
        *,
        settings: ConfiguracionAplicacion,
        audit_repo: RepositorioAuditoriaSincronizacion | None = None,
        category_repo: RepositorioNormalizacionCategorias | None = None,
    ) -> None:
        self.settings = settings
        self.audit_repo = audit_repo
        self.category_repo = category_repo
        self.client = ClienteTiendaNube(
            base_url=settings.tienda_nube_base_url,
            store_id=settings.tienda_nube_store_id,
            access_token=settings.tienda_nube_access_token,
            timeout_seconds=settings.tienda_nube_timeout_seconds,
        )

    async def normalizar_categorias_duplicadas(
        self, *, confirm: bool = False
    ) -> dict[str, Any]:
        """Reasigna productos a categorias canonicas y elimina duplicados vacios.

        Sin confirm=True solo diagnostica. Con confirm=True escribe en Tienda Nube.
        """

        categories_raw = await self.client.list_categories(max_pages=50)
        nodes = self._build_nodes(categories_raw)
        id_to_node = {node.id: node for node in nodes}
        id_map, categorias_a_crear = await self._build_canonical_map(
            nodes, confirm=confirm
        )

        productos_revisados = 0
        productos_actualizados = 0
        errores_productos: list[dict[str, Any]] = []

        if confirm and id_map:
            products = await self.client.list_products(per_page=200, max_pages=100)
            for product in products:
                product_id = product.get("id")
                if product_id in (None, ""):
                    continue
                categorias_actuales = self._extract_product_category_ids(product)
                if not categorias_actuales:
                    continue
                productos_revisados += 1
                categorias_nuevas = self._dedupe_ids(
                    [
                        id_map.get(category_id, category_id)
                        for category_id in categorias_actuales
                    ]
                )
                if categorias_nuevas == categorias_actuales:
                    continue
                try:
                    await self.client.update_product_categories(
                        str(product_id), categorias_nuevas
                    )
                    productos_actualizados += 1
                    await asyncio.sleep(0.35)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "tn_category_product_reassign_failed",
                        extra={"product_id": product_id},
                    )
                    errores_productos.append(
                        {
                            "product_id": product_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        categorias_eliminadas = 0
        errores_eliminacion: list[dict[str, Any]] = []
        duplicate_ids = [
            dup_id for dup_id, canonical_id in id_map.items() if dup_id != canonical_id
        ]
        if confirm and duplicate_ids:
            # Primero hijos, después padres.
            duplicate_ids_sorted = sorted(
                duplicate_ids,
                key=lambda category_id: id_to_node.get(
                    category_id, _CategoryNode(category_id, "", "", None, 0)
                ).depth,
                reverse=True,
            )
            for category_id in duplicate_ids_sorted:
                try:
                    result = await self.client.delete_category(str(category_id))
                    await asyncio.sleep(0.35)
                    if result.get("estado") in {
                        "ELIMINADO",
                        "NO_EXISTE_EN_TIENDA_NUBE",
                    }:
                        categorias_eliminadas += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "tn_category_delete_duplicate_failed",
                        extra={"category_id": category_id},
                    )
                    errores_eliminacion.append(
                        {
                            "category_id": category_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

        duplicados_detectados = len(duplicate_ids)
        result = {
            "ok": len(errores_productos) == 0 and len(errores_eliminacion) == 0,
            "confirm": confirm,
            "categorias_total": len(categories_raw),
            "categorias_duplicadas_detectadas": duplicados_detectados,
            "categorias_a_crear_en_canonico": len(categorias_a_crear),
            "categorias_eliminadas": categorias_eliminadas,
            "productos_revisados": productos_revisados,
            "productos_actualizados": productos_actualizados,
            "errores_productos": errores_productos[:20],
            "errores_eliminacion": errores_eliminacion[:20],
            "mapeo_duplicados_muestra": [
                {"duplicada": duplicate_id, "canonica": canonical_id}
                for duplicate_id, canonical_id in list(id_map.items())[:50]
                if duplicate_id != canonical_id
            ],
        }
        if self.audit_repo is not None:
            self.audit_repo.registrar(
                sku=None,
                accion="TN_CATEGORY_DEDUPLICATION",
                estado="OK" if result["ok"] else "OK_CON_ERRORES",
                mensaje=(
                    f"confirm={confirm} categorias_total={len(categories_raw)} duplicadas={duplicados_detectados} "
                    f"productos_actualizados={productos_actualizados} categorias_eliminadas={categorias_eliminadas}"
                ),
                metodo_gbp="TiendaNubeCategoryService.normalizar_categorias_duplicadas",
            )
        return result

    async def _build_canonical_map(
        self,
        nodes: list[_CategoryNode],
        *,
        confirm: bool,
    ) -> tuple[dict[int, int], list[dict[str, Any]]]:
        """Construye el mapa usando tanto normalización técnica como aliases comerciales."""

        id_map: dict[int, int] = {}
        categorias_a_crear: list[dict[str, Any]] = []
        roots = sorted((node for node in nodes if node.parent_id is None), key=lambda n: n.id)
        children = sorted((node for node in nodes if node.parent_id is not None), key=lambda n: n.id)

        root_groups: dict[str, list[_CategoryNode]] = {}
        root_label: dict[str, str] = {}
        for node in roots:
            canonical_name = self._resolve_business_name("categoria", node.name, None) or node.name
            key = normalize_category_key(canonical_name)
            root_groups.setdefault(key, []).append(node)
            root_label.setdefault(key, canonical_name)

        canonical_root_name_by_id: dict[int, str] = {}
        for key, group in root_groups.items():
            label = root_label[key]
            exact = next((n for n in group if normalize_category_key(n.name) == key), None)
            canonical_id = exact.id if exact is not None else None
            if canonical_id is None:
                payload = {"name": {"es": label}}
                categorias_a_crear.append(payload)
                if confirm:
                    created = await self.client.create_category(payload)
                    await asyncio.sleep(0.35)
                    canonical_id = self._extract_id(created)
            if canonical_id is None:
                canonical_id = group[0].id
            canonical_root_name_by_id[canonical_id] = label
            for node in group:
                id_map[node.id] = canonical_id

        child_groups: dict[tuple[int, str], list[_CategoryNode]] = {}
        child_label: dict[tuple[int, str], str] = {}
        for node in children:
            target_parent_id = id_map.get(node.parent_id or 0, node.parent_id)
            if target_parent_id is None:
                continue
            parent_name = canonical_root_name_by_id.get(target_parent_id)
            canonical_name = self._resolve_business_name(
                "subcategoria", node.name, parent_name
            ) or node.name
            key = (target_parent_id, normalize_category_key(canonical_name))
            child_groups.setdefault(key, []).append(node)
            child_label.setdefault(key, canonical_name)

        for key, group in child_groups.items():
            target_parent_id, normalized_child = key
            label = child_label[key]
            exact = next(
                (
                    n
                    for n in group
                    if n.parent_id == target_parent_id
                    and normalize_category_key(n.name) == normalized_child
                ),
                None,
            )
            canonical_id = exact.id if exact is not None else None
            if canonical_id is None:
                payload = {"name": {"es": label}, "parent": target_parent_id}
                categorias_a_crear.append(payload)
                if confirm:
                    created = await self.client.create_category(payload)
                    await asyncio.sleep(0.35)
                    canonical_id = self._extract_id(created)
            if canonical_id is None:
                canonical_id = group[0].id
            for node in group:
                id_map[node.id] = canonical_id

        return id_map, categorias_a_crear

    def _resolve_business_name(
        self, tipo: str, value: str | None, parent_name: str | None
    ) -> str | None:
        if self.category_repo is None:
            return value
        return self.category_repo.resolver(tipo, value, parent_name)

    @classmethod
    def _build_nodes(cls, categories: list[dict[str, Any]]) -> list[_CategoryNode]:
        raw_nodes: list[tuple[int, str, str, int | None]] = []
        for category in categories:
            category_id = cls._extract_id(category)
            if category_id is None:
                continue
            name = cls._category_es_name(category)
            normalized_name = cls.normalize_category_key(name)
            parent_id = cls._extract_parent_id(category)
            if not normalized_name:
                continue
            raw_nodes.append((category_id, name, normalized_name, parent_id))
        parent_by_id = {
            category_id: parent_id for category_id, _name, _norm, parent_id in raw_nodes
        }
        return [
            _CategoryNode(
                id=category_id,
                name=name,
                normalized_name=normalized_name,
                parent_id=parent_id,
                depth=cls._depth(category_id, parent_by_id),
            )
            for category_id, name, normalized_name, parent_id in raw_nodes
        ]

    @staticmethod
    def _depth(category_id: int, parent_by_id: dict[int, int | None]) -> int:
        depth = 0
        seen = {category_id}
        parent_id = parent_by_id.get(category_id)
        while parent_id is not None and parent_id not in seen:
            depth += 1
            seen.add(parent_id)
            parent_id = parent_by_id.get(parent_id)
        return depth

    @staticmethod
    def _dedupe_ids(values: list[int]) -> list[int]:
        seen: set[int] = set()
        result: list[int] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    @classmethod
    def _extract_product_category_ids(cls, product: dict[str, Any]) -> list[int]:
        categories = product.get("categories") or []
        result: list[int] = []
        if not isinstance(categories, list):
            return result
        for category in categories:
            category_id = (
                cls._extract_id(category)
                if isinstance(category, dict)
                else cls._parse_int(category)
            )
            if category_id is not None:
                result.append(category_id)
        return cls._dedupe_ids(result)

    @staticmethod
    def _category_es_name(category: dict[str, Any]) -> str:
        name = category.get("name")
        if isinstance(name, dict):
            return normalizar_texto_gbp(
                str(name.get("es") or name.get("pt") or name.get("en") or "")
            ).strip()
        return normalizar_texto_gbp(str(name or "")).strip()

    @classmethod
    def _extract_id(cls, value: Any) -> int | None:
        if isinstance(value, dict):
            return cls._parse_int(value.get("id"))
        return cls._parse_int(value)

    @classmethod
    def _extract_parent_id(cls, category: dict[str, Any]) -> int | None:
        parent = category.get("parent")
        if isinstance(parent, dict):
            return cls._extract_id(parent)
        return cls._parse_int(parent)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def normalize_category_key(value: str | None) -> str:
        return normalize_category_key(value)

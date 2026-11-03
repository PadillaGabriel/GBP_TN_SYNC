"""Descubrimiento de variantes creadas directamente en Tiendanube.

Solo establece vínculos comprobables: nunca crea productos ni modifica contenido
comercial o stock externo. La sincronización GBP -> TN ocurre en su propio job.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infraestructura.persistencia.modelos import ProductoFuenteModel, ProductoTiendaNubeModel
from app.infraestructura.persistencia.repositorios import RepositorioProductos, RepositorioAuditoriaSincronizacion
from app.infraestructura.tienda_nube.cliente import ClienteTiendaNube


class DescubrimientoTiendaNube:
    def __init__(self, *, db: Session, tn: ClienteTiendaNube) -> None:
        self.db = db
        self.tn = tn
        self.productos = RepositorioProductos(db)
        self.auditoria = RepositorioAuditoriaSincronizacion(db)

    def _registrar(self, sku: str, estado: str, mensaje: str) -> None:
        self.auditoria.registrar(
            sku=sku, accion="DESCUBRIR_MAPEO_TN", estado=estado,
            mensaje=mensaje[:1000], metodo_gbp="TiendaNube.GET /products",
        )

    def _vincular(self, sku: str, product_id: str, variant_id: str) -> str:
        producto = self.db.scalar(select(ProductoFuenteModel).where(ProductoFuenteModel.sku == sku))
        if producto is None:
            return "SIN_PRODUCTO_GBP_LOCAL"
        existente = self.db.scalar(select(ProductoTiendaNubeModel).where(ProductoTiendaNubeModel.sku == sku))
        if existente is not None and self.productos.es_mapeo_tienda_nube_activo(existente):
            if existente.tn_product_id == product_id and existente.tn_variant_id == variant_id:
                return "YA_VINCULADO"
            self._registrar(sku, "CONFLICTO", "Mapeo activo con otros IDs. Revisión manual requerida")
            return "CONFLICTO"
        vinculo_ajeno = self.db.scalar(
            select(ProductoTiendaNubeModel).where(
                ProductoTiendaNubeModel.tn_variant_id == variant_id,
                ProductoTiendaNubeModel.sku != sku,
            )
        )
        if vinculo_ajeno is not None:
            self._registrar(sku, "CONFLICTO", "La variante ya pertenece a otro SKU local")
            return "CONFLICTO"
        self.productos.guardar_mapeo_tienda_nube(
            producto_fuente_id=producto.id, sku=sku,
            tn_product_id=product_id, tn_variant_id=variant_id,
            estado_publicacion="activo",
        )
        self._registrar(sku, "VINCULADO", f"product_id={product_id} variant_id={variant_id}")
        return "VINCULADO"

    async def conciliar_sku(self, sku: str) -> str:
        """Resolución puntual; rechaza siempre coincidencias no exactas."""
        sku = sku.strip()
        if not sku or self.productos.obtener_por_sku(sku) is None:
            return "SIN_PRODUCTO_GBP_LOCAL"
        respuesta = await self.tn.get_product_by_sku(sku)
        if not isinstance(respuesta, dict) or not respuesta.get("id"):
            return "NO_ENCONTRADO_TN"
        variantes = respuesta.get("variants")
        if not isinstance(variantes, list):
            return "SIN_VARIANTE_VALIDA"
        iguales = [v for v in variantes if isinstance(v, dict) and str(v.get("sku") or "").strip() == sku and v.get("id") is not None]
        if len(iguales) != 1:
            if len(iguales) > 1:
                self._registrar(sku, "CONFLICTO", "Más de una variante con el mismo SKU")
            return "CONFLICTO" if len(iguales) > 1 else "SIN_VARIANTE_VALIDA"
        return self._vincular(sku, str(respuesta["id"]), str(iguales[0]["id"]))

    async def recorrer_catalogo(
        self, *, max_pages: int = 100,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Barrido paginado de variantes TN; el límite evita trabajos ilimitados."""
        resumen: dict[str, Any] = {
            "paginas": 0, "variantes": 0, "vinculados": 0,
            "ya_vinculados": 0, "sin_producto_gbp_local": 0,
            "conflictos": 0, "sin_sku": 0, "incompleto": False,
        }
        candidatos: dict[str, list[tuple[str, str]]] = {}
        completo = False
        for page in range(1, max_pages + 1):
            productos = await self.tn.get_products_page(page=page, per_page=100)
            if not productos:
                completo = True
                break
            resumen["paginas"] = page
            for product in productos:
                if not isinstance(product, dict) or product.get("id") is None:
                    continue
                variantes = product.get("variants") or []
                if not isinstance(variantes, list):
                    continue
                for variant in variantes:
                    if not isinstance(variant, dict):
                        continue
                    resumen["variantes"] += 1
                    sku = str(variant.get("sku") or "").strip()
                    if not sku or variant.get("id") is None:
                        resumen["sin_sku"] += 1
                        continue
                    candidatos.setdefault(sku, []).append((str(product["id"]), str(variant["id"])))
            if on_progress:
                on_progress(dict(resumen))
            if len(productos) < 100:
                completo = True
                break
        # No persistir asociaciones tras una lectura incompleta: podrían existir
        # duplicados en páginas que aún no se consultaron.
        if not completo:
            resumen["incompleto"] = True
            return resumen
        for sku, coincidencias in candidatos.items():
            if len(coincidencias) != 1:
                resumen["conflictos"] += 1
                self._registrar(sku, "CONFLICTO", "SKU duplicado entre variantes del catálogo TN")
                continue
            estado = self._vincular(sku, *coincidencias[0])
            key = {"VINCULADO": "vinculados", "YA_VINCULADO": "ya_vinculados", "CONFLICTO": "conflictos", "SIN_PRODUCTO_GBP_LOCAL": "sin_producto_gbp_local"}[estado]
            resumen[key] += 1
        return resumen

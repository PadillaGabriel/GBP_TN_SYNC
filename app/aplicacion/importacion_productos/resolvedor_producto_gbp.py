from __future__ import annotations

import logging

from app.aplicacion.importacion_productos.compositor_producto_exportaciones import (
    CompositorProductoExportacionesGBP,
    ConfiguracionExportacionesProducto,
)
from app.configuracion import ConfiguracionAplicacion
from app.dominio.modelos.producto import Producto
from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.exportaciones import ProveedorExportacionesGBP
from app.infraestructura.gbp.normalizador import GBPNormalizer

logger = logging.getLogger(__name__)


class ResolvedorProductoGBP:
    """Resuelve productos exclusivamente desde Exportaciones Personalizadas GBP."""

    def __init__(
        self,
        *,
        cliente_gbp: ClienteGBP,
        normalizador: GBPNormalizer,
        configuracion: ConfiguracionAplicacion,
    ) -> None:
        self._cliente = cliente_gbp
        self._normalizador = normalizador
        self._configuracion = configuracion
        self._exportaciones = ProveedorExportacionesGBP(
            cliente_gbp,
            cache_seconds=configuracion.gbp_export_cache_seconds,
        )
        self._compositor = CompositorProductoExportacionesGBP(
            self._exportaciones,
            ConfiguracionExportacionesProducto(
                productos_general_id=configuracion.gbp_export_productos_general_id,
                precios_id=configuracion.gbp_export_productos_precios_id,
                stock_id=configuracion.gbp_export_productos_stock_id,
                lista_precio_id=str(configuracion.online_price_list_id),
                deposito_id=str(configuracion.ecommerce_primary_storage_id),
            ),
        )

    async def obtener_publicable(self, *, token: str, item_id: str) -> Producto:
        del token  # La exportación administra autenticación y renovación internamente.
        return await self._compositor.obtener_por_item_id(item_id, usar_cache=True)

    async def obtener_manual_flexible(
        self, *, token: str, item_id: str, sku: str
    ) -> Producto:
        del token
        if str(sku or "").strip():
            return await self._compositor.obtener_por_sku(sku, usar_cache=True)
        return await self._compositor.obtener_por_item_id(item_id, usar_cache=True)

    async def enriquecer_manual(
        self, producto: Producto, *, token: str, item_id: str
    ) -> Producto:
        del token, item_id
        # El producto ya fue compuesto con las exportaciones 12, 13 y 14.
        return producto

    @staticmethod
    def crear_producto_minimo(
        *, sku: str, item_id: str, titulo: str | None = None
    ) -> Producto:
        sku_final = str(sku or item_id).strip()
        titulo_final = str(titulo or sku_final or f"Producto {item_id}").strip()
        return Producto(
            sku=sku_final,
            id_sistema_gbp=str(item_id).strip(),
            titulo=titulo_final,
            publicable_web=None,
            item_disabled=False,
            item_not_for_sale=False,
            descripcion_web=titulo_final,
            imagenes=[],
            precio_importado=None,
            stock=None,
        )

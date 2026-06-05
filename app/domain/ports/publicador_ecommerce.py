from typing import Protocol

from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.domain.models.sync_result import SyncResult


class PublicadorEcommerce(Protocol):
    """Contrato para publicar productos en un eCommerce."""

    async def crear_o_actualizar_producto(self, producto: Producto) -> SyncResult:
        """Crea o actualiza producto completo."""

    async def actualizar_stock(self, stock: StockProducto) -> SyncResult:
        """Actualiza únicamente stock."""

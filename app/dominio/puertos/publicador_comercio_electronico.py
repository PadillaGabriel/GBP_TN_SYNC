from typing import Protocol

from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockProducto
from app.dominio.modelos.resultado_sincronizacion import SyncResult


class PublicadorComercioElectronico(Protocol):
    """Contrato para publicar productos en un eCommerce."""

    async def crear_o_actualizar_producto(self, producto: Producto) -> SyncResult:
        """Crea o actualiza producto completo."""

    async def actualizar_stock(self, stock: StockProducto) -> SyncResult:
        """Actualiza únicamente stock."""

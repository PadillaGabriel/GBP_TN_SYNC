from typing import Protocol

from app.domain.models.stock import StockProducto


class ProveedorStock(Protocol):
    """Contrato para consultar stock operativo."""

    async def obtener_stock(
        self,
        *,
        sku: str | None = None,
        id_sistema: str | None = None,
    ) -> StockProducto:
        """Obtiene stock por SKU o ID interno."""

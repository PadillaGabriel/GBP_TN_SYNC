from typing import Protocol

from app.domain.models.producto import Producto


class ProveedorProductos(Protocol):
    """Contrato para obtener productos desde una fuente externa."""

    async def listar_productos_publicables(self) -> list[str]:
        """Lista SKUs o IDs internos habilitados para eCommerce."""

    async def obtener_producto_completo(
        self,
        *,
        sku: str | None = None,
        id_sistema: str | None = None,
    ) -> Producto:
        """Obtiene producto completo por SKU o ID interno."""

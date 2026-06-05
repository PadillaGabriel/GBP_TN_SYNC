from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.domain.ports.proveedor_productos import ProveedorProductos
from app.domain.ports.proveedor_stock import ProveedorStock
from app.infrastructure.gbp.client import GBPClient
from app.infrastructure.gbp.module16_registry import Module16Registry
from app.infrastructure.gbp.normalizer import GBPNormalizer


class GBPAdapter(ProveedorProductos, ProveedorStock):
    """Adaptador GBP hacia contratos internos.

    Actualmente bloquea métodos no validados por Módulo 16.
    """

    def __init__(self, *, client: GBPClient, registry: Module16Registry) -> None:
        self.client = client
        self.registry = registry
        self.normalizer = GBPNormalizer()

    async def listar_productos_publicables(self) -> list[str]:
        """Lista SKUs habilitados para eCommerce desde GBP."""

        self.registry.validar("listar_productos_publicables")
        # Implementación real pendiente de método GBP confirmado.
        return []

    async def obtener_producto_completo(
        self,
        *,
        sku: str | None = None,
        id_sistema: str | None = None,
    ) -> Producto:
        """Obtiene producto completo desde GBP."""

        self.registry.validar("obtener_producto_completo")
        # Implementación real pendiente de método GBP confirmado.
        data = {
            "sku": sku,
            "id_sistema_gbp": id_sistema,
            "titulo": "",
        }
        return self.normalizer.normalizar_producto(data)

    async def obtener_stock(
        self,
        *,
        sku: str | None = None,
        id_sistema: str | None = None,
    ) -> StockProducto:
        """Obtiene stock desde GBP."""

        self.registry.validar("obtener_stock")
        # Implementación real pendiente de método GBP confirmado.
        data = {
            "sku": sku,
            "id_sistema_gbp": id_sistema,
            "stock": 0,
        }
        return self.normalizer.normalizar_stock(data)

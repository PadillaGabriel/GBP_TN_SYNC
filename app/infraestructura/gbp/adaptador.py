from app.dominio.modelos.producto import Producto
from app.dominio.modelos.stock import StockProducto
from app.dominio.puertos.proveedor_productos import ProveedorProductos
from app.dominio.puertos.proveedor_stock import ProveedorStock
from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.registro_modulo16 import RegistroModulo16
from app.infraestructura.gbp.normalizador import GBPNormalizer


class AdaptadorGBP(ProveedorProductos, ProveedorStock):
    """Adaptador GBP hacia contratos internos.

    Actualmente bloquea métodos no validados por Módulo 16.
    """

    def __init__(self, *, client: ClienteGBP, registry: RegistroModulo16) -> None:
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

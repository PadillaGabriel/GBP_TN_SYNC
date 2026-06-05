from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.domain.models.sync_result import SyncResult
from app.domain.ports.publicador_ecommerce import PublicadorEcommerce
from app.infrastructure.tienda_nube.client import TiendaNubeClient
from app.infrastructure.tienda_nube.payload_builder import TiendaNubePayloadBuilder


class TiendaNubeAdapter(PublicadorEcommerce):
    """Adaptador de Tienda Nube hacia contrato interno."""

    def __init__(self, *, client: TiendaNubeClient) -> None:
        self.client = client
        self.builder = TiendaNubePayloadBuilder()

    async def crear_o_actualizar_producto(self, producto: Producto) -> SyncResult:
        """Crea o actualiza producto completo en Tienda Nube."""

        existing = await self.client.get_product_by_sku(producto.sku)
        payload = self.builder.build_product_payload(producto)
        if existing is None:
            created = await self.client.create_product(payload)
            return SyncResult(
                exitoso=True,
                accion="crear_producto",
                sku=producto.sku,
                mensaje="Producto creado en Tienda Nube",
                detalles={"tn_product": created},
            )

        product_id = str(existing["id"])
        updated = await self.client.update_product(product_id, payload)
        return SyncResult(
            exitoso=True,
            accion="actualizar_producto",
            sku=producto.sku,
            mensaje="Producto actualizado en Tienda Nube",
            detalles={"tn_product": updated},
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

        variants = existing.get("variants", [])
        if not variants:
            return SyncResult(
                exitoso=False,
                accion="actualizar_stock",
                sku=stock.sku,
                mensaje="Producto sin variantes en Tienda Nube",
            )

        variant_id = str(variants[0]["id"])
        updated = await self.client.update_stock(variant_id, stock.cantidad)
        return SyncResult(
            exitoso=True,
            accion="actualizar_stock",
            sku=stock.sku,
            mensaje="Stock actualizado en Tienda Nube",
            detalles={"tn_variant": updated},
        )

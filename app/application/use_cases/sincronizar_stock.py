from app.domain.models.sync_result import SyncResult
from app.domain.ports.proveedor_stock import ProveedorStock
from app.domain.ports.publicador_ecommerce import PublicadorEcommerce
from app.infrastructure.persistence.repositories import (
    ProductoRepository,
    SyncAuditRepository,
)


class SincronizarStock:
    """Sincroniza exclusivamente stock.

    No actualiza precio, descripción, imágenes, categoría ni medidas.
    """

    def __init__(
        self,
        *,
        proveedor_stock: ProveedorStock,
        publicador: PublicadorEcommerce,
        productos: ProductoRepository,
        auditoria: SyncAuditRepository,
    ) -> None:
        self.proveedor_stock = proveedor_stock
        self.publicador = publicador
        self.productos = productos
        self.auditoria = auditoria

    async def ejecutar(self, *, sku: str) -> SyncResult:
        """Consulta GBP y actualiza Tienda Nube solo si el stock cambió."""

        stock = await self.proveedor_stock.obtener_stock(sku=sku)
        stock_local = self.productos.obtener_stock(sku)

        if stock_local is not None and stock_local == stock.cantidad:
            self.auditoria.registrar(
                sku=sku,
                accion="sincronizar_stock",
                estado="sin_cambios",
                mensaje="Stock sin cambios",
            )
            return SyncResult(
                exitoso=True,
                accion="sincronizar_stock",
                sku=sku,
                mensaje="Stock sin cambios",
                detalles={"stock": stock.cantidad},
            )

        resultado = await self.publicador.actualizar_stock(stock)
        if resultado.exitoso:
            self.productos.guardar_stock(stock)

        self.auditoria.registrar(
            sku=sku,
            accion="sincronizar_stock",
            estado="ok" if resultado.exitoso else "error",
            mensaje=resultado.mensaje,
        )
        return resultado

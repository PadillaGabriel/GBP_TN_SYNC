from app.application.services.hash_service import stable_hash
from app.domain.models.sync_result import SyncResult
from app.domain.ports.proveedor_productos import ProveedorProductos
from app.domain.ports.publicador_ecommerce import PublicadorEcommerce
from app.infrastructure.persistence.repositories import (
    ProductoRepository,
    SyncAuditRepository,
)


class ImportarProductoCompleto:
    """Importa o actualiza un producto completo desde GBP hacia Tienda Nube."""

    def __init__(
        self,
        *,
        proveedor_productos: ProveedorProductos,
        publicador: PublicadorEcommerce,
        productos: ProductoRepository,
        auditoria: SyncAuditRepository,
    ) -> None:
        self.proveedor_productos = proveedor_productos
        self.publicador = publicador
        self.productos = productos
        self.auditoria = auditoria

    async def ejecutar(self, *, sku: str) -> SyncResult:
        """Ejecuta importación completa.

        El precio se toma en esta operación. No queda dentro del ciclo frecuente.
        """

        producto = await self.proveedor_productos.obtener_producto_completo(sku=sku)
        producto.payload_hash = stable_hash(producto.model_dump(mode="json"))
        self.productos.guardar_producto(producto)

        resultado = await self.publicador.crear_o_actualizar_producto(producto)
        self.auditoria.registrar(
            sku=sku,
            accion="importar_producto_completo",
            estado="ok" if resultado.exitoso else "error",
            mensaje=resultado.mensaje,
        )
        return resultado

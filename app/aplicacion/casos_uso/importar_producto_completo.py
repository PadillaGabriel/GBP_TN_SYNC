from app.aplicacion.servicios.servicio_hash import stable_hash
from app.dominio.modelos.resultado_sincronizacion import SyncResult
from app.dominio.puertos.proveedor_productos import ProveedorProductos
from app.dominio.puertos.publicador_comercio_electronico import (
    PublicadorComercioElectronico,
)
from app.aplicacion.puertos.repositorios import (
    RepositorioAuditoriaPuerto,
    RepositorioProductosPuerto,
)


class ImportarProductoCompleto:
    """Importa o actualiza un producto completo desde GBP hacia Tienda Nube."""

    def __init__(
        self,
        *,
        proveedor_productos: ProveedorProductos,
        publicador: PublicadorComercioElectronico,
        productos: RepositorioProductosPuerto,
        auditoria: RepositorioAuditoriaPuerto,
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

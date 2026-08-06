from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from app.aplicacion.servicios.servicio_validacion_producto import (
    ProductoValidationService,
)
from app.aplicacion.importacion_productos import (
    FabricaAdaptadorTiendaNube,
    PersistidorProductoValidado,
    ResolvedorProductoGBP,
)
from app.infraestructura.gbp.cliente import ClienteGBP
from app.infraestructura.gbp.normalizador import GBPNormalizer
from app.infraestructura.persistencia.repositorios import (
    RepositorioProductos,
    RepositorioAuditoriaSincronizacion,
)
from app.infraestructura.tienda_nube.construccion_payload import (
    TiendaNubePayloadBuilder,
)
from app.configuracion import ConfiguracionAplicacion


class TiendaNubeImportService:
    """Fachada compatible que delega cada operación a un caso de uso especializado."""

    def __init__(self, settings: ConfiguracionAplicacion, db: Session) -> None:
        self.settings = settings
        self.db = db
        self.gbp_client = ClienteGBP(
            base_url=settings.gbp_base_url,
            username=settings.gbp_username,
            password=settings.gbp_password,
            timeout_seconds=settings.gbp_timeout_seconds,
            company_id=settings.gbp_company_id,
            web_service_id=settings.gbp_web_service_id,
        )
        self.normalizer = GBPNormalizer()
        self.validation_service = ProductoValidationService()
        self.productos_repo = RepositorioProductos(db)
        self.audit_repo = RepositorioAuditoriaSincronizacion(db)
        self.payload_builder = TiendaNubePayloadBuilder()
        self.resolvedor_producto = ResolvedorProductoGBP(
            cliente_gbp=self.gbp_client,
            normalizador=self.normalizer,
            configuracion=settings,
        )
        self.persistidor_producto = PersistidorProductoValidado(self.productos_repo)
        self.fabrica_tienda_nube = FabricaAdaptadorTiendaNube(settings)
        from app.aplicacion.importacion_productos.casos_uso import (
            ContextoImportacionProductos,
            ImportarLoteProductos,
            ImportarProductoManual,
            OcultarProducto,
            EliminarProducto,
            ReconciliarMapeos,
            MarcarEliminadosExternos,
        )

        contexto = ContextoImportacionProductos(
            settings=self.settings,
            db=self.db,
            gbp_client=self.gbp_client,
            normalizer=self.normalizer,
            validation_service=self.validation_service,
            productos_repo=self.productos_repo,
            audit_repo=self.audit_repo,
            payload_builder=self.payload_builder,
            resolvedor_producto=self.resolvedor_producto,
            persistidor_producto=self.persistidor_producto,
            fabrica_tienda_nube=self.fabrica_tienda_nube,
        )
        self._importar_lote = ImportarLoteProductos(contexto)
        self._importar_manual = ImportarProductoManual(contexto)
        self._ocultar_producto = OcultarProducto(contexto)
        self._eliminar_producto = EliminarProducto(contexto)
        self._reconciliar_mapeos = ReconciliarMapeos(contexto)
        self._marcar_eliminados = MarcarEliminadosExternos(contexto)

    async def importar_prueba_tienda_nube(
        self, *, limit: int = 20, confirm: bool = False
    ) -> dict[str, Any]:
        return await self._importar_lote.ejecutar(limit=limit, confirm=confirm)

    async def importar_producto_manual_tienda_nube(
        self,
        *,
        sku: str | None = None,
        item_id: int | None = None,
        confirm: bool = False,
        forzar: bool = False,
    ) -> dict[str, Any]:
        return await self._importar_manual.ejecutar(
            sku=sku, item_id=item_id, confirm=confirm, forzar=forzar
        )

    async def ocultar_producto_tienda_nube(
        self, *, sku: str, confirm: bool = False
    ) -> dict[str, Any]:
        return await self._ocultar_producto.ejecutar(sku=sku, confirm=confirm)

    async def eliminar_producto_tienda_nube(
        self, *, sku: str, confirm: bool = False
    ) -> dict[str, Any]:
        return await self._eliminar_producto.ejecutar(sku=sku, confirm=confirm)

    async def reconciliar_mapeos_tienda_nube(
        self, *, limit: int = 500, offset: int = 0
    ) -> dict[str, Any]:
        return await self._reconciliar_mapeos.ejecutar(limit=limit, offset=offset)

    def marcar_mapeos_como_eliminados_externos(
        self, *, confirm: bool = False
    ) -> dict[str, Any]:
        return self._marcar_eliminados.ejecutar(confirm=confirm)

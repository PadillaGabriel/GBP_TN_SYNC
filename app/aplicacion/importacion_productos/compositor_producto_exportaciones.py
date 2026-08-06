from __future__ import annotations

from dataclasses import dataclass

from app.dominio.errores import DatoIncompletoError, GBPProductoNoConsultableError
from app.dominio.modelos.producto import Producto
from app.infraestructura.gbp.exportaciones import (
    ProveedorExportacionesGBP,
    precio_desde_exportacion,
    producto_desde_exportacion,
    stock_desde_exportacion,
)


@dataclass(frozen=True, slots=True)
class ConfiguracionExportacionesProducto:
    productos_general_id: int
    precios_id: int
    stock_id: int
    lista_precio_id: str
    deposito_id: str


class CompositorProductoExportacionesGBP:
    """Compone una ficha de producto con las exportaciones 12, 13 y 14.

    La exportación general aporta identidad y contenido; precios y stock son
    fuentes independientes. Una fila ausente nunca se convierte silenciosamente
    en precio o stock cero.
    """

    def __init__(
        self,
        proveedor: ProveedorExportacionesGBP,
        configuracion: ConfiguracionExportacionesProducto,
    ) -> None:
        self._proveedor = proveedor
        self._configuracion = configuracion

    async def obtener_por_sku(self, sku: str, *, usar_cache: bool = True) -> Producto:
        sku_normalizado = str(sku or "").strip()
        fila_general = await self._proveedor.buscar_fila(
            self._configuracion.productos_general_id,
            item_code=sku_normalizado,
            usar_cache=usar_cache,
        )
        if fila_general is None:
            raise GBPProductoNoConsultableError(
                f"La exportación general no devolvió SKU={sku_normalizado}"
            )
        return await self._componer(fila_general, usar_cache=usar_cache)

    async def obtener_por_item_id(
        self, item_id: str, *, usar_cache: bool = True
    ) -> Producto:
        item_id_normalizado = str(item_id or "").strip()
        fila_general = await self._proveedor.buscar_fila(
            self._configuracion.productos_general_id,
            item_id=item_id_normalizado,
            usar_cache=usar_cache,
        )
        if fila_general is None:
            raise GBPProductoNoConsultableError(
                f"La exportación general no devolvió item_id={item_id_normalizado}"
            )
        return await self._componer(fila_general, usar_cache=usar_cache)

    async def _componer(
        self, fila_general: dict[str, str], *, usar_cache: bool
    ) -> Producto:
        producto = producto_desde_exportacion(fila_general)
        sku = producto.sku
        item_id = producto.id_sistema_gbp

        fila_precio = await self._buscar_fuente(
            self._configuracion.precios_id,
            sku=sku,
            item_id=item_id,
            usar_cache=usar_cache,
        )
        fila_stock = await self._buscar_fuente(
            self._configuracion.stock_id,
            sku=sku,
            item_id=item_id,
            usar_cache=usar_cache,
        )

        if fila_precio is not None:
            self._validar_identidad(fila_precio, sku=sku, item_id=item_id, fuente="precio")
            producto.precio_importado = precio_desde_exportacion(
                fila_precio,
                lista_precio_id=self._configuracion.lista_precio_id,
            )

        if fila_stock is not None:
            self._validar_identidad(fila_stock, sku=sku, item_id=item_id, fuente="stock")
            producto.stock = stock_desde_exportacion(
                fila_stock,
                deposito_id=self._configuracion.deposito_id,
            )
            producto.publicable_web = _bool(fila_stock.get("item_web"), default=False)
            producto.item_disabled = not _bool(
                fila_stock.get("item_active"), default=False
            )
            producto.item_not_for_sale = producto.item_disabled

        producto.payload_crudo = {
            "general": dict(fila_general),
            "precio": dict(fila_precio) if fila_precio is not None else None,
            "stock": dict(fila_stock) if fila_stock is not None else None,
        }
        return producto

    async def _buscar_fuente(
        self,
        export_id: int,
        *,
        sku: str,
        item_id: str,
        usar_cache: bool,
    ) -> dict[str, str] | None:
        fila = await self._proveedor.buscar_fila(
            export_id,
            item_code=sku,
            usar_cache=usar_cache,
        )
        if fila is None and item_id:
            fila = await self._proveedor.buscar_fila(
                export_id,
                item_id=item_id,
                usar_cache=usar_cache,
            )
        return fila

    @staticmethod
    def _validar_identidad(
        fila: dict[str, str], *, sku: str, item_id: str, fuente: str
    ) -> None:
        sku_fuente = str(fila.get("item_code") or "").strip()
        item_id_fuente = str(fila.get("item_id") or "").strip()
        if sku_fuente and sku_fuente.casefold() != sku.casefold():
            raise DatoIncompletoError(
                f"La exportación de {fuente} devolvió SKU={sku_fuente} para SKU={sku}"
            )
        if item_id_fuente and item_id_fuente != item_id:
            raise DatoIncompletoError(
                f"La exportación de {fuente} devolvió item_id={item_id_fuente} "
                f"para item_id={item_id}"
            )


def _bool(value: object, *, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "si", "sí"}

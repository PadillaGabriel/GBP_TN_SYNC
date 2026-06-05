from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.domain.models.producto import Producto


class TiendaNubePayloadBuilder:
    """Construye payloads de Tienda Nube desde modelos internos."""

    def build_product_payload(
        self,
        producto: Producto,
        *,
        category_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Payload para crear o actualizar producto completo."""

        payload: dict[str, Any] = {
            "name": {"es": producto.titulo},
            "description": {"es": producto.descripcion_web or ""},
            "variants": [self._build_main_variant(producto)],
        }

        if category_ids:
            payload["categories"] = category_ids

        if producto.imagenes:
            payload["images"] = [
                {"src": str(imagen.url)}
                for imagen in sorted(producto.imagenes, key=lambda item: item.orden)
                if imagen.url is not None
            ]

        return payload

    @staticmethod
    def _format_price(value: Decimal | int | float | str | None) -> str:
        """Formatea precio para Tienda Nube con 2 decimales."""

        if value is None:
            return "0.00"

        amount = Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        return str(amount)

    @staticmethod
    def _build_main_variant(producto: Producto) -> dict[str, Any]:
        precio = (
            TiendaNubePayloadBuilder._format_price(producto.precio_importado.monto)
            if producto.precio_importado
            else "0.00"
        )

        stock = producto.stock.cantidad if producto.stock else 0

        return {
            "sku": producto.sku,
            "price": precio,
            "stock": stock,
            # Regla de negocio Silmar: el codigo de proveedor GBP se publica
            # como codigo universal/barcode en Tienda Nube.
            "barcode": producto.codigo_proveedor,
        }

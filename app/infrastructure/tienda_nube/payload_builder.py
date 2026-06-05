from typing import Any

from app.domain.models.producto import Producto


class TiendaNubePayloadBuilder:
    """Construye payloads de Tienda Nube desde modelos internos."""

    def build_product_payload(self, producto: Producto) -> dict[str, Any]:
        """Payload para crear o actualizar producto completo."""

        payload: dict[str, Any] = {
            "name": {"es": producto.titulo},
            "description": {"es": producto.descripcion or ""},
            "variants": [self._build_main_variant(producto)],
        }
        if producto.imagenes:
            payload["images"] = [
                {"src": str(imagen.url)} for imagen in sorted(producto.imagenes, key=lambda x: x.orden)
                if imagen.url is not None
            ]
        return payload

    @staticmethod
    def _build_main_variant(producto: Producto) -> dict[str, Any]:
        precio = producto.precio_importado.monto if producto.precio_importado else 0
        stock = producto.stock.cantidad if producto.stock else 0
        return {
            "sku": producto.sku,
            "price": str(precio),
            "stock": stock,
            "barcode": producto.codigo_universal,
        }

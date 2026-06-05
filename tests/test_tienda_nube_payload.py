from decimal import Decimal

from app.domain.models.precio import PrecioProducto
from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.infrastructure.tienda_nube.payload_builder import TiendaNubePayloadBuilder


def test_payload_uses_web_description_price_and_stock():
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        descripcion_web="Descripcion web",
        precio_importado=PrecioProducto(monto=Decimal("123.456")),
        stock=StockProducto(sku="SKU1", id_sistema_gbp="1", cantidad=7),
    )
    payload = TiendaNubePayloadBuilder().build_product_payload(producto)
    assert payload["description"]["es"] == "Descripcion web"
    assert payload["variants"][0]["price"] == "123.46"
    assert payload["variants"][0]["stock"] == 7

from decimal import Decimal

from app.domain.models.precio import PrecioProducto
from app.domain.models.producto import Producto
from app.domain.models.stock import StockProducto
from app.infrastructure.tienda_nube.adapter import TiendaNubeAdapter


class FakeUpdateTiendaNubeClient:
    def __init__(self) -> None:
        self.product_payload = None
        self.variant_payload = None
        self.created_variant_payload = None

    async def get_product_by_sku(self, sku: str):
        return {
            "id": 10,
            "name": {"es": "Viejo"},
            "variants": [
                {"id": 20, "sku": sku, "price": "1.00", "stock": 1},
            ],
            "images": [{"id": 99, "src": "https://example.com/old.jpg"}],
        }

    async def list_categories(self):
        return []

    async def create_product(self, payload):
        raise AssertionError("No debe crear producto existente")

    async def create_category(self, payload):
        raise AssertionError("No debe crear categorias sin categoria GBP")

    async def update_product(self, product_id: str, payload):
        self.product_payload = payload
        return {"id": int(product_id), **payload, "variants": [{"id": 20, "sku": "SKU1"}]}

    async def update_variant(self, *, product_id: str, variant_id: str, payload):
        self.variant_payload = payload
        return {"id": int(variant_id), **payload}

    async def create_variant(self, product_id: str, payload):
        self.created_variant_payload = payload
        return {"id": 21, **payload}


async def test_adapter_updates_product_and_variant_separately():
    client = FakeUpdateTiendaNubeClient()
    adapter = TiendaNubeAdapter(client=client)
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto nuevo",
        descripcion_web="Descripcion nueva",
        codigo_proveedor="PROV-1",
        precio_importado=PrecioProducto(monto=Decimal("29999.000020000000000000")),
        stock=StockProducto(sku="SKU1", id_sistema_gbp="1", cantidad=12),
    )

    resultado = await adapter.crear_o_actualizar_producto(producto)

    assert resultado.exitoso is True
    assert resultado.accion == "actualizar_producto"
    assert client.product_payload == {
        "name": {"es": "Producto nuevo"},
        "description": {"es": "<p>Descripcion nueva</p>"},
    }
    assert "variants" not in client.product_payload
    assert "images" not in client.product_payload
    assert client.variant_payload == {
        "sku": "SKU1",
        "price": "29999.00",
        "stock_management": True,
        "stock": 12,
        "barcode": "PROV-1",
    }
    assert client.created_variant_payload is None
    assert resultado.detalles["tn_variant"]["id"] == 20

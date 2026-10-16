from decimal import Decimal

import pytest

from app.dominio.modelos.imagen import ImagenProducto
from app.dominio.modelos.precio import PrecioProducto
from app.dominio.modelos.producto import Producto
from app.infraestructura.tienda_nube.adaptador import AdaptadorTiendaNube


class TiendaFalsa:
    def __init__(self, *, images=None):
        self.images = list(images or [])
        self.created_images = []
        self.product_payload = None
        self.variant_payload = None

    async def get_product_by_sku(self, sku):
        return {"id": 11, "variants": [{"id": 22, "sku": sku}], "images": list(self.images)}

    async def get_product(self, product_id):
        return {"id": int(product_id), "images": list(self.images)}

    async def list_categories(self):
        return []

    async def update_product(self, product_id, payload):
        self.product_payload = payload
        return {"id": int(product_id), **payload}

    async def update_variant(self, *, product_id, variant_id, payload):
        self.variant_payload = payload
        return {"id": int(variant_id), **payload}

    async def create_product_image(self, product_id, source_url):
        self.created_images.append(source_url)
        self.images.append({"id": len(self.images) + 50, "src": source_url})
        return self.images[-1]


def producto():
    return Producto(
        sku="AB-123", id_sistema_gbp="333", titulo="Nuevo título GBP",
        descripcion_web="Nueva descripción GBP",
        precio_importado=PrecioProducto(monto=Decimal("125.50")),
        imagenes=[ImagenProducto(url="https://example.com/1.jpg")],
    )


@pytest.mark.asyncio
async def test_repara_publicacion_sin_imagenes_y_sobrescribe_campos_gbp():
    tienda = TiendaFalsa()
    resultado = await AdaptadorTiendaNube(client=tienda).crear_o_actualizar_producto(producto())
    assert tienda.product_payload["name"]["es"] == "Nuevo título GBP"
    assert tienda.product_payload["description"]["es"] == "<p>Nueva descripción GBP</p>"
    assert tienda.variant_payload["price"] == "125.50"
    assert tienda.created_images == ["https://example.com/1.jpg"]
    assert resultado.detalles["imagenes_agregadas"] == 1

    await AdaptadorTiendaNube(client=tienda).crear_o_actualizar_producto(producto())
    assert tienda.created_images == ["https://example.com/1.jpg"]


@pytest.mark.asyncio
async def test_no_toca_galeria_que_tiene_imagenes():
    tienda = TiendaFalsa(images=[{"id": 77, "src": "https://tn.example/original.jpg"}])
    resultado = await AdaptadorTiendaNube(client=tienda).crear_o_actualizar_producto(producto())
    assert tienda.created_images == []
    assert resultado.detalles["imagenes_agregadas"] == 0


@pytest.mark.asyncio
async def test_no_borra_descripcion_si_gbp_no_la_envia():
    tienda = TiendaFalsa()
    data = producto().model_copy(update={"descripcion_web": None, "imagenes": []})
    await AdaptadorTiendaNube(client=tienda).crear_o_actualizar_producto(data)
    assert "description" not in tienda.product_payload
    assert tienda.created_images == []

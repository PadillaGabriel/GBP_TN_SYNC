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
    assert payload["description"]["es"] == "<p>Descripcion web</p>"
    assert payload["variants"][0]["price"] == "123.46"
    assert payload["variants"][0]["stock"] == 7


def test_payload_uses_vendor_code_as_barcode_and_keeps_long_description():
    long_description = "Organizador de Acero Cromado\n" * 400
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        codigo_universal="7790000000000",
        codigo_proveedor="PROV-123",
        descripcion_web=long_description,
        precio_importado=PrecioProducto(monto=Decimal("123.456")),
        stock=StockProducto(sku="SKU1", id_sistema_gbp="1", cantidad=7),
    )

    payload = TiendaNubePayloadBuilder().build_product_payload(producto)

    assert payload["description"]["es"].count("Organizador de Acero Cromado") == 400
    assert payload["description"]["es"].startswith("<p>")
    assert "<br>" in payload["description"]["es"]
    assert payload["variants"][0]["barcode"] == "PROV-123"


def test_payload_accepts_category_ids():
    producto = Producto(sku="SKU1", id_sistema_gbp="1", titulo="Producto")

    payload = TiendaNubePayloadBuilder().build_product_payload(producto, category_ids=[10, 20])

    assert payload["categories"] == [10, 20]



def test_payload_formats_description_with_paragraphs_bullets_and_separators():
    description = """SOMOS SILMAR BAZAR ONLINE

•Realizamos envíos a todo el pais
•Si estas en CABA o GBA, tu pedido llega en el día

============================================================
DISPENSER JABON LIQUIDO DE CERAMICA

•Art 6130
-Alto: 17cm
-Base: 9cm"""
    producto = Producto(
        sku="6130BL",
        id_sistema_gbp="314",
        titulo="DISPENSER C/ESPONJA BLANCO",
        descripcion_web=description,
        precio_importado=PrecioProducto(monto=Decimal("1000")),
        stock=StockProducto(sku="6130BL", id_sistema_gbp="314", cantidad=3),
    )

    payload = TiendaNubePayloadBuilder().build_product_payload(producto)
    html = payload["description"]["es"]

    assert html.startswith("<p>SOMOS SILMAR BAZAR ONLINE</p>")
    assert "<p>•Realizamos envíos a todo el pais<br>•Si estas en CABA o GBA" in html
    assert "<hr>" in html
    assert "<p>DISPENSER JABON LIQUIDO DE CERAMICA</p>" in html
    assert "•Art 6130<br>-Alto: 17cm<br>-Base: 9cm" in html


def test_payload_escapes_description_html_to_avoid_raw_markup():
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        descripcion_web="Texto <script>alert(1)</script> & mas",
    )

    payload = TiendaNubePayloadBuilder().build_product_payload(producto)

    assert "<script>" not in payload["description"]["es"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; mas" in payload["description"]["es"]


def test_update_product_payload_does_not_include_variants_or_images():
    producto = Producto(
        sku="SKU1",
        id_sistema_gbp="1",
        titulo="Producto",
        descripcion_web="Descripcion",
        precio_importado=PrecioProducto(monto=Decimal("123.456")),
        stock=StockProducto(sku="SKU1", id_sistema_gbp="1", cantidad=7),
    )

    payload = TiendaNubePayloadBuilder().build_update_product_payload(producto, category_ids=[1])

    assert payload == {
        "name": {"es": "Producto"},
        "description": {"es": "<p>Descripcion</p>"},
        "categories": [1],
    }
    assert "variants" not in payload
    assert "images" not in payload


def test_update_variant_payload_does_not_zero_missing_price_or_stock():
    producto = Producto(sku="SKU1", id_sistema_gbp="1", titulo="Producto")

    payload = TiendaNubePayloadBuilder().build_update_variant_payload(producto)

    assert payload == {"sku": "SKU1"}


def test_create_variant_payload_uses_safe_defaults_when_missing_data():
    producto = Producto(sku="SKU1", id_sistema_gbp="1", titulo="Producto")

    payload = TiendaNubePayloadBuilder().build_create_variant_payload(producto)

    assert payload == {
        "sku": "SKU1",
        "price": "0.00",
        "stock_management": True,
        "stock": 0,
    }

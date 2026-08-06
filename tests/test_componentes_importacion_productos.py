from app.aplicacion.importacion_productos.resolvedor_producto_gbp import (
    ResolvedorProductoGBP,
)
from app.aplicacion.importacion_productos.utilidades_tienda_nube import (
    extraer_id_producto_tn,
    extraer_id_variante_tn,
)


def test_extrae_identificadores_tienda_nube() -> None:
    respuesta = {"id": 123, "variants": [{"id": 456}]}
    assert extraer_id_producto_tn(respuesta) == "123"
    assert extraer_id_variante_tn(respuesta) == "456"


def test_crea_producto_minimo_seguro() -> None:
    producto = ResolvedorProductoGBP.crear_producto_minimo(
        sku=" SKU-1 ",
        item_id="99",
    )
    assert producto.sku == "SKU-1"
    assert producto.id_sistema_gbp == "99"
    assert producto.precio_importado is None
    assert producto.stock is None
    assert producto.imagenes == []

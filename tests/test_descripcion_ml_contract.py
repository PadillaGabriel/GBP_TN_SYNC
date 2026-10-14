"""Regresiones: la descripción comercial nunca se sustituye silenciosamente."""
from app.infraestructura.gbp.exportaciones import producto_desde_exportacion
from app.infraestructura.tienda_nube.construccion_payload import TiendaNubePayloadBuilder


def test_exportacion_no_usa_titulo_si_falta_descripcion_ml():
    producto = producto_desde_exportacion({
        "item_id": "42", "item_code": "SKU42", "item_desc": "Titulo comercial",
        "descripcion_larga": "",
    })
    assert producto.descripcion_web == ""
    payload = TiendaNubePayloadBuilder().build_update_product_payload(producto)
    assert "description" not in payload

def test_exportacion_preserva_descripcion_ml():
    producto = producto_desde_exportacion({
        "item_id": "42", "item_code": "SKU42", "item_desc": "Titulo",
        "descripcion_larga": "Descripción completa\nsegunda línea",
    })
    payload = TiendaNubePayloadBuilder().build_update_product_payload(producto)
    assert "Descripción completa" in payload["description"]["es"]
    assert "segunda línea" in payload["description"]["es"]

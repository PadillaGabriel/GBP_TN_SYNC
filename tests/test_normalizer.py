import pytest

from app.dominio.errores import DatoIncompletoError
from app.infraestructura.gbp.normalizador import GBPNormalizer


def test_normalizador_requiere_sku() -> None:
    normalizer = GBPNormalizer()

    with pytest.raises(DatoIncompletoError):
        normalizer.normalizar_stock({"stock": 5})


def test_normalizador_stock_usa_stock_disponible_y_no_general() -> None:
    normalizer = GBPNormalizer()

    stock = normalizer.normalizar_stock({"sku": "ABC", "stock": -2, "stor_id": 1})

    assert stock.sku == "ABC"
    assert stock.cantidad == 0
    assert stock.stock_original_gbp == -2


def test_normalizador_producto_no_usa_item_detail() -> None:
    normalizer = GBPNormalizer()

    producto = normalizer.normalizar_producto(
        {
            "item_id": 11,
            "item_code": "360",
            "item_desc": "DIFUSOR PAMELA FLOR 125CC",
            "item_detail": "VARIOS",
            "item_vendorCode": "D126154146",
            "item_web": "true",
            "WebSite_Description": "Descripcion web",
        }
    )

    assert producto.codigo_proveedor == "D126154146"
    assert producto.descripcion_web == "Descripcion web"
    assert producto.publicable_web is True

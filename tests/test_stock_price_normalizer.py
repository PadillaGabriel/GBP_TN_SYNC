from decimal import Decimal

from app.infraestructura.gbp.normalizador import GBPNormalizer


def test_normalizar_precio_detecta_price_list_item_price():
    normalizer = GBPNormalizer()
    precio = normalizer.normalizar_precio(
        [{"item_id": "30", "prliitem_price": "1234.50"}],
        price_list_id=1,
    )

    assert precio is not None
    assert precio.monto == Decimal("1234.50")
    assert precio.lista_precio_id == "1"


def test_normalizar_stock_suma_solo_depositos_ecommerce():
    normalizer = GBPNormalizer()
    stock = normalizer.normalizar_stock_desde_filas(
        [
            {"stor_id": "1", "Stock": "5.0000"},
            {"stor_id": "2", "Stock": "99.0000"},
            {"stor_id": "16", "Stock": "-2.0000"},
        ],
        sku="ABC",
        id_sistema_gbp="30",
        ecommerce_storage_ids=["1", "16"],
    )

    assert stock.consultable is True
    assert stock.cantidad == 3
    assert stock.stock_original_gbp == 3.0
    usados = [
        deposito.stor_id
        for deposito in stock.depositos
        if deposito.usado_para_tienda_nube
    ]
    assert usados == ["1", "16"]


def test_stock_no_consultable_si_no_hay_depositos_usados():
    normalizer = GBPNormalizer()
    stock = normalizer.normalizar_stock_desde_filas(
        [{"stor_id": "2", "Stock": "10.0000"}],
        sku="ABC",
        id_sistema_gbp="30",
        ecommerce_storage_ids=["1"],
    )

    assert stock.consultable is False
    assert stock.cantidad == 0

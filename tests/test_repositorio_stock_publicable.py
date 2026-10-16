"""La lectura de GBP no debe registrarse como stock confirmado en Tiendanube."""
from unittest.mock import MagicMock, patch

from app.dominio.modelos.stock import StockDeposito, StockProducto
from app.infraestructura.persistencia.repositorios.productos import RepositorioProductos


def test_consulta_gbp_preserva_stock_publicable_confirmado():
    db = MagicMock()
    existente = MagicMock()
    existente.stock_publicable_tn = 25
    db.scalar.return_value = existente
    stock = StockProducto(sku="3556", cantidad=19, depositos=[StockDeposito(
        stor_id="18", stock_disponible=19, stock_original=19,
        usado_para_tienda_nube=True,
    )])
    repo = RepositorioProductos(db)
    repo.guardar_stock(10, stock, actualizar_publicable=False)
    assert existente.stock_disponible_gbp == 19
    assert existente.stock_publicable_tn == 25
    repo.guardar_stock(10, stock)
    assert existente.stock_publicable_tn == 19
    assert db.commit.call_count == 2

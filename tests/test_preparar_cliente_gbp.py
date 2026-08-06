import pytest

from app.aplicacion.pedidos.casos_uso.preparar_cliente_gbp import (
    PedidoNoEncontradoParaClienteError,
    PrepararClienteGBP,
)


class RepositorioFalso:
    def obtener_por_id_para_validacion(self, pedido_id):
        if pedido_id == 404:
            return None
        return {
            "cliente": {
                "nombre": "Melisa",
                "apellido": "Carmona",
                "numero_documento": "33214438",
                "email": "melisa@example.com",
                "telefono": "+542964610324",
                "tipo_documento": None,
            },
            "envio": {
                "direccion": "Laguna Don Bosco 1636",
                "ciudad": "Río Grande",
                "provincia": "Tierra del Fuego",
                "codigo_postal": "9420",
                "pais": "AR",
            },
        }


def test_prepara_cliente_sin_escribir() -> None:
    resultado = PrepararClienteGBP(RepositorioFalso()).ejecutar(1)
    assert resultado["modo"] == "SOLO_LECTURA"
    assert resultado["cliente_propuesto"]["documento"] == "33214438"
    assert resultado["cliente_propuesto"]["clase_fiscal_id"] == 2
    assert resultado["cliente_propuesto"]["documento_facturacion_id"] == 145


def test_pedido_inexistente() -> None:
    with pytest.raises(PedidoNoEncontradoParaClienteError):
        PrepararClienteGBP(RepositorioFalso()).ejecutar(404)
